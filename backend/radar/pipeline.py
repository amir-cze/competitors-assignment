"""The per-source pipeline: fetch -> extract -> dedup -> (diff) -> score -> route -> deliver.

`Pipeline` receives every external collaborator (fetcher, adapters, scorer, deliverer) so it can be
exercised end to end against fixtures with no network and no model. One call of `process_source`
is one `Run`. It is safe to call from the worker or synchronously from the operator UI ("Check now").
All external failures are caught and turned into source health state.
"""

from __future__ import annotations

import uuid
from datetime import timedelta

from sqlalchemy import delete, select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.orm import Session, joinedload
from sqlalchemy.orm.exc import StaleDataError

from radar.assess.llm import BudgetExceeded
from radar.assess.scoring import Scorer, load_context
from radar.config import Settings
from radar.deliver.slack import SlackDeliverer
from radar.ingest.adapters import AdapterRegistry, AdapterResult, RawItem, SourceContext
from radar.ingest.dedup import find_by_url, find_exact, find_near_duplicate
from radar.ingest.diff import diff_page_text, render_diff_for_llm
from radar.ingest.extract import canonicalize_url, content_hash, extract_document, normalize_text
from radar.ingest.http import Fetcher
from radar.logging import get_logger
from radar.models import (
    HealthStatus,
    Item,
    ItemKind,
    ItemSource,
    PageSnapshot,
    RawDocument,
    Route,
    Run,
    Source,
    SystemState,
    Team,
    Topic,
    new_id,
    utcnow,
)
from radar.ops_events import record_event

log = get_logger(__name__)

MIN_TEXT_CHARS = 200
FIRST_RUN_UNDATED_CAP = 5
CLAIM_STALE_MINUTES = 30


class RunLog:
    def __init__(self) -> None:
        self.lines: list[dict] = []

    def add(self, msg: str, **data) -> None:
        self.lines.append({"t": utcnow().isoformat(timespec="seconds"), "msg": msg, **data})


class SourceGone(Exception):
    """Someone removed the competitor (or source) from the watchlist while this run was in progress.
    Not an error: the rows we are writing to no longer exist, so stop and discard quietly."""


def _source_exists(session: Session, source_id: uuid.UUID) -> bool:
    return session.scalar(select(Source.id).where(Source.id == source_id)) is not None


class Pipeline:
    def __init__(
        self,
        *,
        settings: Settings,
        fetcher: Fetcher,
        adapters: AdapterRegistry,
        scorer: Scorer,
        deliverer: SlackDeliverer,
    ):
        self._settings = settings
        self._fetcher = fetcher
        self._adapters = adapters
        self._scorer = scorer
        self._deliverer = deliverer

    # ----------------------------------------------------------------------- entry points

    def process_source(self, session: Session, source_id: uuid.UUID, *, trigger: str = "schedule") -> Run:
        source = session.scalar(
            select(Source).options(joinedload(Source.competitor)).where(Source.id == source_id)
        )
        if source is None:
            raise ValueError("source not found")
        run = Run(source_id=source.id, trigger=trigger)
        session.add(run)
        session.commit()
        rlog = RunLog()
        rlog.add("start", kind=source.kind, url=source.url)

        ctx = SourceContext(
            url=source.url,
            fetcher=self._fetcher,
            config=source.config or {},
            etag=source.etag,
            last_modified=source.last_modified,
            requires_js=source.requires_js,
            max_items=self._settings.max_items_per_run,
            session=session,
        )
        try:
            result = self._adapters.get(source.kind).fetch(ctx)
        except Exception as exc:  # adapter bug or unexpected network failure
            log.exception("pipeline.adapter_crash", source_id=str(source.id))
            result = AdapterResult(error=f"{type(exc).__name__}: {exc}"[:500])

        run.http_status = result.http_status or None
        for note in result.notes:
            rlog.add(note)

        try:
            if result.error:
                self._on_failure(session, source, run, rlog, result.error)
            elif result.not_modified:
                run.status = "not_modified"
                rlog.add("not modified (conditional GET)")
                self._on_success(session, source, run, rlog, result, items_found=None)
            else:
                self._apply_result_metadata(session, source, result)
                if source.kind == "page_watch":
                    self._handle_page_watch(session, source, run, rlog, result)
                    self._on_success(session, source, run, rlog, result, items_found=None)
                else:
                    self._handle_items(session, source, run, rlog, result.items)
                    self._on_success(session, source, run, rlog, result, items_found=len(result.items))
                run.status = "ok"
        except SourceGone:
            return self._abandon_run(session, source_id, trigger)
        except Exception as exc:
            # A database error leaves the transaction unusable; start clean before recording the failure.
            # Work is committed per item, so at most the current item is lost.
            session.rollback()
            if not _source_exists(session, source_id):
                return self._abandon_run(session, source_id, trigger)
            log.exception("pipeline.crash", source_id=str(source.id))
            self._on_failure(session, source, run, rlog, f"{type(exc).__name__}: {exc}"[:500])

        run.finished_at = utcnow()
        run.log = rlog.lines
        source.claimed_at = None
        try:
            session.commit()
        except StaleDataError:
            # The source row vanished between our last check and this commit (removed from the watchlist).
            return self._abandon_run(session, source_id, trigger)
        return run

    @staticmethod
    def _abandon_run(session: Session, source_id: uuid.UUID, trigger: str) -> Run:
        session.rollback()
        log.info("pipeline.source_removed_mid_run", source_id=str(source_id))
        # The run row was cascade-deleted with the source; return a detached stand-in for the caller's log line.
        now = utcnow()
        return Run(
            id=new_id(),
            source_id=source_id,
            trigger=trigger,
            status="cancelled",
            started_at=now,
            finished_at=now,
            items_found=0,
            items_new=0,
            items_assessed=0,
            llm_cost_usd=0.0,
            error="source removed from the watchlist while the run was in progress",
            log=[],
        )

    def score_pending_items(self, session: Session, limit: int = 20) -> int:
        """Second chance for items that were parked (budget, transient LLM failure)."""
        if not self._scorer.available:
            return 0
        items = list(
            session.scalars(
                select(Item)
                .options(joinedload(Item.competitor))
                .where(Item.status.in_(["pending", "budget_hold"]))
                .order_by(Item.first_seen_at.asc())
                .limit(limit)
            ).all()
        )
        if not items:
            return 0
        teams, topics = load_context(session)
        rlog = RunLog()
        done = 0
        for item in items:
            cost = self._score_and_deliver(session, item, teams, topics, rlog)
            if cost is None and item.status == "budget_hold":
                break
            if cost is not None:
                done += 1
            session.commit()
        if done:
            log.info("pipeline.pending_scored", count=done)
        return done

    # ----------------------------------------------------------------------- items

    def _apply_result_metadata(self, session: Session, source: Source, result: AdapterResult) -> None:
        source.etag = result.etag
        source.last_modified = result.last_modified
        if result.config_updates:
            cfg = dict(source.config or {})
            cfg.update(result.config_updates)
            source.config = cfg
            if "recipe" in result.config_updates:
                record_event(
                    session,
                    "recipe_learned",
                    f"Learned a new extraction recipe for {source.competitor.name} – {source.label or source.url}",
                    source_id=source.id,
                    data=result.config_updates,
                )
        if result.page_html and source.kind != "page_watch":
            session.add(
                RawDocument(
                    source_id=source.id,
                    url=source.url,
                    http_status=result.http_status,
                    body=result.page_html[:400_000],
                )
            )

    def _handle_items(
        self, session: Session, source: Source, run: Run, rlog: RunLog, raw_items: list[RawItem]
    ) -> None:
        run.items_found = len(raw_items)
        if not raw_items:
            rlog.add("no items returned")
            return

        first_run = source.last_success_at is None
        window_start = utcnow() - timedelta(days=self._settings.backfill_days)
        teams, topics = load_context(session)
        competitor = source.competitor

        # Fast path: which URLs do we already know?
        new_raw: list[RawItem] = []
        for raw in raw_items:
            canon = canonicalize_url(raw.url)
            existing = find_by_url(session, competitor.id, canon)
            if existing:
                _link(session, existing, source, canon)
                continue
            raw.url = canon
            new_raw.append(raw)
        rlog.add("url dedup", known=len(raw_items) - len(new_raw), new=len(new_raw))
        if not new_raw:
            return

        # Backfill policy: on the very first run, do not alert on history.
        if first_run:
            dated = [r for r in new_raw if r.published_at]
            if dated:
                to_score = {r.url for r in dated if r.published_at >= window_start}
            else:
                to_score = {r.url for r in new_raw[:FIRST_RUN_UNDATED_CAP]}
            rlog.add(
                "first run backfill policy", will_score=len(to_score), archived=len(new_raw) - len(to_score)
            )
        else:
            to_score = {r.url for r in new_raw}

        created = 0
        for raw in new_raw[: self._settings.max_items_per_run]:
            try:
                with session.begin_nested():
                    item = self._ingest_one(session, source, raw, archive=raw.url not in to_score, rlog=rlog)
            except Exception as exc:
                if not _source_exists(session, source.id):
                    raise SourceGone from exc  # don't fail the remaining 30 items one by one
                log.warning("pipeline.item_failed", url=raw.url, error=str(exc)[:300])
                rlog.add("item failed", url=raw.url, error=str(exc)[:200])
                continue
            if item is None:
                continue
            created += 1
            run.items_new += 1
            if item.status == "pending":
                cost = self._score_and_deliver(session, item, teams, topics, rlog)
                if cost is not None:
                    run.llm_cost_usd += cost
                    run.items_assessed += 1
            session.commit()
        rlog.add("done", created=created)

    def _fetch_article(self, raw: RawItem, source: Source) -> tuple[str | None, str]:
        """Returns (html, final_url). Uses feed-provided content when substantial, otherwise fetches the page."""
        if raw.html and len(raw.html) > 3000:
            return raw.html, raw.url
        res = self._fetcher.fetch_rendered(raw.url) if source.requires_js else self._fetcher.fetch(raw.url)
        if not res.ok or not res.body:
            return raw.html, raw.url  # fall back to whatever the feed gave us rather than dropping the item
        return res.body, res.final_url

    def _ingest_one(
        self, session: Session, source: Source, raw: RawItem, *, archive: bool, rlog: RunLog
    ) -> Item | None:
        competitor = source.competitor
        html, final_url = self._fetch_article(raw, source)
        if html:
            doc = extract_document(html, final_url)
            text = doc.text
            title = raw.title or doc.title or final_url
            published = raw.published_at or doc.published_at
            canonical = doc.canonical_url if doc.canonical_url.startswith("http") else raw.url
        else:
            text = normalize_text(raw.summary or "")
            title = raw.title or raw.url
            published = raw.published_at
            canonical = raw.url

        if canonical != raw.url:
            existing = find_by_url(session, competitor.id, canonical)
            if existing:
                _link(session, existing, source, raw.url)
                return None

        text = text or title
        digest = content_hash(f"{title}\n{text}")
        exact = find_exact(session, competitor.id, digest)
        if exact:
            _link(session, exact, source, raw.url)
            rlog.add("exact duplicate", url=raw.url, of=str(exact.id))
            return None

        embedding: list[float] | None = None
        if len(text) >= MIN_TEXT_CHARS and self._scorer.available:
            try:
                embedding = self._scorer.embed_for_dedup(session, title, text)
                near = find_near_duplicate(
                    session, competitor.id, embedding, threshold=self._settings.dedup_similarity_threshold
                )
                if near:
                    dup, sim = near
                    _link(session, dup, source, raw.url)
                    rlog.add("near duplicate", url=raw.url, of=str(dup.id), similarity=round(sim, 3))
                    return None
            except BudgetExceeded:
                rlog.add("embedding skipped: budget exhausted")
            except Exception as exc:
                rlog.add("embedding failed", error=str(exc)[:200])

        status = "archived" if archive else ("thin" if len(text) < MIN_TEXT_CHARS else "pending")
        item = Item(
            competitor_id=competitor.id,
            kind=ItemKind.post.value,
            canonical_url=canonical,
            title=title[:500],
            published_at=published,
            content_text=text,
            content_hash=digest,
            embedding=embedding,
            status=status,
        )
        session.add(item)
        session.flush()
        session.add(ItemSource(item_id=item.id, source_id=source.id, url=raw.url))
        session.flush()
        rlog.add("new item", url=canonical, status=status, title=title[:80])
        return item

    # ----------------------------------------------------------------------- scoring + delivery

    def _score_and_deliver(
        self, session: Session, item: Item, teams: list[Team], topics: list[Topic], rlog: RunLog
    ) -> float | None:
        if not self._scorer.available:
            item.status = "budget_hold"
            rlog.add("scoring skipped: OPENAI_API_KEY missing", item=str(item.id))
            return None
        try:
            result = self._scorer.score_item(session, item, teams=teams, topics=topics)
        except BudgetExceeded as exc:
            item.status = "budget_hold"
            rlog.add("scoring parked: budget", item=str(item.id))
            self._budget_event_once(session, str(exc))
            return None
        except Exception as exc:
            log.warning("pipeline.score_failed", item_id=str(item.id), error=str(exc)[:300])
            rlog.add("scoring failed", item=str(item.id), error=str(exc)[:200])
            item.status = "pending"
            return None

        by_id = {t.id: t for t in teams}
        for a in result.assessments:
            if a.route == Route.immediate.value:
                team = by_id[a.team_id]
                delivery = self._deliverer.enqueue_immediate(session, item, a, team)
                if delivery.status == "pending":
                    sent = self._deliverer.send(session, delivery, team)
                    rlog.add("slack immediate", team=team.key, sent=sent, item=str(item.id))
        rlog.add(
            "scored", item=str(item.id), max_relevance=item.max_relevance, category=item.primary_category
        )
        return result.cost_usd

    def _budget_event_once(self, session: Session, message: str) -> None:
        key = "budget_alert_date"
        state = session.get(SystemState, key)
        today = utcnow().date().isoformat()
        if state and state.value.get("date") == today:
            return
        if state is None:
            state = SystemState(key=key, value={})
            session.add(state)
        state.value = {"date": today}
        record_event(
            session,
            "budget_hold",
            f"{message}. New items are stored and will be scored when budget resets.",
            level="warn",
            alert_via=self._deliverer,
        )

    # ----------------------------------------------------------------------- page watch

    def _handle_page_watch(
        self, session: Session, source: Source, run: Run, rlog: RunLog, result: AdapterResult
    ) -> None:
        text = result.page_text or ""
        digest = content_hash(text)
        prev = session.scalar(
            select(PageSnapshot)
            .where(PageSnapshot.source_id == source.id)
            .order_by(PageSnapshot.fetched_at.desc())
        )
        if prev is None:
            session.add(PageSnapshot(source_id=source.id, text_hash=digest, text=text))
            rlog.add("baseline snapshot stored", chars=len(text))
            return
        if prev.text_hash == digest:
            rlog.add("no change")
            return

        ignore = (source.config or {}).get("ignore_patterns") or []
        diff = diff_page_text(prev.text, text, ignore_patterns=ignore)
        if diff.changed_chars < self._settings.page_change_min_chars or diff.is_empty:
            session.add(PageSnapshot(source_id=source.id, text_hash=digest, text=text))
            rlog.add("change below threshold", changed_chars=diff.changed_chars)
            return

        rendered = render_diff_for_llm(diff)
        label = source.label or source.url
        item = Item(
            competitor_id=source.competitor_id,
            kind=ItemKind.page_change.value,
            canonical_url=source.url,
            title=f"{label} wording changed"[:500],
            published_at=utcnow(),
            content_text=rendered,
            content_hash=content_hash(rendered),
            page_diff={
                **diff.as_dict(),
                "before_excerpt": prev.text[:1500],
                "after_excerpt": text[:1500],
                "page_label": label,
            },
            status="pending",
        )
        session.add(item)
        session.flush()
        session.add(ItemSource(item_id=item.id, source_id=source.id, url=source.url))
        session.add(PageSnapshot(source_id=source.id, text_hash=digest, text=text, item_id=item.id))
        run.items_found = 1
        run.items_new = 1
        rlog.add(
            "page change detected",
            changed_chars=diff.changed_chars,
            added=len(diff.added),
            removed=len(diff.removed),
        )
        teams, topics = load_context(session)
        cost = self._score_and_deliver(session, item, teams, topics, rlog)
        if cost is not None:
            run.llm_cost_usd += cost
            run.items_assessed += 1

    # ----------------------------------------------------------------------- health + scheduling

    def _on_success(
        self,
        session: Session,
        source: Source,
        run: Run,
        rlog: RunLog,
        result: AdapterResult,
        *,
        items_found: int | None,
    ) -> None:
        now = utcnow()
        previous_health = source.health
        source.last_run_at = now
        source.last_success_at = now
        source.consecutive_failures = 0
        source.last_error = None
        source.next_run_at = now + timedelta(minutes=source.interval_minutes)
        label = f"{source.competitor.name} – {source.label or source.url}"

        new_health = HealthStatus.healthy.value
        if items_found is not None:
            if items_found == 0 and (source.baseline_items_per_run or 0) >= 2:
                new_health = HealthStatus.structure_changed.value
            if items_found > 0 or source.baseline_items_per_run is None:
                source.baseline_items_per_run = (
                    float(items_found)
                    if source.baseline_items_per_run is None
                    else 0.7 * source.baseline_items_per_run + 0.3 * items_found
                )
        if any(n.startswith("structure_changed") for n in result.notes):
            record_event(
                session,
                "structure_changed",
                f"Layout changed on {label}; recipe re-derived automatically.",
                level="warn",
                source_id=source.id,
                alert_via=self._deliverer,
            )

        source.health = new_health
        if new_health != previous_health:
            if new_health == HealthStatus.structure_changed.value:
                record_event(
                    session,
                    "health",
                    f"{label} returned 0 items (usually {source.baseline_items_per_run:.0f}). The page structure may have changed.",
                    level="warn",
                    source_id=source.id,
                    alert_via=self._deliverer,
                )
            elif previous_health in (HealthStatus.failing.value, HealthStatus.structure_changed.value):
                record_event(
                    session,
                    "health",
                    f"{label} recovered.",
                    level="info",
                    source_id=source.id,
                    alert_via=self._deliverer,
                )
        rlog.add(
            "scheduled", next_run_at=source.next_run_at.isoformat(timespec="minutes"), health=source.health
        )

    def _on_failure(self, session: Session, source: Source, run: Run, rlog: RunLog, error: str) -> None:
        now = utcnow()
        previous_health = source.health
        run.status = "error"
        run.error = error
        source.last_run_at = now
        source.consecutive_failures += 1
        source.last_error = error
        backoff = min(source.interval_minutes * (2 ** min(source.consecutive_failures, 5)), 24 * 60)
        source.next_run_at = now + timedelta(minutes=backoff)
        source.health = (
            HealthStatus.degraded.value if source.consecutive_failures < 3 else HealthStatus.failing.value
        )
        rlog.add("failure", error=error, failures=source.consecutive_failures, retry_in_minutes=backoff)
        if source.health == HealthStatus.failing.value and previous_health != HealthStatus.failing.value:
            record_event(
                session,
                "health",
                f"{source.competitor.name} – {source.label or source.url} has failed {source.consecutive_failures} times in a row: {error}",
                level="error",
                source_id=source.id,
                alert_via=self._deliverer,
            )


# --------------------------------------------------------------------------- pure DB helpers (no collaborators)


def _link(session: Session, item: Item, source: Source, url: str) -> None:
    exists = session.scalar(select(ItemSource).where(ItemSource.item_id == item.id, ItemSource.url == url))
    if not exists:
        session.add(ItemSource(item_id=item.id, source_id=source.id, url=url))


def due_source_ids(session: Session, limit: int) -> list[uuid.UUID]:
    """Claim due sources with SKIP LOCKED so several workers can run without a coordinator."""
    now = utcnow()
    stale = now - timedelta(minutes=CLAIM_STALE_MINUTES)
    rows = session.execute(
        select(Source.id)
        .where(
            Source.enabled.is_(True),
            Source.next_run_at <= now,
            (Source.claimed_at.is_(None)) | (Source.claimed_at < stale),
        )
        .order_by(Source.next_run_at)
        .limit(limit)
        .with_for_update(skip_locked=True)
    ).all()
    ids = [r[0] for r in rows]
    for sid in ids:
        session.get(Source, sid).claimed_at = now
    if ids:
        session.commit()
    return ids


def claim_once(session: Session, job: str, *, period: str) -> bool:
    """Cross-replica "run exactly once per period" for jobs that are not idempotent (the nightly eval).

    First worker to INSERT `job:{job}:{period}` into system_state wins; everyone else gets False.
    No lock to leak and nothing to clean up: the row doubles as the record that the job ran.
    """
    stmt = (
        pg_insert(SystemState)
        .values(key=f"job:{job}:{period}", value={"claimed_at": utcnow().isoformat()})
        .on_conflict_do_nothing(index_elements=[SystemState.key])
        # RETURNING yields no row on conflict; rowcount is unreliable for ORM inserts.
        .returning(SystemState.key)
    )
    won = session.execute(stmt).first() is not None
    session.commit()
    return won


def prune_retention(session: Session, settings: Settings) -> dict:
    raw_cutoff = utcnow() - timedelta(days=settings.raw_html_retention_days)
    snap_cutoff = utcnow() - timedelta(days=settings.snapshot_retention_days)
    raw_deleted = session.execute(delete(RawDocument).where(RawDocument.fetched_at < raw_cutoff)).rowcount
    # Keep the latest snapshot per source regardless of age, and any snapshot tied to an item.
    latest_ids = (
        select(PageSnapshot.id)
        .distinct(PageSnapshot.source_id)
        .order_by(PageSnapshot.source_id, PageSnapshot.fetched_at.desc())
    )
    snap_deleted = session.execute(
        delete(PageSnapshot).where(
            PageSnapshot.fetched_at < snap_cutoff,
            PageSnapshot.id.not_in(latest_ids),
            PageSnapshot.item_id.is_(None),
        )
    ).rowcount
    return {"raw_documents_deleted": raw_deleted, "snapshots_deleted": snap_deleted}

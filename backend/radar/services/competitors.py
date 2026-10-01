from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import datetime

from sqlalchemy import func, select
from sqlalchemy.orm import Session, joinedload

from radar.config import get_settings
from radar.errors import Conflict, NotFound, UpstreamFailure
from radar.ingest.discovery import DiscoveryResult, discover
from radar.ingest.extract import canonicalize_url
from radar.ingest.http import Fetcher
from radar.models import Competitor, HealthStatus, Item, Source, utcnow


@dataclass
class CompetitorStats:
    item_count: int
    last_item_at: datetime | None
    health: str  # healthy | attention | checking


def _ensure_scheme(url: str) -> str:
    return url if url.startswith(("http://", "https://")) else f"https://{url}"


def _interval_for(kind: str) -> int:
    settings = get_settings()
    return (
        settings.page_watch_interval_minutes
        if kind == "page_watch"
        else settings.default_source_interval_minutes
    )


def health_rollup(sources: list[Source]) -> str:
    healths = {s.health for s in sources if s.enabled}
    if not healths or healths <= {HealthStatus.new.value}:
        return "checking"
    if healths & {HealthStatus.failing.value, HealthStatus.structure_changed.value}:
        return "attention"
    return "healthy"


def stats_for(session: Session, competitor: Competitor) -> CompetitorStats:
    count, last = session.execute(
        select(func.count(), func.max(Item.first_seen_at)).where(Item.competitor_id == competitor.id)
    ).one()
    return CompetitorStats(
        item_count=int(count or 0), last_item_at=last, health=health_rollup(competitor.sources)
    )


def get_competitor(session: Session, competitor_id: uuid.UUID) -> Competitor:
    comp = session.scalar(
        select(Competitor).options(joinedload(Competitor.sources)).where(Competitor.id == competitor_id)
    )
    if comp is None:
        raise NotFound("Competitor not found")
    return comp


def list_competitors(session: Session) -> list[Competitor]:
    return list(
        session.scalars(select(Competitor).options(joinedload(Competitor.sources)).order_by(Competitor.name))
        .unique()
        .all()
    )


def discover_for(url: str, fetcher: Fetcher) -> DiscoveryResult:
    try:
        return discover(url.strip(), fetcher)
    except ValueError as exc:
        raise UpstreamFailure(str(exc)) from exc
    except Exception as exc:
        raise UpstreamFailure(f"We could not inspect that site: {exc}") from exc


def create_competitor(
    session: Session, *, name: str, homepage_url: str, notes: str | None, sources: list[dict]
) -> Competitor:
    if session.scalar(select(Competitor).where(func.lower(Competitor.name) == name.strip().lower())):
        raise Conflict(f"{name.strip()} is already on the watchlist.")
    comp = Competitor(
        name=name.strip(), homepage_url=canonicalize_url(_ensure_scheme(homepage_url)), notes=notes
    )
    session.add(comp)
    session.flush()
    seen: set[str] = set()
    for s in sources:
        url = canonicalize_url(_ensure_scheme(s["url"]))
        if url in seen:
            continue
        seen.add(url)
        session.add(
            Source(
                competitor_id=comp.id,
                kind=s["kind"],
                url=url,
                label=s.get("label"),
                config=s.get("config") or {},
                interval_minutes=_interval_for(s["kind"]),
                next_run_at=utcnow(),
            )
        )
    session.flush()
    session.refresh(comp)
    return comp


def update_competitor(session: Session, competitor_id: uuid.UUID, changes: dict) -> Competitor:
    comp = get_competitor(session, competitor_id)
    for field, value in changes.items():
        setattr(comp, field, value)
    session.flush()
    return comp


def delete_competitor(session: Session, competitor_id: uuid.UUID) -> None:
    comp = session.get(Competitor, competitor_id)
    if comp:
        session.delete(comp)


def add_watch_page(session: Session, competitor_id: uuid.UUID, *, url: str, label: str | None) -> Competitor:
    comp = get_competitor(session, competitor_id)
    canon = canonicalize_url(_ensure_scheme(url))
    if any(s.url == canon for s in comp.sources):
        raise Conflict("That page is already being watched.")
    if not label:
        path = canon.split("//", 1)[-1].split("/", 1)[-1].strip("/")
        label = (path.replace("-", " ").replace("/", " / ").title() if path else "Homepage") + (
            " page" if path else ""
        )
    session.add(
        Source(
            competitor_id=comp.id,
            kind="page_watch",
            url=canon,
            label=label,
            interval_minutes=_interval_for("page_watch"),
            next_run_at=utcnow(),
        )
    )
    session.flush()
    session.refresh(comp)
    return comp


def check_now(session: Session, competitor_id: uuid.UUID) -> int:
    """Pull every enabled source forward so the worker picks it up on its next tick."""
    comp = get_competitor(session, competitor_id)
    queued = 0
    for s in comp.sources:
        if s.enabled:
            s.next_run_at = utcnow()
            queued += 1
    return queued

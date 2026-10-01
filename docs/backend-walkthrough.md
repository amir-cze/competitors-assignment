# Backend walkthrough

How the backend works, following one competitor blog post from "the worker wakes up" to "a card in the R&D inbox." This is the operational companion to [design.md](design.md), which covers the *why*.

## Two processes, one database

The backend is two entry points over the same Postgres:

- `radar-api` — FastAPI. It reads and writes rows. It never fetches a competitor site on a schedule.
- `radar-worker` — the unattended part. APScheduler in-process; no Redis, no Celery, no external cron.

Both are built by the same composition root, `radar/container.py`. It constructs the shared collaborators once — the LLM client, the HTTP fetcher, the Slack notifier, the adapter registry, the `Pipeline` — and hands them to whichever process is starting. That is also why tests can swap in a `FakeLLM` and a `FixtureFetcher` without touching pipeline code.

## What triggers a collection

Nothing external. The worker's scheduler (`radar/worker.py`) has four jobs:

| Job | Cadence | Does |
| --- | --- | --- |
| `tick` | every `worker_tick_seconds` (30 s) | claim due sources, process them, then score any parked items |
| `heartbeat` | every 60 s | write `system_state.worker_heartbeat`, ping `HEALTHCHECK_URL`, retry failed Slack deliveries |
| `digests` | hourly at :05 | send daily digests for teams whose `digest_hour_utc` just passed |
| `nightly` | `eval_hour_utc`:15 (03:15 UTC) | prune old raw HTML and snapshots, run the golden-set eval |

"Due" is a column, not a timer. Every `sources` row has `next_run_at`. On each tick the worker runs, in effect:

```sql
SELECT id FROM sources
WHERE enabled
  AND next_run_at <= now()
  AND (claimed_at IS NULL OR claimed_at < now() - interval '30 minutes')
ORDER BY next_run_at
FOR UPDATE SKIP LOCKED
LIMIT 8;
```

then stamps `claimed_at` and commits (`due_source_ids` in `radar/pipeline.py`). `SKIP LOCKED` means two worker replicas never grab the same source and never need to coordinate. The 30-minute stale rule un-sticks a source if a worker died mid-run. Claimed IDs go to a small thread pool (`worker_concurrency`, default 4).

Every other trigger funnels into the same `Pipeline.process_source()`:

- Business **Check now** sets `next_run_at = now()`; the next tick picks it up.
- Ops **Run** calls `process_source` inline and returns the run log.
- A newly saved competitor gets `next_run_at = now()` on each of its sources.

## One source, one run

`process_source` opens a `runs` row first, so a crash still leaves a record. Then:

1. **Fetch via adapter.** `source.kind` selects `feed`, `sitemap`, `html_list`, or `page_watch` from the `AdapterRegistry`. The adapter receives a `SourceContext` with the URL, stored ETag / Last-Modified, per-source config JSON (for example a cached CSS recipe), and the fetcher. The fetcher enforces per-host delay, robots.txt, and conditional GET. A `304 Not Modified` short-circuits the run.

2. **URL dedup.** Each returned link is canonicalized (tracking parameters stripped, trailing slash normalized) and looked up in `items.canonical_url` for that competitor. Known URLs get a new `item_sources` link — so we know the same post appeared on both the blog and the press room — and are dropped.

3. **First-run backfill policy.** If the source has never succeeded, items older than `backfill_days` (7) are stored as `archived` rather than scored. Adding a competitor with five years of posts does not page anyone. Undated items on a first run are capped at five.

4. **Per item, inside a savepoint:** fetch the article page (unless the feed already shipped substantial HTML), extract main text with trafilatura, hash it. Exact hash match → link and drop. Otherwise embed `title + text` and ask pgvector for the nearest item from the last 90 days; cosine similarity ≥ `dedup_similarity_threshold` (0.95) → link and drop. Survivors become an `items` row with status `pending` (or `thin` if under 200 characters, `archived` if outside the backfill window).

5. **Score.** `Scorer.score_item` (`radar/assess/scoring.py`) loads the active `prompt_versions` row, renders the system prompt with every team's lens, every topic, and few-shot examples pulled from prior `feedback`, and makes one Structured Outputs call. The response carries a headline, summary, category, `is_substantive`, and one `(relevance, why, evidence_quote, topics_matched)` per team. It writes one `assessments` row per team stamped with `prompt_version_id` and model, records spend in `llm_usage`, and moves the item to `assessed`. If the daily budget is exhausted or the key is missing, the item stays `budget_hold` and `score_pending_items` retries it on the next tick.

6. **Route and deliver.** `decide_route` (`radar/assess/routing.py`) is a pure function: muted competitor → `muted`; not substantive → `inbox`; `≥ immediate_threshold` → `immediate`; `≥ digest_threshold` → `digest`; else `inbox`. For `immediate` on a team with Slack configured, a `deliveries` row is inserted with a unique `(item, team, channel)` key *before* the HTTP call — that is the idempotency guard — and then posted. Failures are retried by the heartbeat job.

7. **Health.** On success: `consecutive_failures = 0`, `next_run_at = now + interval_minutes`, and a rolling `baseline_items_per_run`. HTTP 200 with zero yield against a non-zero baseline is a `structure_changed` ops event. On failure: exponential backoff (`interval × 2^n`, capped at 24 h), health `degraded` after one failure and `failing` after three. The transition to `failing` fires an operator alert once, not every tick.

Page-watch sources skip steps 2–4. They store a `page_snapshots` row; the next fetch is diffed against the previous snapshot with the noise rules in `radar/ingest/diff.py` (dates, counters, cookie banners, reordered lines), and only a diff above `page_change_min_chars` becomes an `items` row of kind `page_change` carrying the `page_diff` JSON. That item then flows through the same scoring step.

## How it is stored

Every table lives in `radar/models.py`; Alembic owns the schema (`backend/alembic/`).

**Configuration, owned by the business**

- `teams` — key, name, lens paragraph, `immediate_threshold`, `digest_threshold`, `digest_hour_utc`, encrypted Slack webhook.
- `topics` — name, description, optional team.
- `competitors` — name, homepage, muted flag.
- `sources` — kind, url, `interval_minutes`, health, ETag / Last-Modified, config JSON, `next_run_at`, `claimed_at`, failure counters, yield baseline.

**Content**

- `items` — one row per distinct piece of competitor content: `canonical_url`, `content_text`, `content_hash`, `embedding` (pgvector), `kind` (`post` / `page_change`), `status`, plus denormalized `max_relevance` and `primary_category` for fast inbox sorting.
- `item_sources` — the many-to-many that lets one item come from several sources.
- `page_snapshots` — watched-page text history.
- `raw_documents` — fetched HTML, kept `raw_html_retention_days` (30) so a broken extraction can be debugged.

**Judgement**

- `assessments` — one row per item per team: relevance, category, why, evidence quote, topics matched, route, and the `prompt_version_id` and model it was produced under.
- `deliveries` — what was sent where, status, error, unique on `(item, team, channel)`.
- `feedback` — the thumbs, keyed by item and team, with reason and a `promoted_to_golden` flag.

**Quality loop**

- `prompt_versions` — immutable content, exactly one active.
- `eval_items` — the golden set: title, content, per-team boolean labels, `origin` (seed / feedback / manual).
- `eval_runs` — precision / recall / F1 per team per run, cost, prompt version.

**Operations**

- `runs` — one per fetch: status, HTTP code, items found / new / assessed, cost, and the step-by-step JSON log the ops Runs page shows.
- `llm_usage` — every model call with purpose, tokens, and cost; the daily budget is a sum over today's rows.
- `ops_events` — recipe learned, source failing, structure changed, budget hold.
- `system_state` — heartbeat and a few single-row flags.

## Item status lifecycle

```
pending ──score──▶ assessed
   │
   ├── no key / budget ──▶ budget_hold ──retry on tick──▶ assessed
   ├── under 200 chars ──▶ thin        (kept, never scored)
   └── outside backfill ─▶ archived    (kept, never scored)
```

## Where the API fits

The API is thin on purpose. Routers under `radar/api/routes/` parse the request and call a service; services under `radar/services/` do the querying and mutation; serializers under `radar/api/serializers/` turn ORM rows into Pydantic response shapes. Domain errors raised by services (`radar/errors.py`) become HTTP responses in one handler in `radar/api/main.py`.

The inbox endpoint, for example, is one query over `items` joined to `assessments`, filtered by team and route, with the caller's `feedback` row attached. No scoring happens at read time. The API does real work in only three places, and each reuses the worker's objects rather than its own logic:

- **Discovery** — probing a homepage when a URL is pasted. Nothing is saved until the user confirms.
- **Ops → Run** — `process_source` inline.
- **Ops → Run golden eval** — `Evaluator.run` inline.

## Configuration that shapes behaviour

All from the environment (`radar/config.py`). The ones that change what you see:

| Setting | Default | Effect |
| --- | --- | --- |
| `WORKER_TICK_SECONDS` | 30 | how often due sources are claimed |
| `WORKER_CONCURRENCY` | 4 | sources processed in parallel per worker |
| `DEFAULT_SOURCE_INTERVAL_MINUTES` | 60 | re-check cadence for feeds / listings |
| `PAGE_WATCH_INTERVAL_MINUTES` | 360 | re-check cadence for watched pages |
| `BACKFILL_DAYS` | 7 | first-run window; older is archived |
| `MAX_ITEMS_PER_RUN` | 40 | cap per source per run |
| `LLM_DAILY_BUDGET_USD` | 5 | hard stop; overflow parks as `budget_hold` |
| `DEDUP_SIMILARITY_THRESHOLD` | 0.92 | cosine threshold for near-duplicates |
| `PAGE_CHANGE_MIN_CHARS` | 200 | minimum moved text to count as a change |
| `RAW_HTML_RETENTION_DAYS` | 30 | pruned nightly |
| `SNAPSHOT_RETENTION_DAYS` | 90 | pruned nightly |

## Seeing it live

```bash
cd backend
uv run radar-worker
```

Add a competitor on the Watchlist, then watch `/ops/runs` fill in within the next tick. `/ops` → System shows the heartbeat turning from Quiet to Alive within a minute.

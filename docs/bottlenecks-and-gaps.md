# Bottlenecks and technical gaps

An honest engineering account of where Radar's limits are, why it was built this way anyway, and what would
change first as the watchlist grows. Numbers are from running the system against real competitor sites, not
estimates.

## Where the time goes

The worker claims up to 8 due sources every 30 s and runs 4 in parallel threads. Per source:

| Case | Work | Wall time |
| --- | --- | --- |
| Nothing new (>95% of runs) | one conditional GET → `304 Not Modified` | 1–3 s |
| New item | article fetch (+2 s per-host politeness gap) → extract → embedding (~0.3 s) → scoring call (3–6 s) → Slack | ~8 s per item, nearly all waiting on OpenAI |
| First run of a source | listing + one fetch per URL, but only in-window items are scored; the rest are archived unscored | 2 s × pages (a 200-URL sitemap ≈ 7 min) |

One worker: 4 lanes × 3,600 s/h ≈ 14,400 lane-seconds/hour ≈ **~1,800 new items/hour**, or thousands of quiet
sources/hour. Noma's realistic scale is 30–60 competitors × 2–3 sources ≈ 150 sources and 50–100 new items *per day*.
Utilization is in the low single digits. Postgres as the queue (`SELECT … FOR UPDATE SKIP LOCKED`) handles thousands of
claims per second; Radar makes about eight per 30 seconds.

## Bottlenecks, in order

### 1. One model call per new item

The dominant cost in both latency and dollars (~$0.002 per item with `gpt-4.1-mini`; the 18-item golden eval costs
$0.017). Everything before the call exists to avoid it: URL and hash dedup, embedding near-duplicates (≥ 0.95 cosine),
the "thin content" gate, the first-run backfill policy, and a hard daily USD budget that parks overflow as `budget_hold`.
A provider-side quota failure trips a 15-minute circuit breaker so the worker fails fast instead of retrying per item.

**Next:** a cheap pre-filter (embedding similarity to the three lenses, or a nano-tier model) so only plausible items
reach the full three-team call; batch 3–5 items per call. Expected: 2–4× fewer tokens for the same recall.

### 2. The source is the unit of work

This is the real structural limit. One source run does fetch → extract → dedup → score → deliver for every new item,
sequentially, in one lane. Consequences:

- **Head-of-line blocking.** A competitor with 30 new posts holds a lane for ~4 minutes; if several sources are fat at
  once, cheap 304-checks for everyone else wait behind them. One competitor's publishing day delays detection for all.
- **Coarse parallelism.** The 4 lanes are "4 sources", not "4 units of actual work". Scoring calls for independent items
  cannot overlap.
- **Coarse failure.** Item 17 of 30 failing marks the *source* run as failed and backs off the whole source, although
  the site is healthy. Per-item savepoints limit database damage, but the scheduling decision is per source.
- **Mixed limits.** Fetching is bound by the target site's politeness, scoring by OpenAI's rate limit, delivery by Slack.
  Unrelated capacities, one lane, so the slowest governs.

**Next (first change I would make as volume grows):** split into two stages with two units.

- *Discovery* — unit = source. Fetch the listing/feed, diff against known URLs, insert `items` rows as `pending`.
  Seconds per run regardless of how many new items appeared. Keeps `next_run_at` + `SKIP LOCKED`.
- *Processing* — unit = item. Claim from `items WHERE status = 'pending' FOR UPDATE SKIP LOCKED`; fetch article, extract,
  dedup, score, route, deliver. Own pool size (tuned to OpenAI's limits), own per-item retry/backoff and cost accounting.

The pieces exist: `pending` is a status, `score_pending_items` already drains it each tick, and `_ingest_one` is already
per-item inside a savepoint. The change is to stop calling `_score_and_deliver` from inside the source run — roughly
60–80 lines and an `attempts` column. Why not now: at 150 sources it changes nothing observable, and the single-stage
pipeline is one function a successor can read top to bottom.

### 3. Per-host politeness is per process

`_HostGate` (2 s minimum gap per host, robots.txt cache) lives in worker memory. Two worker replicas are each polite
and the site sees double the rate. **Next, if and only if we run more than one worker:** a shared per-host token
bucket and robots cache in Redis (~20 lines). This is the one place a Redis dependency earns its keep; it is not a
reason to adopt a queue.

### 4. JavaScript-only sites

Default fetching is plain HTTP. Sources flagged `requires_js` render with headless Chromium (Playwright, optional
install). Each render costs 2–5 s and real CPU/memory. Today zero sources on the watchlist need it; discovery shows
JS-only sites as "no candidates found", so the miss is visible, not silent. **Next, if more than a handful need it:** a
dedicated render pool, which is the one piece I would feed from a proper queue.

## Why not a message queue (Celery / RQ / SQS) now

It would not move bottleneck 1 (the item still needs its 5 s model call) or 3 (politeness is a property of the target
site). It would help with 2, but Postgres already provides claim-with-lock semantics and the `pending` status is already
the queue; splitting stages does not require a broker. A queue adds Redis/RabbitMQ, a result backend and another
process to watch, and the item would still take 8 s. Decision rule: adopt a broker when the render pool exists or when
the system passes ~1,000 sources, whichever comes first.

## Horizontal scaling: what happens with N replicas

Everything stateful is in Postgres, so every process is disposable. `docker compose up --scale worker=3` works today.
There is no leader election; instead each job is either partitioned by a claim or safe to run on every replica.

| Process / job | With N replicas | Why it is safe |
| --- | --- | --- |
| API | N stateless servers behind any load balancer | Auth is a signed cookie or a header token; no server-side session, no caches that matter |
| Web (Next.js) | N stateless servers | Pure proxy to the API |
| Worker `tick` (collection) | Due sources are **divided** between replicas | `due_source_ids` claims with `FOR UPDATE SKIP LOCKED` and stamps `claimed_at` in the same transaction |
| Immediate Slack sends | Exactly one per item × team | `deliveries.dedupe_key UNIQUE`; the second writer fails the constraint and rolls back |
| `heartbeat` (every 60 s) | Runs on every replica | Last write wins on one `system_state` row; it answers "is *a* worker alive", which is the question |
| `digests` (hourly :05) | Runs on every replica, **sends once** | `send()` keys the delivery `digest:{team}:{date}`; same UNIQUE constraint, so N callers → one Slack message |
| `nightly` prune | Runs on every replica | Idempotent: `DELETE … WHERE fetched_at < cutoff` |
| `nightly` eval | **Claimed once per day** | `claim_once()` inserts `job:nightly_eval:{date}` into `system_state` with `ON CONFLICT DO NOTHING`; the winner runs the golden set, the rest log `eval_skipped`. Without this, N replicas meant N eval runs and N× the eval's LLM spend |

What does *not* scale with replicas: per-host politeness (bottleneck 3), the in-process quota breaker (each replica
discovers "OpenAI has no credits" with one failed call of its own, then stops), and Postgres itself, which is the
queue, the vector index and the store. The daily LLM budget *does* hold across replicas because it is summed from the
`llm_usage` table on every call, not tracked in memory.

## Technical gaps (known, deliberate)

| Gap | Impact today | Fix |
| --- | --- | --- |
| Shared password for `/`, single token for `/ops` | No per-user identity or audit of who gave feedback | SSO (OIDC); first thing to replace before a real handoff |
| `SESSION_SECRET` derives the at-rest key for Slack webhooks | Rotating it re-encrypts nothing: existing webhooks become unreadable and must be re-entered | Separate `ENCRYPTION_KEY` with key-version prefix on stored secrets |
| APScheduler is in-process | Job state is not durable across restarts | Acceptable: durable state (`next_run_at`) is in Postgres; `misfire_grace_time` covers a restart over the :05 digest |
| Scheduler tick granularity 30 s | Up to 30 s latency between "due" and "running" | Irrelevant for weekly content; it is a setting |
| Single LLM provider | OpenAI outage → items park as `budget_hold` and score later | `LLMClient` protocol is the swap point; a second client is ~60 lines |
| Discovery on Webflow-style sites proposes individual posts as "listings" (their related-posts widgets) | Operator must deselect them in the preview | Penalise candidates whose URL depth exceeds the blog index; prefer the shortest path with ≥ N items |
| Near-duplicate threshold is global (0.95) | Boilerplate-heavy news pages once collapsed at 0.92; 0.95 fixed it on the current watchlist | Per-competitor threshold, or dedup on body text only (exclude title/nav) |
| Feedback happens in the dashboard only | Slack readers must click through to vote | Slack interactivity payload (needs a Slack app, not a webhook) |
| No per-item "send to Slack" action | Items scored before Slack was connected are not retro-delivered | `POST /items/{id}/slack/{team}` writing to `deliveries` (idempotent) |
| Heartbeat requires `HEALTHCHECK_URL` | Unset → "nobody checks it's running" is true of the design, not of the instance | One env var; healthchecks.io free tier |
| Worker logs `tick skipped: maximum number of running instances` during long runs | Looks like an error; it is the one-tick-at-a-time guard | Cosmetic: lower the log level for that message |
| Competitor removed while its first run is still scoring | Found in a real log: every remaining item failed on a foreign key and the final source update crashed the run. Now detected on the first failure; the run stops with one `source_removed_mid_run` line and no further model calls | Done. Remaining waste is the items already scored before the click; a "removing…" state that waits for in-flight runs would close that |

## What growth looks like

- **More sources**: linear in quiet-run cost (seconds each). The first-run backfill policy keeps onboarding a 500-page
  site from spending budget. Nothing changes until ~1,000 sources.
- **More items**: bottleneck 1, then 2. Pre-filter and batching first; stage split second.
- **More teams**: one row and one paragraph. Scoring is one call per item, not per team; a fourth team adds output
  tokens, not calls.
- **More topics**: prompt context, not classifiers. Marginal cost is tokens.
- **More consumers**: Slack webhooks are per team, not per person; the dashboard is read-mostly behind one API.
  Per-user identity is the gap (see SSO above), not throughput.

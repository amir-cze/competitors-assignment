# Radar — design

Radar is a competitor-content monitor for Noma. The product thesis is simple: **the enemy is not missing news, it is being muted.** Three teams (Marketing, Product, R&D) each get a short, explainable inbox of what actually matters to them, plus Slack when something is worth interrupting the day. A separate operator desk exists so the person who built this is not on the hook at 3 a.m.

## Product decisions

The brief is deliberately high level. These are the calls I made on behalf of the users, each traced to a line in it.

- *"A system that alerts on everything will be muted within a week"* → three outcomes per team, not one alert: ≥ 75 interrupts in Slack, 50–74 waits for the daily digest, the rest sits in an inbox nobody is pinged about. Thresholds and digest hour are per team. On the first run history is archived, not announced. The briefing says "Quiet this week. That is the point." — silence is a feature, so the UI treats it as one.
- *"Each with a different idea of what important means"* → one item, three independent scores, three one-sentence *why*s, each with a verbatim quote. The lens is a paragraph the team writes in plain language, not a config key.
- *"Capabilities they have that we do not"* → Product's lens is meaningless without knowing what *we* sell. "What we sell" is a field in Settings owned by the business and injected into every assessment. It is not an engineer's sentence in a prompt file.
- *"Add a competitor … with no exposure to how the system works"* → paste a homepage. Discovery proposes feeds, sitemaps, listings and pages to watch, with a preview of what each would yield; the user ticks boxes. The word "RSS" never appears.
- *"A page whose messaging quietly changes"* → page watch with a cosmetic-vs-substantive filter, and "Wording that changed" as its own section of the briefing rather than mixed into posts.
- *"Nobody has to check that it is still running"* → the business page carries an attention banner in business language ("2 sources failing", "monitoring paused") so the people who depend on it find out before the operator does.
- *"Not in a position to audit it"* → every card has thumbs; feedback feeds the prompt as calibration, a golden set measures precision and recall per team per prompt version, and disagreements are a review queue. The *why* and the quote exist so a non-expert can disagree with the model with evidence.
- *"Run for the next two years"* → a daily LLM budget the owner sets, a quota breaker, and a bill that cannot surprise anyone.

## Architecture

```
competitor sites  →  adapters  →  extract / dedup / diff  →  per-team scoring  →  route  →  inbox + Slack
                         ↑                                         ↑
                   discovery (URL in)                    team lenses + topics + feedback
                         ↑                                         ↑
                    business UI                               operator UI
                         │                                         │
                         └──────────── FastAPI + Postgres ─────────┘
                                          ↑
                                   APScheduler worker
```

**Ingest.** Four adapters share one contract (`fetch → list of items or page text`): RSS/Atom, sitemap, HTML listing, page watch. Discovery from a homepage URL probes `<link rel=alternate>`, common feed paths, `sitemap.xml`, and listing pages (`/blog`, `/news`, `/resources`) and shows a preview before anything is saved. HTML listings cache a CSS recipe and re-derive it when yield collapses. Fetching is polite (per-host delay, robots.txt, conditional GET). New posts are extracted with trafilatura; exact-hash then embedding near-duplicates collapse the same announcement across a blog and a press room into one item.

**Assess.** One Structured Output call per item returns, for each team: relevance 0–100, a category, one-line why, a verbatim evidence quote, topics matched. The prompt template is versioned and owned by operators. Lenses, topics and the company's own "what we sell" profile are owned by the business and injected at call time. Few-shot examples come from prior feedback. Thin content is forced into the inbox. A daily USD budget parks remaining items as `budget_hold` rather than failing the run.

**Route and deliver.** Pure thresholds per team: ≥ immediate → Slack now; ≥ digest → daily digest; else inbox only. Muted competitors never alert. Slack posts are Block Kit, deep-link to the item for feedback, and are idempotent via a `deliveries` table.

**Surfaces.** `/` is the business briefing: watchlist, per-team inbox with thumbs, what we sell, lenses, topics, Slack settings. `/ops` is token-gated: source health, run logs, prompt versions, golden-set evals, heartbeat and spend. Shared-password / operator-token auth is the first thing to replace with SSO.

**Worker.** APScheduler ticks; due sources are claimed with `SELECT … FOR UPDATE SKIP LOCKED`. Failures back off. Yield dropping to zero on HTTP 200 is a structure-change event. A heartbeat URL (healthchecks.io) is pinged every minute so silence is the alert.

## Technology choices

| Chose | Why | Rejected |
| --- | --- | --- |
| Python 3.12, FastAPI, SQLAlchemy 2, Alembic, Pydantic v2, `uv` | Strong for HTTP + workers + Structured Outputs; typed schemas shared with the LLM; I can defend every layer in 90 minutes. | n8n / Zapier (fails “no workflow canvas”, no eval story). |
| Next.js 15 + Tailwind | Two distinct products in one origin, cookie session via a same-origin proxy. | Separate SPAs or a Python template UI (worse two-surface split). |
| Postgres 16 + pgvector | One store for OLTP, JSON diffs, and near-dup embeddings. | Redis + Celery (extra moving parts at this volume). |
| OpenAI `gpt-4.1-mini` Structured Outputs + `text-embedding-3-small` | Cheap, schema-locked, enough for scoring. | LangChain (thin value over the SDK). Firecrawl / Diffbot (hides the adapter problem this assignment is about; would revisit at 100+ sources). |
| Railway + Docker Compose | Same images locally and in prod; always-on worker without a second orchestrator. | Serverless cron (cold starts, no SKIP LOCKED story). |
| APScheduler in-process | No broker to run. Horizontal scale is more worker replicas pulling the same queue. | Celery/RQ. |
| Incoming webhooks per team | Lowest-friction Slack. | Slack app with OAuth (better later, more setup for a handoff). |

Different constraints, different picks: if the watchlist were 200+ JS-heavy sites, I would make Playwright the default and put a crawl budget in front of it. If several regions needed isolation, I would split scoring into its own service behind a queue. If legal required on-prem models, the `LLMClient` protocol is the swap point — the rest of the pipeline does not care.

## How it behaves as it grows

- **Sources.** Claiming is `SKIP LOCKED`, so a second worker replica is extra throughput with no coordinator. Per-host politeness stays correct because it is keyed on domain, not process.
- **Items.** Dedup (hash, then cosine ≥ 0.95) and a “is this substantive?” gate keep the LLM off boilerplate. The daily budget is a hard stop: overflow sits in the inbox unscored, visible on `/ops`.
- **Teams / topics.** Scoring is one call per item, not per team; adding a fourth team is a row and a paragraph, not a new pipeline. Topics are prompt context, not a separate classifier.
- **Retention.** Raw HTML 30 days, snapshots 90, text kept. Logs are per-run JSON, not a second database.

## Output quality — how we know, how it improves

Useful is defined per team, so the loop is per team.

1. **Every surfaced card can be marked useful / not useful**, with an optional reason. That mark is stored against the assessment, not as a free-floating comment.
2. **A golden set** (seeded from real competitor posts, plus every *disagreement* from feedback — a human overruling the route; agreements would test nothing) is scored offline against the active prompt version. Votes can be withdrawn, and withdrawing removes the label they created. Precision, recall and F1 are stored per team, per prompt version, with cost.
3. **Live metrics** on `/ops/evals` compare thumbs to the route that was chosen: precision on what we interrupted people with, and a recall proxy for “useful but left in the archive.” Disagreements are a review queue; one click promotes them into the golden set.
4. **Prompt versions** are immutable. Activating a new one is an operator action; the next eval run tells you if it won.

The seed golden set exists so week one is not “trust the demo.” The inbox empty-state is deliberate: quiet means the thresholds are doing their job.

## Left out, and next

Left out on purpose: SSO / per-user identity, a Slack OAuth app, LinkedIn/Twitter adapters, a full Playwright image as default, automatic threshold tuning, a public status page, multi-tenant orgs.

Next, in order: SSO, a Slack interactivity payload so thumbs happen without opening the dashboard, Playwright for the handful of JS-only newsrooms, then a weekly “should we lower Marketing’s immediate threshold?” suggestion driven by the eval trend.

Three product gaps I know about and chose not to half-build:

- **Language trends.** Marketing's lens is partly about *terms* — "whether they are pushing a particular term or trying to define a category." That is a cross-competitor, over-time question, and Radar scores one item at a time. Topics let the business ask "watch this term"; nothing yet says "three competitors started saying *agentic security* this quarter." This is the first product feature I would build: a monthly term-frequency view over assessed items, with the model proposing new terms rather than the business having to guess them.
- **Who saw what.** The brief's own pain is "nobody is quite sure who checked what." With a shared password there is no "seen by" or "assigned to"; Slack is the record today. This lands with SSO, not before it.
- **Sales.** The brief mentions sales as the team that hears news days late. Immediate routing fixes the latency; a sales-shaped output ("what to say when a prospect brings this up") would be a fourth lens. Scoring is per team already, so it is a row in `teams` plus a "create team" button, not a redesign — I left it out because nobody asked for it yet.

The first *scaling* change is structural rather than a feature: today the source is the unit of work, so one competitor’s big publishing day holds a lane for minutes. Splitting into a discovery stage (unit = source) and a processing stage (unit = item, claimed from `items.status = 'pending'`) fixes head-of-line blocking without a broker. Measured limits, the order of bottlenecks, and the known gaps are in [bottlenecks-and-gaps.md](bottlenecks-and-gaps.md).

## Risks

- **Sites that only exist in JavaScript.** Default fetch will look empty; the operator can flag `requires_js`. Until that is used, those competitors are a discovery miss, not a silent miss — the preview will say so.
- **Prompt drift.** A well-meaning lens rewrite can tank precision. Mitigation: prompt versioning + eval before/after, and business edits lenses not the template.
- **Slack webhook leakage.** Webhooks are encrypted at rest (Fernet derived from `SESSION_SECRET`). Still rotate if a database dump leaks.
- **Default passwords.** `/ops` flags when `BUSINESS_PASSWORD` / `OPS_TOKEN` are still the shipped defaults. Change them before the handoff.
- **OpenAI outage or budget exhaustion.** Ingest continues; items park as `budget_hold` and score when the budget resets or the operator hits “score pending.”
- **Legal / robots.** We honour robots.txt and identify as RadarBot. A competitor that blocks us will show as a failing source, not a crash.
- **Attribution.** Scoring can be confidently wrong. Evidence quotes and the thumbs loop are the check; we never auto-tune thresholds from a single downvote.

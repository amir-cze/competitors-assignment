# Radar — the complete tour

Every screen, every button, and what happens underneath when you press it. Read it once before the video;
keep it open during the 90-minute session. Where it says *"underneath"*, that is the part a reviewer will ask about.

Two surfaces, two audiences:

| URL | Who | Signs in with |
| --- | --- | --- |
| `/` | Marketing, Product, R&D — the people who *consume* | shared password (`BUSINESS_PASSWORD`) |
| `/ops` | whoever *runs* it — you, then a successor | operator token (`OPS_TOKEN`) |

Nothing on `/` mentions adapters, selectors, prompts or models. Nothing on `/ops` is needed day to day.

---

## Part 1 — The business surface (`/`)

### 1.1 Login

`/login`. One field, the shared password. Sets a signed cookie (`radar_session`); no server-side session store, which is
why the API can run as several replicas. The small "Operator? Sign in to /ops" link is the only hint that another
surface exists.

### 1.2 Briefing (`/`) — the home page

The cross-team overview. Designed so that *quiet* reads as success.

- **Stats row** — competitors watched, items seen in the last 7 days, monitoring status, last check time.
- **Attention banner** — appears only when something needs a human: sources failing, monitoring paused (no worker
  heartbeat for 5 min), scoring paused (LLM budget or quota). Written in business language; the operator details are on
  `/ops`.
- **Three team tiles** — per team, how many items were flagged this week, split into *interrupted* (sent to Slack) and
  *in the digest*. Zero shows "Quiet this week. That is the point." Each tile links to that team's inbox.
- **What mattered** — the strongest items of the week across all teams, one row each: score, competitor, time, title,
  the strongest team's one-line *why*, and a chip per team that it was flagged for (copper = sent to Slack, grey = digest).
  Point at one row in the video: same post, 85 for R&D, 65 for Product, nothing for Marketing.
- **Wording that changed** — recent page-change items, separate from posts because they read differently.

*Underneath:* one query (`/api/overview`), items are joined to their best assessment in the window; "flagged" means
route ∈ {immediate, digest}.

### 1.3 Watchlist (`/watchlist`) — who we follow

**Add a competitor**
1. Paste a homepage (`https://zenity.io`) → **Look up**.
2. Radar fetches the homepage and probes for `<link rel=alternate>` feeds, common feed paths, `sitemap.xml`,
   and listing pages (`/blog`, `/news`, `/resources`, `/changelog`…). Takes 5–20 s; the card says how long.
3. You get a **preview**: each candidate shows its kind (feed / sitemap / html list / page watch), how many recent items
   it yielded, two sample titles, and a copper **suggested** pill on the ones Radar would keep. Tick/untick.
   The homepage itself is always offered as a page watch.
4. The **name** is pre-filled from `og:site_name` / `<title>`, with taglines stripped ("Zenity | Agentic AI Security" → "Zenity").
5. **Add to watchlist**. Sources are scheduled immediately.

*Underneath:* `POST /api/competitors/discover` runs the probes in parallel (8 threads). Nothing is saved until you press
Add. The user never chooses RSS, CSS selectors or a model — that is the self-sufficiency requirement in one screen.

**Per competitor card** — health dot (rolls up its sources), piece count, last item time, the list of sources with their
own health dots, and four actions:

- **Check now** — marks all its sources due; the worker picks them up within 30 s. The video's rescue button.
- **Mute / Unmute** — muted competitors are still collected and scored, but never alert anyone (route becomes
  *muted*). For a competitor you want on record but not in Slack.
- **Watch a page** — paste any URL (`/pricing`, a product page). Adds a page-watch source: the text is snapshotted,
  and future changes become "wording changed" items. See 2.3 for how change detection works.
- **Remove** — deletes the competitor and everything collected from it (confirm dialog).

**First run behaviour:** when a source is added, everything already on the site older than `BACKFILL_DAYS` is stored as
*archived* — visible in "Everything scanned", never scored, never sent. Only genuinely new content from then on costs
money or interrupts anyone. This is the "don't flood Slack on day one" decision.

### 1.4 Inboxes (`/inbox/marketing`, `/inbox/product`, `/inbox/rnd`)

One inbox per team. Header: team name, the team's lens in full, and two counters — **N flagged** (sent to Slack or
in the digest) and **N scanned** (everything Radar read for this team in the window).

**Views** (tabs), each with a one-line description under the row that quotes the team's real threshold:

| Tab | Shows | Why it exists |
| --- | --- | --- |
| **Flagged for {Team}** | score ≥ digest threshold (default 50) | the default: what Radar thinks deserves attention |
| **Everything scanned** | every scored item, including those filed below threshold | the audit view — "what did Radar decide *not* to show me?" Mark one Useful here and it learns it missed something |
| **Page wording changes** | only `page_change` items | they read differently from posts; Marketing lives here |
| **Marked useful** | items this team voted Useful | the saved list; part of what scoring is calibrated against |

**Filters:** headline search, time window (7/30/90 days), category (product launch, feature update, positioning shift,
funding, partnership, research, hiring signal, compliance).

**Each card:**
- **Score** (0–100, this team's relevance) — the big number on the left.
- Competitor · kind (new post / page change) · category · when published.
- **Title** → links to the item page.
- **Why** — one sentence written for this team, naming what changed and why *they* should care.
- **Evidence quote** — verbatim from the source, so a non-expert can check the model's claim.
- **Topic pills** — which watched topics the model saw in it.
- **Route pill** — what Radar did: **Sent to Slack** (≥ 75) · **In daily digest** (50–74) · **Filed, not sent** (< 50).
  It is a status, not a button.
- **Worth your time? Useful / Not useful** — the feedback loop. See 1.7 for what it does.

Empty state on "Flagged": *"Nothing that needs you right now. Quiet is a feature."*

### 1.5 Item page (`/items/{id}?team=…`)

The full picture for one item:
- Headline (model-rewritten, neutral) and the original title; **Original →** link; category; two-sentence summary.
- **What the wording did** (page changes only) — two columns, *Taken out* and *Put in*, with the character count.
- **Why it matters, by team** — all three assessments side by side: score, route, category, *why*, quote. The clearest
  demonstration that one item gets three independent judgements.
- **Excerpt** of the extracted text.
- Right column: **Was this useful for {Team}?** with an optional *why* box (reasons are shown to the model as
  calibration), and **Seen on** — every URL this item was found at (duplicates collapsed into one card, see 2.2).

### 1.6 Settings (`/settings`) — the business configures the judgement

**What we sell** (top card, applies to all teams). A paragraph describing Noma's product line and what it does *not*
sell. Injected into every scoring call as `ABOUT US`. Product's lens — "capabilities they have that we do not" — can
only be judged against this. Ships with starter text and a "Starter text — edit it" pill until someone saves their own.
Demo beat: change one phrase, save, say "the business owns this, not a prompt file."

**Per team** (tabs Marketing / Product / R&D):

*What {Team} cares about*
- **Lens** — a free-text paragraph, injected verbatim into the prompt as `TEAM product cares about: …`. Rewrite it the
  way you would brief an analyst. Changing it affects the next item scored; no restart.
- **Topics** — short names (`MCP`, `AI red teaming`) with optional description; team-scoped or shared (◦). They are
  listed in the prompt as "topics the business asked us to watch"; the model tags matches, which show as pills on cards
  and in Slack. Click a pill to remove it. (Honest note: a topic match is a signal to the model, not a hard score boost —
  see the FAQ.)

*When to interrupt*
- **Send to Slack at** (default 75) — the score that interrupts someone's day.
- **Daily digest at** (default 50) — below this the item is filed and nobody is told.
- **Digest hour UTC** (default 6) — when the daily roll-up goes out.
- **Send to Slack** checkbox + **Slack incoming webhook** — paste once; stored encrypted (Fernet), shown masked afterwards.
- **Save** · **Test Slack** (posts a hello to the channel) · **Preview digest** (shows what tomorrow's digest would contain)
  · **Send digest now** (forces it).

### 1.7 What Useful / Not useful actually does

Not a tag. Three effects, none of them on the item you clicked:

1. **Changes the prompt for the next item.** Each team's most recent votes (3 useful, 3 not useful, with reasons) are
   rendered into the system prompt as calibration examples. Takes effect on the next scoring call.
2. **A disagreement becomes a permanent test case.** Useful on a *filed* item, or Not useful on a *flagged* one,
   promotes the item into the golden set (origin `feedback`) with your verdict as the label. Every eval from then on
   checks whether the prompt gets it right. **Agreements are not promoted** — Useful on something already flagged tells
   the eval nothing — they count as calibration and in the live metrics only. So after voting Useful on flagged items the
   golden set still reads "seed 18"; vote Useful on something in "Everything scanned" that was filed to see a promotion.
3. **Feeds the live quality numbers** on `/ops/evals` — precision on flagged items, recall proxy on filed ones.

**Undo.** Click the selected answer again on a card (or **Withdraw** on the item page) to clear the vote. If that vote
had created a golden label, the label is removed too, and the golden item is deleted when no feedback labels remain.
Seeded and hand-written golden items are never touched by a business click; the operator removes those on `/ops/evals`.
Changing Useful → Not useful withdraws the old label before applying the new rule.

Deliberately *not* done: rescoring the item, recalling a Slack message, moving thresholds. One downvote must not change
what interrupts a whole team.

### 1.8 What lands in Slack

**Immediate** (score ≥ team threshold): one Block Kit message per item per team — score, competitor, headline, *why*,
evidence quote, topics, and four buttons: **Open source**, **Details in Radar**, **👍 Useful**, **👎 Not useful**.
The thumbs are deep links into the item page that record the vote on arrival (incoming webhooks cannot receive
clicks; a Slack app with interactivity would make it zero-click — that is on the "next" list). Idempotent: the
`deliveries` table has a unique key per item × team, so a retry or a second worker cannot double-post.

**Daily digest** (at the team's hour): everything that scored in the digest band since the last digest, one message,
sorted by score. Sent once per team per day, enforced by the same unique key.

---

## Part 2 — What happens unattended

### 2.1 The worker

One process, APScheduler, four jobs:

| Job | When | What |
| --- | --- | --- |
| `tick` | every 30 s | claim due sources (`FOR UPDATE SKIP LOCKED`), process up to 4 in parallel, then score anything left `pending` |
| `heartbeat` | every 60 s | write a `system_state` row (the "Alive" on `/ops`), ping `HEALTHCHECK_URL` if set, retry failed Slack deliveries |
| `digests` | hourly at :05 | send digests for teams whose hour it is |
| `nightly` | 03:15 UTC | prune raw HTML / old snapshots, run the golden-set eval (claimed once per day across replicas) |

The schedule itself lives in the database: each source has `next_run_at` and `interval_minutes`. The worker is stateless;
run two and they split the work. A failing source backs off exponentially (×2 per failure, cap 24 h) and recovers on
the first success.

### 2.2 Per source, per run

1. **Fetch** politely: robots.txt honoured, 2 s minimum gap per host, conditional GET (most runs end with a 304 in 1–3 s).
2. **Adapter** turns the response into candidate items — feed, sitemap, HTML listing (heuristic → cached CSS recipe →
   LLM-derived recipe if yield collapses; see 3.2), or page text for page watches.
3. **Dedup** chain, cheapest first: URL already known (including alias URLs) → skip without fetching; exact content hash →
   link as duplicate; **embedding** (`text-embedding-3-small`, pgvector cosine ≥ 0.95, same competitor, 90-day window) →
   link as near-duplicate. The same funding announcement on the blog, the press room and a news page becomes one card
   with three "Seen on" URLs.
4. **Extract** the article text (trafilatura). Thin content (< minimum chars) is kept but marked *thin* and not scored.
5. **Score** — one Structured Outputs call returns, for all teams at once: headline, summary, category, `is_substantive`,
   and per team relevance / why / evidence quote / topics matched. Scores are persisted with the prompt version and model.
6. **Route** per team by thresholds; **deliver** immediates to Slack; everything is visible in the inbox regardless.
7. **Health** bookkeeping: baseline items-per-run, "0 items on HTTP 200" flagged as a probable structure change,
   consecutive failures, ops events.

### 2.3 Page change detection

Four gates, each cheaper than the next: conditional GET → text hash (did anything change?) → line diff with noise
suppression (cookie banners, ©, "5 min read", numbers and dates masked, moved lines ignored) → size threshold (200
chars of real change) → only then an item is created with the before/after as its body, and the model is told to
*"focus on what the new wording claims that the old wording did not."* Changing only the copyright year produces nothing.

### 2.4 Money and outages

- **Daily LLM budget** (`LLM_DAILY_BUDGET_USD`), summed from `llm_usage` on every call. When exhausted, collection
  continues and items park as `budget_hold`; they score when the day rolls over or the operator presses "Score pending now".
- **Quota breaker**: if OpenAI says the account has no credits, scoring pauses for 15 min instead of failing every item,
  and `/ops` says so.
- If Slack rejects a message, the delivery is marked failed and retried on the next heartbeat.

---

## Part 3 — The operator surface (`/ops`)

### 3.1 System (`/ops`) — "the 3 a.m. page"

- **Worker** — Alive / Quiet, last heartbeat.
- **Queue** — sources due now, items waiting to be scored. **Score pending now** button.
- **LLM today** — spend vs budget, model name, and a notice if the provider breaker is open.
- **Checks** — database reachable, OpenAI key present, `HEALTHCHECK_URL` set, ops Slack set, which teams have Slack,
  and two flags that are red on purpose if **the business password or ops token is still the shipped default**.
  **Ping live** actually calls OpenAI and the database.
- **Health / runs 24h** — sources by health (healthy / attention / failing), run outcomes, and spend per day per purpose
  (assess / embed / recipe / eval).

### 3.2 Sources (`/ops/sources`)

Every source across all competitors: competitor and label, kind, enabled flag, health with the last error, last success
and next scheduled run, and **yield** as `new/found` for the last five runs (the fastest way to spot a page that went
quiet). Actions:

- **Run** — process it now and show the **run log** underneath: every step with timing (fetched, 304, recipe yielded N,
  exact duplicate, near duplicate 0.97, scored, delivered…). This log is the explainability of the pipeline.
- **Disable / Enable** — stop checking without deleting history.
- **Reset recipe** — HTML listings cache the CSS selectors that find posts (learned once by the LLM when the heuristic
  fails; relearned automatically when yield collapses). Reset forces a relearn for the case where the automation learned
  something plausible but wrong — e.g. it is picking up a "related posts" sidebar and yield is non-zero but low.

### 3.3 Runs (`/ops/runs`)

Every run across all sources, newest first, filterable by status (ok / error / running). Click a row for its log.
Where you go when a competitor "disappeared": you will see the 403, the timeout, or the "0 items (usually 12)".

### 3.4 Prompts (`/ops/prompts`)

The scoring prompt is a versioned template. The active version is shown in full. **New version**: paste the next prompt
and a note; **Save draft** or **Save and activate**. Validation refuses a template missing `{teams_block}`,
`{topics_block}` or `{examples_block}` — the business-owned parts cannot be edited out. Older versions are listed with
**Activate** so rollback is one click. Every assessment and every eval run records which version produced it.

The business never sees this page. They edit lenses, topics and "what we sell"; the operator edits *how the analyst
thinks*. That split is the answer to "prompt drift".

### 3.5 Evaluation (`/ops/evals`)

- **Live cards per team** — precision on flagged items (of what we interrupted people with, how much got Useful),
  recall proxy (Useful votes on items we filed), number of marks, missed-useful count. Empty until people vote.
- **Golden set size** by origin (seeded / promoted from feedback / manual).
- **Run golden eval** — scores every golden item with the *active* prompt, no persistence, and records precision / recall /
  F1 per team plus cost. Also runs nightly.
- **History** — one row per eval run: when, prompt version, n, per-team P/R, cost. This is how you tell a regression
  from a bad week: v1 vs v2 on the same items.
- **Disagreements** — every vote that contradicts the route (flagged-but-not-useful, filed-but-useful), with **Promote**
  to add it to the golden set (automatic for new votes; this handles older ones).
- **Golden set** table with per-team labels and origin (seed / feedback / manual), **Remove** per row, and
  **Add a labeled example** for hand-written cases.

### 3.6 Ops alerts

Events (`source failing N times`, `0 items — structure may have changed`, `recipe relearned`, `budget hold`, `recovered`)
are stored and, if `OPS_SLACK_WEBHOOK` is set, posted to an operator channel. If `HEALTHCHECK_URL` is set (e.g.
healthchecks.io), silence from the heartbeat is the alert — nobody has to check it is running.

---

## Part 4 — Suggested walkthrough order (for rehearsal)

1. `/` briefing → point at a row with three different scores.
2. `/watchlist` → paste a competitor → preview → Add → **Check now**.
3. `/settings` → edit "What we sell" one phrase → Save. Product tab → add topic → Save.
4. `/inbox/marketing` → read one card (score, why, quote, route pill) → **Everything scanned** for two seconds → open
   an item → **Not useful** with a reason.
5. `/ops` → Alive, spend, red default-credential flags if any.
6. `/ops/sources` → **Run** one → read the log.
7. `/ops/evals` → the disagreement you just created → **Run golden eval** → history row.
8. `/ops/prompts` → show the version list; do not edit on camera.

---

## FAQ — questions you will get, and the short answers

**Why one model call per item and not one per team?** Three calls would triple cost and lose the shared headline /
summary / substantive judgement. Structured Outputs returns all teams in one schema.

**Why not embeddings for relevance?** No explanation, no quote, no category. The thumbs loop needs all three.

**Why Postgres as the queue?** `SKIP LOCKED` gives claim semantics; `pending` is already the queue; one system to run.
Decision rule for a broker: a Playwright render pool or ~1,000 sources. See `bottlenecks-and-gaps.md`.

**Do topics force a score?** No — they are a prompt signal and a tag. A hard rule ("a topic match should not score below
the digest threshold") belongs in prompt v2, through `/ops/prompts`, with an eval before/after.

**What if the LLM is down?** Collection continues; items park; nothing is lost; `/ops` says why.

**What if a site redesigns?** Yield drops to 0 on HTTP 200 → ops event → recipe relearned automatically on the next run;
if it learned something wrong, Reset recipe.

**Who can see who voted?** Nobody — shared password, no identity. SSO is the first thing to replace; "seen by" lands
with it.

**How does it scale?** Stateless API and worker; sources partitioned by `SKIP LOCKED`; digests and eval made idempotent
by database constraints. The first structural change at scale is item-as-unit-of-work for the processing stage.

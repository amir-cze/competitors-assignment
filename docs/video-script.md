# Video script (≤ 5 minutes, one take)

Open on the briefing. Speak to a non-technical colleague, not to an interviewer.

**0:00–0:40 — what and why**  
“This is Radar. Noma’s competitors publish constantly; the failure mode is not missing a post, it is alerting so often that Marketing mutes us. Radar watches competitor sites, scores each piece separately for Marketing, Product and R&D, and only interrupts a team when it is actually for them.” Point at one row: “Same post, once — 85 for R&D, 65 for Product, nothing for Marketing. That is the whole idea.”

**0:40–1:20 — architecture in one breath**  
Share `/ops` for two seconds, then back. “A worker pulls due sources, adapters handle feeds, sitemaps, HTML listings and watched pages, we dedup, then one model call scores all three teams. Slack or inbox is a threshold, not a vibe. Operators see health, prompts and evals; the business never does.”

**1:20–2:40 — configure it the way its users would**  
1. Log in at `/` with the shared password.  
2. Watchlist → paste `https://zenity.io` (or whichever still resolves) → wait for the preview → keep the suggested sources → save.  
3. Settings → Product → add topic `MCP` if it is not there → tweak the lens by one sentence → save.  
4. Optional: paste a Slack webhook, Test Slack.

Say out loud: “They pasted a URL. They did not pick RSS, CSS selectors, or a model.”

**2:40–3:40 — what it produces**  
Open Marketing inbox. Read one card: competitor, score, why, evidence quote. Open the item. If a wording-change exists, show before/after. Mark one Yes and one No. Mention Slack only if a test message landed; otherwise say “same card would have posted above 75.”

**3:40–4:20 — how we know it is useful**  
`/ops` → Evals. Point at golden-set size, last precision/recall per team, the disagreements queue, “Run golden eval.” “Thumbs from the inbox become labels. Labels become a nightly score. Prompt versions are how we tell a regression from a bad week.”

**4:20–4:50 — left out, on purpose**  
“No SSO yet, no LinkedIn adapter, Playwright is opt-in so the default box stays small. Next is SSO and Slack buttons for feedback. The risk I am watching is JS-only sites and prompt drift — both have an operator path, not a silent failure.”

**4:50–5:00 — close**  
“Set it up once. After that, the business owns the watchlist and the lenses; ops owns sources, spend and whether the scores are still true.”

## If something is empty during recording

- No items: Watchlist → Check now on the competitor you just added, wait ~30s, refresh the inbox.  
- Discovery slow: say “this is a live fetch of their site” and keep rolling.  
- No Slack: skip the channel, show Alert settings and the inbox card instead.

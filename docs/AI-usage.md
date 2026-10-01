# AI usage

AI assistants were used throughout, as they are in the role. Everything below was read, run, or edited by me before it landed.

**Cursor agent (Claude)** — the only coding assistant used in this repository.

Used for:

- Turning the assignment and the agreed plan into a FastAPI / Next.js layout (models, adapters, worker, two UIs).
- Boilerplate I would otherwise copy: Alembic skeleton, Dockerfiles, GitHub Actions, Tailwind tokens, cookie proxy.
- First drafts of prompts, the design doc, the video script, and this note — then rewritten.
- Tests around routing, diffs, adapters, and the fixture pipeline; fixing issues the suite caught.
- UI implementation for the business briefing and `/ops`, including discovery and eval screens.

Not used for:

- The product thesis (“the enemy is being muted”) or the stack choices — those were decided before generation.
- Blind paste of secrets, production credentials, or competitor content into prompts beyond what is already public on their sites.
- The golden-set labels: those were written as judgments, not asked of the model.

**OpenAI models (runtime, not authoring)** — `gpt-4.1-mini` Structured Outputs for scoring, listing-recipe repair, and page-change summaries; `text-embedding-3-small` for near-duplicate detection. These are the product, not the author.

If a file looks generated, it was still reviewed against the assignment’s bars: two surfaces, unattended operation, and a visible quality loop.

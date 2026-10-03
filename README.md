# Radar

Competitor content monitoring for Noma. Watches competitor sites, scores each piece separately for Marketing, Product and R&D, and puts only what matters in an inbox (and Slack, if you want it).

The failure mode this is built against is not *missing* a post. It is alerting so often that someone mutes it.

## Run it locally

You need Docker, and an OpenAI key.

```bash
cp .env.example .env
# put OPENAI_API_KEY in .env
cd infra
docker compose up --build
```

Open [http://localhost:3000](http://localhost:3000).

- Business password: `noma-radar` (change `BUSINESS_PASSWORD`)
- Operator desk: [http://localhost:3000/ops](http://localhost:3000/ops) with `OPS_TOKEN`

Slack and [healthchecks.io](https://healthchecks.io) are optional. Without them, delivery stays in the inbox and the heartbeat only logs locally.

Compose Postgres is on **5434** so it does not collide with other local clusters.

### Native dev (API hot-reload)

```bash
docker compose -f infra/docker-compose.yml up db
cd backend
uv sync --group dev
uv run alembic upgrade head
uv run radar-seed
uv run radar-api          # :8000
uv run radar-worker       # another terminal
cd ../web
npm install
npm run dev               # :3000, proxies /api to the backend
```

`uv run radar-seed --competitors` will try live discovery against the default watchlist.

## What you are looking at

| Path | Who | What |
| --- | --- | --- |
| `/` | Marketing, Product, R&D | Briefing, per-team inbox, watchlist (paste a URL), what we sell, lenses, topics, Slack |
| `/ops` | Whoever keeps it running | Sources, runs, prompts, golden-set evals, heartbeat and spend |
| `/api/docs` | Operators | OpenAPI |

Paste a competitor homepage on the Watchlist. Radar proposes feeds, sitemaps and listing pages. Nothing is saved until you confirm.

## Deploy (Railway)

Same images as Compose. Create a Postgres plugin and three services:

1. **api** — `backend/Dockerfile`. Command: `alembic upgrade head && radar-seed && radar-api`. Health: `GET /api/health`.
2. **worker** — same image. Command: `radar-worker`.
3. **web** — `web/Dockerfile`. Env: `API_INTERNAL_URL` pointing at the api service (private network).

Set `OPENAI_API_KEY`, `BUSINESS_PASSWORD`, `OPS_TOKEN`, `SESSION_SECRET`, `PUBLIC_BASE_URL`. Optionally `HEALTHCHECK_URL` (a healthchecks.io ping URL) and `OPS_SLACK_WEBHOOK`.

## Tests

```bash
cd backend
uv run pytest
```

CI (GitHub Actions) runs ruff, pytest against Postgres+pgvector, and a Next.js production build.

## Docs

- [docs/design.md](docs/design.md) — architecture, choices, scale, quality loop, risks
- [docs/backend-walkthrough.md](docs/backend-walkthrough.md) — what triggers a collection, the per-source pipeline, and how everything is stored
- [docs/bottlenecks-and-gaps.md](docs/bottlenecks-and-gaps.md) — where the limits are, measured; what changes first as it grows; known gaps
- [docs/video-script.md](docs/video-script.md) — 5-minute walkthrough
- [docs/AI-usage.md](docs/AI-usage.md) — which assistants, for what

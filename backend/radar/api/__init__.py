"""HTTP layer: thin routers, schemas, serializers. Collaborators come from `radar.container`.

Layout
------
api/routes/business/   Watchlist, inbox, teams, topics. The people who consume the output.
api/routes/ops/        Sources, runs, prompts, evals, system. The people who keep it running.
api/schemas/           Request/response models, one file per resource.
api/serializers/       ORM -> schema. The only place that knows both shapes.
"""

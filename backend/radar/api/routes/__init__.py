"""Business and operator route packages. The app includes leaf routers; we do not nest APIRouters."""

from fastapi import FastAPI

from radar.api.routes.business import auth, inbox, overview, teams, topics, watchlist
from radar.api.routes.ops import auth as ops_auth
from radar.api.routes.ops import evals, prompts, sources, system


def register_routes(app: FastAPI) -> None:
    for module in (auth, overview, teams, topics, watchlist, inbox):
        app.include_router(module.router, prefix="/api")
    for module in (ops_auth, sources, prompts, evals, system):
        app.include_router(module.router, prefix="/api/ops")

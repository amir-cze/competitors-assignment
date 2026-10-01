from __future__ import annotations

from contextlib import asynccontextmanager

import uvicorn
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from radar import __version__
from radar.api.routes import register_routes
from radar.config import get_settings
from radar.container import get_deps
from radar.db import ping
from radar.errors import RadarError
from radar.logging import configure_logging, get_logger

log = get_logger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    configure_logging()
    deps = (
        get_deps()
    )  # build collaborators eagerly so misconfiguration fails at startup, not on first request
    log.info("api.start", version=__version__, env=deps.settings.environment, llm=deps.llm.configured)
    yield
    log.info("api.stop")


def create_app() -> FastAPI:
    settings = get_settings()
    app = FastAPI(
        title="Radar API",
        version=__version__,
        lifespan=lifespan,
        docs_url="/api/docs",
        openapi_url="/api/openapi.json",
    )
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    register_routes(app)

    @app.exception_handler(RadarError)
    async def radar_error_handler(_: Request, exc: RadarError) -> JSONResponse:
        """Services raise domain errors; this is the single place they become HTTP."""
        if exc.status_code >= 500:
            log.warning("api.upstream_error", error=exc.message)
        return JSONResponse(status_code=exc.status_code, content={"detail": exc.message})

    @app.get("/api/health")
    def health():
        return {"ok": ping(), "version": __version__}

    return app


app = create_app()


def run() -> None:
    dev = get_settings().environment == "development"
    uvicorn.run(
        "radar.api.main:app",
        host="0.0.0.0",
        port=8000,
        reload=dev,
        reload_dirs=["radar"] if dev else None,  # never watch .venv; package installs would wedge the reloader
    )


if __name__ == "__main__":
    run()

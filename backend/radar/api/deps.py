"""FastAPI dependencies and the `Annotated` aliases routes use for them.

def list_teams(db: DB, _: BusinessRole): ...
def run_source(source_id: uuid.UUID, db: DB, deps: Container, _: OpsRole): ...
"""

from __future__ import annotations

from typing import Annotated

from fastapi import Depends, Request, Response
from sqlalchemy.orm import Session

from radar.config import get_settings
from radar.container import Deps, get_deps
from radar.db import get_db
from radar.errors import Unauthorized
from radar.security import read_session, sign_session

BUSINESS_COOKIE = "radar_session"
OPS_COOKIE = "radar_ops"
COOKIE_MAX_AGE = 60 * 60 * 24 * 14


def set_session_cookie(response: Response, name: str, role: str) -> None:
    response.set_cookie(
        key=name,
        value=sign_session(role),
        httponly=True,
        samesite="lax",
        secure=get_settings().public_base_url.startswith("https://"),
        max_age=COOKIE_MAX_AGE,
        path="/",
    )


def clear_session_cookie(response: Response, name: str) -> None:
    response.delete_cookie(name, path="/")


def require_business(request: Request) -> str:
    """Business session, or an operator session (operators may use the business surface)."""
    if read_session(request.cookies.get(BUSINESS_COOKIE)) == "business":
        return "business"
    if read_session(request.cookies.get(OPS_COOKIE)) == "ops":
        return "ops"
    raise Unauthorized("Please sign in")


def require_ops(request: Request) -> str:
    """Operator session cookie, or a header token for scripts and CI."""
    if read_session(request.cookies.get(OPS_COOKIE)) == "ops":
        return "ops"
    token = request.headers.get("x-ops-token")
    if token and token == get_settings().ops_token:
        return "ops"
    raise Unauthorized("Operator access required")


DB = Annotated[Session, Depends(get_db)]
Container = Annotated[Deps, Depends(get_deps)]
BusinessRole = Annotated[str, Depends(require_business)]
OpsRole = Annotated[str, Depends(require_ops)]

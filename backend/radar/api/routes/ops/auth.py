"""Operator token for /ops."""

from fastapi import APIRouter, Response

from radar.api.deps import OPS_COOKIE, Container, OpsRole, clear_session_cookie, set_session_cookie
from radar.api.schemas import OpsLoginIn
from radar.errors import Unauthorized
from radar.security import constant_time_equals

router = APIRouter(prefix="/auth", tags=["ops"])


@router.post("/login")
def login(body: OpsLoginIn, response: Response, deps: Container):
    if not constant_time_equals(body.token, deps.settings.ops_token):
        raise Unauthorized("Invalid operator token")
    set_session_cookie(response, OPS_COOKIE, "ops")
    return {"ok": True, "role": "ops"}


@router.post("/logout")
def logout(response: Response):
    clear_session_cookie(response, OPS_COOKIE)
    return {"ok": True}


@router.get("/me")
def me(role: OpsRole):
    return {"role": role}

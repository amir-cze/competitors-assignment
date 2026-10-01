"""Shared password for the business surface."""

from fastapi import APIRouter, Response

from radar.api.deps import BUSINESS_COOKIE, BusinessRole, Container, clear_session_cookie, set_session_cookie
from radar.api.schemas import LoginIn
from radar.errors import Unauthorized
from radar.security import constant_time_equals

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post("/login")
def login(body: LoginIn, response: Response, deps: Container):
    if not constant_time_equals(body.password, deps.settings.business_password):
        raise Unauthorized("That password is not right.")
    set_session_cookie(response, BUSINESS_COOKIE, "business")
    return {"ok": True, "role": "business"}


@router.post("/logout")
def logout(response: Response):
    clear_session_cookie(response, BUSINESS_COOKIE)
    return {"ok": True}


@router.get("/me")
def me(role: BusinessRole):
    return {"role": role}

"""Health, queue, spend, integration checks."""

from fastapi import APIRouter, Query

from radar.api.deps import DB, Container, OpsRole
from radar.services import system as system_svc

router = APIRouter(tags=["ops-system"])


@router.get("/system")
def status(db: DB, deps: Container, _: OpsRole):
    return system_svc.status(db, settings=deps.settings, llm=deps.llm)


@router.post("/system/checks")
def live_checks(deps: Container, _: OpsRole):
    return system_svc.live_checks(deps.llm)


@router.post("/system/score-pending")
def score_pending(db: DB, deps: Container, _: OpsRole):
    return {"scored": deps.pipeline.score_pending_items(db, limit=50)}


@router.get("/llm-usage")
def llm_usage(db: DB, _: OpsRole, days: int = Query(7, le=90)):
    return system_svc.llm_usage_by_day(db, days)

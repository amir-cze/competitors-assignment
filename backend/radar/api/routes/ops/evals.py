"""Golden set and evaluation runs."""

from uuid import UUID

from fastapi import APIRouter, Query, Response

from radar.api.deps import DB, Container, OpsRole
from radar.api.schemas import GoldenIn, GoldenManualIn
from radar.api.serializers.ops import eval_run, golden_item
from radar.services import evaluation as eval_svc

router = APIRouter(prefix="/evals", tags=["ops-evals"])


@router.get("")
def dashboard(db: DB, _: OpsRole):
    return eval_svc.dashboard(db)


@router.post("/run")
def trigger_eval(db: DB, deps: Container, _: OpsRole, max_items: int | None = Query(None, le=200)):
    return eval_run(eval_svc.trigger(db, deps.evaluator, max_items))


@router.get("/golden/items")
def list_golden(db: DB, _: OpsRole):
    return [golden_item(row) for row in eval_svc.golden_items(db)]


@router.post("/golden", status_code=201)
def promote_item(body: GoldenIn, db: DB, _: OpsRole):
    row = eval_svc.promote(db, body.item_id, body.labels)
    return {"id": str(row.id), "labels": row.labels}


@router.post("/golden/manual", status_code=201)
def add_golden_manual(body: GoldenManualIn, db: DB, _: OpsRole):
    row = eval_svc.add_manual(
        db,
        competitor_name=body.competitor_name,
        title=body.title,
        content_text=body.content_text,
        labels=body.labels,
        kind=body.kind,
    )
    return {"id": str(row.id)}


@router.delete("/golden/{golden_id}", status_code=204)
def delete_golden(golden_id: UUID, db: DB, _: OpsRole):
    eval_svc.delete_golden(db, golden_id)
    return Response(status_code=204)


@router.get("/{eval_run_id}")
def eval_detail(eval_run_id: UUID, db: DB, _: OpsRole):
    return eval_run(eval_svc.get_eval_run(db, eval_run_id), with_details=True)

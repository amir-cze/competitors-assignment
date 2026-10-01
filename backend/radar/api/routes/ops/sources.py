"""Sources, runs and the operator event log."""

from uuid import UUID

from fastapi import APIRouter, Query, Response

from radar.api.deps import DB, Container, OpsRole
from radar.api.schemas import SourceIn, SourcePatch
from radar.api.serializers.ops import ops_event, source_row
from radar.api.serializers.ops import run as serialize_run
from radar.services import sources as sources_svc

router = APIRouter(tags=["ops-sources"])


@router.get("/sources")
def list_sources(db: DB, _: OpsRole):
    return [source_row(source, runs) for source, runs in sources_svc.list_sources(db)]


@router.post("/sources")
def create_source(body: SourceIn, competitor_id: UUID, db: DB, _: OpsRole):
    source = sources_svc.create_source(
        db, competitor_id, kind=body.kind, url=body.url, label=body.label, config=body.config
    )
    return source_row(source, [])


@router.patch("/sources/{source_id}")
def update_source(source_id: UUID, body: SourcePatch, db: DB, _: OpsRole):
    return source_row(sources_svc.update_source(db, source_id, body.model_dump(exclude_unset=True)), [])


@router.post("/sources/{source_id}/run")
def run_source(source_id: UUID, db: DB, deps: Container, _: OpsRole, sync: bool = Query(True)):
    """`sync=true` runs the pipeline inline and returns the run log; `sync=false` queues it."""
    if not sync:
        sources_svc.queue_run(db, source_id)
        return {"queued": True}
    return serialize_run(sources_svc.run_now(db, source_id, deps.pipeline), with_log=True)


@router.post("/sources/{source_id}/reset-recipe")
def reset_recipe(source_id: UUID, db: DB, _: OpsRole):
    sources_svc.reset_recipe(db, source_id)
    return {"ok": True}


@router.delete("/sources/{source_id}", status_code=204)
def delete_source(source_id: UUID, db: DB, _: OpsRole):
    sources_svc.delete_source(db, source_id)
    return Response(status_code=204)


@router.get("/runs")
def list_runs(
    db: DB,
    _: OpsRole,
    source_id: UUID | None = None,
    status: str | None = None,
    limit: int = Query(50, le=200),
):
    return [
        serialize_run(row, with_source=True)
        for row in sources_svc.list_runs(db, source_id=source_id, status=status, limit=limit)
    ]


@router.get("/runs/{run_id}")
def get_run(run_id: UUID, db: DB, _: OpsRole):
    return serialize_run(sources_svc.get_run(db, run_id), with_log=True, with_source=True)


@router.get("/events")
def list_events(db: DB, _: OpsRole, limit: int = Query(50, le=200)):
    return [ops_event(row) for row in sources_svc.list_events(db, limit)]

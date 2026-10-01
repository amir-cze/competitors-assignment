"""Operator use cases around sources and runs."""

from __future__ import annotations

import uuid

from sqlalchemy import select
from sqlalchemy.orm import Session, joinedload

from radar.config import get_settings
from radar.errors import NotFound
from radar.models import Competitor, HealthStatus, OpsEvent, Run, Source, utcnow
from radar.pipeline import Pipeline


def get_source(session: Session, source_id: uuid.UUID) -> Source:
    s = session.scalar(select(Source).options(joinedload(Source.competitor)).where(Source.id == source_id))
    if s is None:
        raise NotFound("Source not found")
    return s


def list_sources(session: Session) -> list[tuple[Source, list[Run]]]:
    sources = session.scalars(
        select(Source)
        .options(joinedload(Source.competitor))
        .order_by(Source.health.desc(), Source.next_run_at)
    ).all()
    out = []
    for s in sources:
        recent = session.scalars(
            select(Run).where(Run.source_id == s.id).order_by(Run.started_at.desc()).limit(12)
        ).all()
        out.append((s, list(reversed(recent))))
    return out


def update_source(session: Session, source_id: uuid.UUID, changes: dict) -> Source:
    s = get_source(session, source_id)
    was_enabled = s.enabled
    for field, value in changes.items():
        setattr(s, field, value)
    if s.enabled and not was_enabled:
        s.health = HealthStatus.new.value
        s.consecutive_failures = 0
        s.next_run_at = utcnow()
    if not s.enabled:
        s.health = HealthStatus.disabled.value
    session.flush()
    return s


def create_source(
    session: Session, competitor_id: uuid.UUID, *, kind: str, url: str, label: str | None, config: dict | None
) -> Source:
    comp = session.get(Competitor, competitor_id)
    if comp is None:
        raise NotFound("Competitor not found")
    s = Source(
        competitor_id=comp.id,
        kind=kind,
        url=url,
        label=label,
        config=config or {},
        next_run_at=utcnow(),
        interval_minutes=get_settings().page_watch_interval_minutes
        if kind == "page_watch"
        else get_settings().default_source_interval_minutes,
    )
    session.add(s)
    session.flush()
    s.competitor = comp
    return s


def delete_source(session: Session, source_id: uuid.UUID) -> None:
    s = session.get(Source, source_id)
    if s:
        session.delete(s)


def run_now(session: Session, source_id: uuid.UUID, pipeline: Pipeline) -> Run:
    get_source(session, source_id)
    return pipeline.process_source(session, source_id, trigger="manual")


def queue_run(session: Session, source_id: uuid.UUID) -> None:
    get_source(session, source_id).next_run_at = utcnow()


def reset_recipe(session: Session, source_id: uuid.UUID) -> None:
    s = get_source(session, source_id)
    cfg = dict(s.config or {})
    cfg.pop("recipe", None)
    cfg.pop("recipe_derived_at", None)
    s.config = cfg
    s.next_run_at = utcnow()


# ----------------------------------------------------------------------------- runs / events


def list_runs(session: Session, *, source_id: uuid.UUID | None, status: str | None, limit: int) -> list[Run]:
    stmt = (
        select(Run)
        .options(joinedload(Run.source).joinedload(Source.competitor))
        .order_by(Run.started_at.desc())
        .limit(limit)
    )
    if source_id:
        stmt = stmt.where(Run.source_id == source_id)
    if status:
        stmt = stmt.where(Run.status == status)
    return list(session.scalars(stmt).all())


def get_run(session: Session, run_id: uuid.UUID) -> Run:
    r = session.scalar(
        select(Run).options(joinedload(Run.source).joinedload(Source.competitor)).where(Run.id == run_id)
    )
    if r is None:
        raise NotFound("Run not found")
    return r


def list_events(session: Session, limit: int) -> list[OpsEvent]:
    return list(session.scalars(select(OpsEvent).order_by(OpsEvent.created_at.desc()).limit(limit)).all())

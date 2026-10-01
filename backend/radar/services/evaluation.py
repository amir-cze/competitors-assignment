"""Facade over radar.eval for the operator surface."""

from __future__ import annotations

import uuid

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from radar.errors import NotFound
from radar.eval import metrics
from radar.models import EvalItem, EvalRun, PromptVersion


def dashboard(session: Session) -> dict:
    prompts = {p.id: p.version for p in session.scalars(select(PromptVersion)).all()}
    golden_count = session.scalar(select(func.count()).select_from(EvalItem)) or 0
    by_origin = dict(session.execute(select(EvalItem.origin, func.count()).group_by(EvalItem.origin)).all())
    return {
        "live": metrics.live_metrics(session),
        "history": [
            {
                "id": str(r.id),
                "run_at": r.run_at.isoformat(),
                "prompt_version": prompts.get(r.prompt_version_id),
                "model": r.model,
                "n_items": r.n_items,
                "metrics": r.metrics,
                "cost_usd": r.cost_usd,
                "trigger": r.trigger,
            }
            for r in metrics.eval_history(session)
        ],
        "golden_count": int(golden_count),
        "golden_by_origin": {k: int(v) for k, v in by_origin.items()},
        "disagreements": metrics.disagreements(session),
    }


def get_eval_run(session: Session, eval_run_id: uuid.UUID) -> EvalRun:
    r = session.get(EvalRun, eval_run_id)
    if r is None:
        raise NotFound("Eval run not found")
    return r


def trigger(session: Session, evaluator: metrics.Evaluator, max_items: int | None) -> EvalRun:
    return evaluator.run(session, trigger="manual", max_items=max_items)


def golden_items(session: Session) -> list[EvalItem]:
    return list(session.scalars(select(EvalItem).order_by(EvalItem.created_at.desc())).all())


def promote(session: Session, item_id: uuid.UUID, labels: dict[str, bool] | None) -> EvalItem:
    try:
        return metrics.promote_to_golden(session, item_id, labels)
    except ValueError as exc:
        raise NotFound(str(exc)) from exc


def add_manual(
    session: Session,
    *,
    competitor_name: str,
    title: str,
    content_text: str,
    labels: dict[str, bool],
    kind: str,
) -> EvalItem:
    g = EvalItem(
        competitor_name=competitor_name,
        title=title,
        content_text=content_text,
        labels=labels,
        kind=kind,
        origin="seed",
    )
    session.add(g)
    session.flush()
    return g


def delete_golden(session: Session, golden_id: uuid.UUID) -> None:
    g = session.get(EvalItem, golden_id)
    if g:
        session.delete(g)

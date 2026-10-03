"""How do we know the output is any good?

Two complementary signals:
1. Golden-set evaluation: a labeled set of items (seeded + promoted from feedback) is re-scored with the
   active prompt on a schedule. Precision/recall per team tells us whether a prompt or model change helped.
2. Live feedback metrics: what people actually rated in the inbox and Slack, split by whether we surfaced
   the item or not. This is the number that matters in production, and it feeds few-shot calibration.
"""

from __future__ import annotations

import uuid
from datetime import timedelta

from sqlalchemy import func, select
from sqlalchemy.orm import Session, joinedload

from radar.assess.llm import BudgetExceeded
from radar.assess.prompts import active_prompt
from radar.assess.scoring import Scorer, load_context
from radar.logging import get_logger
from radar.models import Assessment, EvalItem, EvalRun, Feedback, Item, Route, Team, utcnow

log = get_logger(__name__)
SURFACED = (Route.immediate.value, Route.digest.value)


def _prf(tp: int, fp: int, fn: int, tn: int) -> dict:
    precision = tp / (tp + fp) if tp + fp else None
    recall = tp / (tp + fn) if tp + fn else None
    if precision is not None and recall is not None:
        f1 = 2 * precision * recall / (precision + recall) if precision + recall else 0.0
    else:
        f1 = None
    return {
        "tp": tp,
        "fp": fp,
        "fn": fn,
        "tn": tn,
        "precision": precision,
        "recall": recall,
        "f1": f1,
        "n": tp + fp + fn + tn,
    }


class Evaluator:
    def __init__(self, scorer: Scorer, max_items_default: int):
        self._scorer = scorer
        self._max_items = max_items_default

    def run(self, session: Session, *, trigger: str = "schedule", max_items: int | None = None) -> EvalRun:
        teams, topics = load_context(session)
        pv = active_prompt(session)
        golden = list(
            session.scalars(
                select(EvalItem).order_by(EvalItem.created_at.desc()).limit(max_items or self._max_items)
            ).all()
        )
        run = EvalRun(prompt_version_id=pv.id, model=self._scorer.model, trigger=trigger, n_items=len(golden))
        session.add(run)
        session.flush()
        if not golden or not self._scorer.available:
            run.metrics = {"error": "no golden items" if not golden else "LLM not configured"}
            return run

        counts = {t.key: {"tp": 0, "fp": 0, "fn": 0, "tn": 0} for t in teams}
        details: list[dict] = []
        total_cost = 0.0
        for g in golden:
            try:
                parsed, cost = self._scorer.score_text(
                    session,
                    competitor_name=g.competitor_name,
                    title=g.title,
                    body=g.content_text,
                    kind=g.kind,
                    teams=teams,
                    topics=topics,
                    template=pv.content,
                )
            except BudgetExceeded:
                details.append({"eval_item_id": str(g.id), "error": "budget exhausted"})
                break
            except Exception as exc:
                details.append({"eval_item_id": str(g.id), "error": str(exc)[:200]})
                continue
            total_cost += cost
            scores = {ts.team_key: ts.relevance for ts in parsed.teams}
            row = {"eval_item_id": str(g.id), "title": g.title, "competitor": g.competitor_name, "teams": {}}
            for team in teams:
                if team.key not in g.labels:
                    continue
                expected = bool(g.labels[team.key])
                score = int(scores.get(team.key, 0))
                predicted = score >= team.digest_threshold and parsed.is_substantive
                bucket = "tp" if predicted and expected else "fp" if predicted else "fn" if expected else "tn"
                counts[team.key][bucket] += 1
                row["teams"][team.key] = {
                    "expected": expected,
                    "score": score,
                    "predicted": predicted,
                    "ok": predicted == expected,
                }
            details.append(row)

        run.metrics = {k: _prf(**v) for k, v in counts.items()}
        run.details = details
        run.cost_usd = total_cost
        log.info("eval.done", n=len(golden), metrics=run.metrics, cost=round(total_cost, 4))
        return run


def live_metrics(session: Session, days: int = 30) -> dict:
    since = utcnow() - timedelta(days=days)
    out: dict = {"days": days, "teams": {}}
    for team in session.scalars(select(Team)).all():
        rows = session.execute(
            select(Feedback.verdict, Assessment.route, func.count())
            .join(
                Assessment,
                (Assessment.item_id == Feedback.item_id) & (Assessment.team_id == Feedback.team_id),
            )
            .where(Feedback.team_id == team.id, Feedback.created_at >= since)
            .group_by(Feedback.verdict, Assessment.route)
        ).all()
        surfaced_useful = surfaced_not = hidden_useful = hidden_not = 0
        for verdict, route, n in rows:
            surfaced = route in SURFACED
            if verdict == "useful" and surfaced:
                surfaced_useful += n
            elif verdict == "not_useful" and surfaced:
                surfaced_not += n
            elif verdict == "useful":
                hidden_useful += n
            else:
                hidden_not += n
        total = surfaced_useful + surfaced_not + hidden_useful + hidden_not
        base = (
            select(func.count())
            .select_from(Assessment)
            .where(Assessment.team_id == team.id, Assessment.created_at >= since)
        )
        surfaced_total = session.scalar(base.where(Assessment.route.in_(SURFACED))) or 0
        assessed_total = session.scalar(base) or 0
        out["teams"][team.key] = {
            "name": team.name,
            "feedback_count": total,
            "surfaced_precision": surfaced_useful / (surfaced_useful + surfaced_not)
            if surfaced_useful + surfaced_not
            else None,
            "missed_useful": hidden_useful,
            "recall_proxy": surfaced_useful / (surfaced_useful + hidden_useful)
            if surfaced_useful + hidden_useful
            else None,
            "surfaced_total": surfaced_total,
            "assessed_total": assessed_total,
            "surface_rate": surfaced_total / assessed_total if assessed_total else None,
        }
    return out


def disagreements(session: Session, limit: int = 50) -> list[dict]:
    rows = session.execute(
        select(Feedback, Assessment, Item)
        .join(Assessment, (Assessment.item_id == Feedback.item_id) & (Assessment.team_id == Feedback.team_id))
        .join(Item, Item.id == Feedback.item_id)
        .options(joinedload(Item.competitor), joinedload(Feedback.team))
        .order_by(Feedback.created_at.desc())
        .limit(limit * 3)
    ).all()
    out = []
    for f, a, i in rows:
        surfaced = a.route in SURFACED
        if (f.verdict == "useful") == surfaced:
            continue
        out.append(
            {
                "feedback_id": str(f.id),
                "item_id": str(i.id),
                "team_key": f.team.key,
                "team_name": f.team.name,
                "headline": i.headline or i.title,
                "competitor": i.competitor.name,
                "verdict": f.verdict,
                "reason": f.reason,
                "relevance": a.relevance,
                "route": a.route,
                "kind": "missed" if f.verdict == "useful" else "false_alarm",
                "promoted": f.promoted_to_golden,
                "created_at": f.created_at.isoformat(),
            }
        )
        if len(out) >= limit:
            break
    return out


def promote_to_golden(
    session: Session, item_id: uuid.UUID, labels: dict[str, bool] | None = None
) -> EvalItem:
    item = session.get(Item, item_id)
    if item is None:
        raise ValueError("item not found")
    existing = session.scalar(select(EvalItem).where(EvalItem.item_id == item_id))
    if labels is None:
        labels = {f.team.key: f.verdict == "useful" for f in item.feedback}
    if existing:
        merged = dict(existing.labels)
        merged.update(labels)
        existing.labels = merged
        golden = existing
    else:
        golden = EvalItem(
            item_id=item.id,
            competitor_name=item.competitor.name,
            title=item.headline or item.title,
            content_text=item.content_text[:8000],
            kind=item.kind,
            labels=labels,
            origin="feedback",
        )
        session.add(golden)
    for f in item.feedback:
        if f.team.key in labels:
            f.promoted_to_golden = True
    session.flush()
    return golden


def withdraw_from_golden(session: Session, item_id: uuid.UUID, team_key: str) -> bool:
    """Undo one team's feedback-derived label. Only touches golden items that feedback created;
    seeded and hand-written examples are the operator's and are never changed by a business click.
    Returns True if a label was removed."""
    golden = session.scalar(select(EvalItem).where(EvalItem.item_id == item_id, EvalItem.origin == "feedback"))
    if golden is None or team_key not in golden.labels:
        return False
    labels = dict(golden.labels)
    labels.pop(team_key)
    if labels:
        golden.labels = labels
    else:
        session.delete(golden)
    session.flush()
    return True


def eval_history(session: Session, limit: int = 20) -> list[EvalRun]:
    return list(session.scalars(select(EvalRun).order_by(EvalRun.run_at.desc()).limit(limit)).all())

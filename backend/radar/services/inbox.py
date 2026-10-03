"""Read models for the business surface (overview, inbox, item detail) and the feedback use case."""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import datetime, timedelta

from sqlalchemy import Select, func, select
from sqlalchemy.orm import Session, joinedload

from radar.errors import NotFound
from radar.eval.metrics import promote_to_golden, withdraw_from_golden
from radar.models import Assessment, Competitor, Delivery, Feedback, Item, Route, SystemState, Team, utcnow
from radar.services import competitors as competitors_svc
from radar.services.teams import get_team, list_teams

SURFACED_ROUTES = (Route.immediate.value, Route.digest.value)


def _with_card_relations(stmt: Select) -> Select:
    return stmt.options(
        joinedload(Item.competitor),
        joinedload(Item.assessments).joinedload(Assessment.team),
        joinedload(Item.feedback).joinedload(Feedback.team),
    )


# ----------------------------------------------------------------------------- overview


@dataclass
class TeamHighlights:
    """Scoreboard for one team: how much we interrupted them this week, and how much is queued for the digest."""

    team: Team
    surfaced_7d: int
    immediate_7d: int
    digest_7d: int


@dataclass
class Overview:
    teams: list[TeamHighlights]
    highlights: list[Item]  # each item once, with all its assessments loaded; the UI shows team chips
    competitor_count: int
    items_7d: int
    attention: list[str]
    monitoring_running: bool
    last_check: datetime | None
    recent_changes: list[Item] = field(default_factory=list)


def worker_last_seen(session: Session) -> datetime | None:
    hb = session.get(SystemState, "worker_heartbeat")
    return datetime.fromisoformat(hb.value["at"]) if hb and hb.value.get("at") else None


def overview(session: Session, *, days: int = 7) -> Overview:
    since = utcnow() - timedelta(days=days)
    scoreboard: list[TeamHighlights] = []
    for team in list_teams(session):
        by_route = dict(
            session.execute(
                select(Assessment.route, func.count())
                .where(
                    Assessment.team_id == team.id,
                    Assessment.created_at >= since,
                    Assessment.route.in_(SURFACED_ROUTES),
                )
                .group_by(Assessment.route)
            ).all()
        )
        immediate = int(by_route.get(Route.immediate.value, 0))
        digest = int(by_route.get(Route.digest.value, 0))
        scoreboard.append(
            TeamHighlights(team=team, surfaced_7d=immediate + digest, immediate_7d=immediate, digest_7d=digest)
        )

    # The week's items, each once, strongest first. Which teams they concern is read off the assessments.
    strongest = (
        select(Assessment.item_id, func.max(Assessment.relevance).label("top"))
        .where(Assessment.created_at >= since, Assessment.route.in_(SURFACED_ROUTES))
        .group_by(Assessment.item_id)
        .subquery()
    )
    highlights = (
        session.scalars(
            _with_card_relations(select(Item).join(strongest, strongest.c.item_id == Item.id))
            .order_by(strongest.c.top.desc(), Item.first_seen_at.desc())
            .limit(8)
        )
        .unique()
        .all()
    )

    comps = competitors_svc.list_competitors(session)
    attention = [c.name for c in comps if competitors_svc.health_rollup(c.sources) == "attention"]
    items_7d = session.scalar(select(func.count()).select_from(Item).where(Item.first_seen_at >= since)) or 0
    last_seen = worker_last_seen(session)
    recent_changes = (
        session.scalars(
            select(Item)
            .options(joinedload(Item.competitor))
            .where(Item.kind == "page_change", Item.first_seen_at >= since)
            .order_by(Item.first_seen_at.desc())
            .limit(5)
        )
        .unique()
        .all()
    )
    return Overview(
        teams=scoreboard,
        highlights=list(highlights),
        competitor_count=len(comps),
        items_7d=int(items_7d),
        attention=attention,
        monitoring_running=bool(last_seen and utcnow() - last_seen < timedelta(minutes=5)),
        last_check=last_seen,
        recent_changes=list(recent_changes),
    )


# ----------------------------------------------------------------------------- inbox


@dataclass
class InboxFilters:
    view: str = "surfaced"  # surfaced | all | changes | starred
    competitor_id: uuid.UUID | None = None
    category: str | None = None
    days: int = 30
    query: str | None = None
    limit: int = 50
    offset: int = 0


@dataclass
class InboxResult:
    team: Team
    items: list[Item]
    total: int
    counts: dict[str, int]


def inbox(session: Session, team_key: str, filters: InboxFilters) -> InboxResult:
    team = get_team(session, team_key)
    since = utcnow() - timedelta(days=filters.days)
    stmt = (
        select(Item)
        .join(Assessment, (Assessment.item_id == Item.id) & (Assessment.team_id == team.id))
        .where(Item.first_seen_at >= since)
    )

    if filters.view == "surfaced":
        stmt = stmt.where(Assessment.route.in_(SURFACED_ROUTES))
    elif filters.view == "changes":
        stmt = stmt.where(Item.kind == "page_change")
    elif filters.view == "starred":
        stmt = stmt.join(Feedback, (Feedback.item_id == Item.id) & (Feedback.team_id == team.id)).where(
            Feedback.verdict == "useful"
        )
    if filters.competitor_id:
        stmt = stmt.where(Item.competitor_id == filters.competitor_id)
    if filters.category:
        stmt = stmt.where(Assessment.category == filters.category)
    if filters.query:
        like = f"%{filters.query.strip()}%"
        stmt = stmt.where(Item.title.ilike(like) | Item.headline.ilike(like) | Item.summary.ilike(like))

    total = session.scalar(select(func.count()).select_from(stmt.subquery())) or 0
    rows = (
        session.scalars(
            _with_card_relations(stmt)
            .order_by(Assessment.relevance.desc(), Item.first_seen_at.desc())
            .limit(filters.limit)
            .offset(filters.offset)
        )
        .unique()
        .all()
    )

    counts_rows = session.execute(
        select(Assessment.route, func.count())
        .join(Item, Item.id == Assessment.item_id)
        .where(Assessment.team_id == team.id, Item.first_seen_at >= since)
        .group_by(Assessment.route)
    ).all()
    counts = {route: int(n) for route, n in counts_rows}
    counts["changes"] = int(
        session.scalar(
            select(func.count())
            .select_from(Item)
            .join(Assessment, (Assessment.item_id == Item.id) & (Assessment.team_id == team.id))
            .where(Item.kind == "page_change", Item.first_seen_at >= since)
        )
        or 0
    )
    return InboxResult(team=team, items=list(rows), total=int(total), counts=counts)


# ----------------------------------------------------------------------------- item detail + feedback


def get_item(session: Session, item_id: uuid.UUID) -> Item:
    item = session.scalar(
        _with_card_relations(select(Item)).options(joinedload(Item.sources)).where(Item.id == item_id)
    )
    if item is None:
        raise NotFound("Item not found")
    return item


def deliveries_for(session: Session, item_id: uuid.UUID) -> list[Delivery]:
    return list(session.scalars(select(Delivery).where(Delivery.item_id == item_id)).all())


def give_feedback(
    session: Session, item_id: uuid.UUID, *, team_key: str, verdict: str, reason: str | None
) -> Feedback:
    item = session.get(Item, item_id)
    if item is None:
        raise NotFound("Item not found")
    team = get_team(session, team_key)
    fb = session.scalar(select(Feedback).where(Feedback.item_id == item.id, Feedback.team_id == team.id))
    if fb is None:
        fb = Feedback(item_id=item.id, team_id=team.id, verdict=verdict, reason=reason)
        session.add(fb)
    else:
        if fb.promoted_to_golden:
            # A changed mind must not leave the old label in the test set.
            withdraw_from_golden(session, item.id, team.key)
        fb.verdict = verdict
        fb.reason = reason
        fb.created_at = utcnow()
        fb.promoted_to_golden = False
    session.flush()

    # A disagreement with the model is the most informative label we can get: promote it to the golden set.
    # Agreements stay as calibration examples and metrics only; they would not test anything.
    assessment = next((a for a in item.assessments if a.team_id == team.id), None)
    if assessment is not None:
        surfaced = assessment.route in SURFACED_ROUTES
        if (verdict == "useful") != surfaced:
            promote_to_golden(session, item.id, {team.key: verdict == "useful"})
    fb.team = team
    return fb


def clear_feedback(session: Session, item_id: uuid.UUID, team_key: str) -> None:
    """Undo a vote. If the vote had become a golden label, that label goes with it."""
    team = get_team(session, team_key)
    fb = session.scalar(select(Feedback).where(Feedback.item_id == item_id, Feedback.team_id == team.id))
    if fb is None:
        return
    if fb.promoted_to_golden:
        withdraw_from_golden(session, item_id, team.key)
    session.delete(fb)


def competitor_names(session: Session) -> dict[uuid.UUID, str]:
    return dict(session.execute(select(Competitor.id, Competitor.name)).all())

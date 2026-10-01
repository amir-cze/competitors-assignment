"""Per-team inbox, item detail, and the feedback loop."""

from uuid import UUID

from fastapi import APIRouter, Query, Response

from radar.api.deps import DB, BusinessRole
from radar.api.schemas import FeedbackIn, FeedbackOut, InboxPage, ItemDetail
from radar.api.serializers.inbox import feedback as serialize_feedback
from radar.api.serializers.inbox import item_card, item_detail
from radar.api.serializers.teams import team as serialize_team
from radar.services import inbox as inbox_svc

router = APIRouter(tags=["inbox"])


@router.get("/inbox/{team_key}", response_model=InboxPage)
def inbox(
    team_key: str,
    db: DB,
    _: BusinessRole,
    view: str = Query("surfaced", pattern="^(surfaced|all|changes|starred)$"),
    competitor_id: UUID | None = None,
    category: str | None = None,
    days: int = Query(30, ge=1, le=365),
    q: str | None = None,
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
):
    result = inbox_svc.inbox(
        db,
        team_key,
        inbox_svc.InboxFilters(
            view=view,
            competitor_id=competitor_id,
            category=category,
            days=days,
            query=q,
            limit=limit,
            offset=offset,
        ),
    )
    return InboxPage(
        team=serialize_team(result.team),
        items=[item_card(item, result.team) for item in result.items],
        total=result.total,
        counts=result.counts,
    )


@router.get("/items/{item_id}", response_model=ItemDetail)
def get_item(item_id: UUID, db: DB, _: BusinessRole):
    item = inbox_svc.get_item(db, item_id)
    return item_detail(item, inbox_svc.deliveries_for(db, item.id))


@router.post("/items/{item_id}/feedback", response_model=FeedbackOut)
def give_feedback(item_id: UUID, body: FeedbackIn, db: DB, _: BusinessRole):
    row = inbox_svc.give_feedback(db, item_id, team_key=body.team_key, verdict=body.verdict, reason=body.reason)
    return serialize_feedback(row)


@router.delete("/items/{item_id}/feedback/{team_key}", status_code=204)
def clear_feedback(item_id: UUID, team_key: str, db: DB, _: BusinessRole):
    inbox_svc.clear_feedback(db, item_id, team_key)
    return Response(status_code=204)

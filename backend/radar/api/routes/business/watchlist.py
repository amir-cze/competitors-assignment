"""The watchlist: add a competitor from a URL, watch a page, mute, remove."""

from uuid import UUID

from fastapi import APIRouter, Response
from sqlalchemy.orm import Session

from radar.api.deps import DB, BusinessRole, Container
from radar.api.schemas import CompetitorIn, CompetitorOut, CompetitorPatch, DiscoverIn, WatchPageIn
from radar.api.serializers.competitors import competitor as serialize_competitor
from radar.models import Competitor
from radar.services import competitors as competitors_svc

router = APIRouter(prefix="/competitors", tags=["watchlist"])


def _out(db: Session, row: Competitor) -> CompetitorOut:
    return serialize_competitor(row, competitors_svc.stats_for(db, row))


@router.get("", response_model=list[CompetitorOut])
def list_competitors(db: DB, _: BusinessRole):
    return [_out(db, row) for row in competitors_svc.list_competitors(db)]


@router.post("/discover")
def discover_sources(body: DiscoverIn, deps: Container, _: BusinessRole):
    """Inspect a homepage and propose sources. Nothing is saved until the user confirms."""
    return competitors_svc.discover_for(body.url, deps.fetcher).to_dict()


@router.post("", response_model=CompetitorOut, status_code=201)
def create_competitor(body: CompetitorIn, db: DB, _: BusinessRole):
    row = competitors_svc.create_competitor(
        db,
        name=body.name,
        homepage_url=body.homepage_url,
        notes=body.notes,
        sources=[source.model_dump() for source in body.sources],
    )
    return _out(db, row)


@router.patch("/{competitor_id}", response_model=CompetitorOut)
def update_competitor(competitor_id: UUID, body: CompetitorPatch, db: DB, _: BusinessRole):
    return _out(db, competitors_svc.update_competitor(db, competitor_id, body.model_dump(exclude_unset=True)))


@router.delete("/{competitor_id}", status_code=204)
def delete_competitor(competitor_id: UUID, db: DB, _: BusinessRole):
    competitors_svc.delete_competitor(db, competitor_id)
    return Response(status_code=204)


@router.post("/{competitor_id}/watch-page", response_model=CompetitorOut, status_code=201)
def watch_page(competitor_id: UUID, body: WatchPageIn, db: DB, _: BusinessRole):
    return _out(db, competitors_svc.add_watch_page(db, competitor_id, url=body.url, label=body.label))


@router.post("/{competitor_id}/check-now")
def check_now(competitor_id: UUID, db: DB, _: BusinessRole):
    return {"ok": True, "queued": competitors_svc.check_now(db, competitor_id)}

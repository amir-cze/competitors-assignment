"""Team lenses, alert thresholds, Slack connection and digests."""

from fastapi import APIRouter

from radar.api.deps import DB, BusinessRole, Container
from radar.api.schemas import TeamOut, TeamPatch
from radar.api.serializers.teams import team as serialize_team
from radar.deliver import digest as digest_svc
from radar.services import teams as teams_svc

router = APIRouter(prefix="/teams", tags=["teams"])


@router.get("", response_model=list[TeamOut])
def list_teams(db: DB, _: BusinessRole):
    return [serialize_team(row) for row in teams_svc.list_teams(db)]


@router.patch("/{key}", response_model=TeamOut)
def update_team(key: str, body: TeamPatch, db: DB, _: BusinessRole):
    changes = body.model_dump(exclude_unset=True)
    webhook = changes.pop("slack_webhook", None)
    return serialize_team(teams_svc.update_team(db, key, changes, slack_webhook=webhook))


@router.post("/{key}/slack/test")
def test_slack(key: str, db: DB, deps: Container, _: BusinessRole):
    teams_svc.send_slack_test(db, key, deps.deliverer)
    return {"ok": True}


@router.get("/{key}/digest/preview")
def digest_preview(key: str, db: DB, _: BusinessRole):
    return digest_svc.preview(db, teams_svc.get_team(db, key))


@router.post("/{key}/digest/send")
def digest_send_now(key: str, db: DB, deps: Container, _: BusinessRole):
    return deps.digests.send(db, teams_svc.get_team(db, key), force=True)

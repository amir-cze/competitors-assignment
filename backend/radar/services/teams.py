from __future__ import annotations

import uuid

from sqlalchemy import func, select
from sqlalchemy.orm import Session, joinedload

from radar.deliver.slack import SlackDeliverer
from radar.errors import Conflict, InvalidInput, NotFound, UpstreamFailure
from radar.models import Team, Topic
from radar.security import decrypt, encrypt

SLACK_WEBHOOK_PREFIX = "https://hooks.slack.com/"


def get_team(session: Session, key: str) -> Team:
    team = session.scalar(select(Team).options(joinedload(Team.topics)).where(Team.key == key))
    if team is None:
        raise NotFound("Unknown team")
    return team


def list_teams(session: Session) -> list[Team]:
    return list(
        session.scalars(select(Team).options(joinedload(Team.topics)).order_by(Team.created_at))
        .unique()
        .all()
    )


def update_team(session: Session, key: str, changes: dict, *, slack_webhook: str | None = None) -> Team:
    """`changes` holds plain column updates; `slack_webhook` is handled separately because it is encrypted."""
    team = get_team(session, key)
    if slack_webhook is not None:
        if slack_webhook.strip() == "":
            team.slack_webhook_encrypted = None
            team.slack_enabled = False
        else:
            if not slack_webhook.startswith(SLACK_WEBHOOK_PREFIX):
                raise InvalidInput(
                    f"That does not look like a Slack incoming webhook URL (it should start with {SLACK_WEBHOOK_PREFIX})."
                )
            team.slack_webhook_encrypted = encrypt(slack_webhook.strip())
    for field, value in changes.items():
        setattr(team, field, value)
    # Invariants the UI should never be able to break.
    if team.digest_threshold > team.immediate_threshold:
        team.digest_threshold = team.immediate_threshold
    if team.slack_enabled and not team.slack_webhook_encrypted:
        raise InvalidInput("Add a Slack webhook before turning Slack alerts on.")
    session.flush()
    return team


def team_webhook_plain(team: Team) -> str | None:
    return decrypt(team.slack_webhook_encrypted) if team.slack_webhook_encrypted else None


def send_slack_test(session: Session, key: str, deliverer: SlackDeliverer) -> None:
    team = get_team(session, key)
    webhook = team_webhook_plain(team)
    if not webhook:
        raise InvalidInput("No Slack webhook saved for this team yet.")
    try:
        deliverer.send_test(team, webhook)
    except Exception as exc:
        raise UpstreamFailure(f"Slack did not accept the message: {exc}") from exc


# ----------------------------------------------------------------------------- topics


def list_topics(session: Session) -> list[Topic]:
    return list(
        session.scalars(select(Topic).options(joinedload(Topic.team)).order_by(Topic.created_at)).all()
    )


def create_topic(session: Session, *, name: str, description: str | None, team_key: str | None) -> Topic:
    team = get_team(session, team_key) if team_key else None
    team_id = team.id if team else None
    duplicate = session.scalar(
        select(Topic).where(func.lower(Topic.name) == name.strip().lower(), Topic.team_id == team_id)
    )
    if duplicate:
        raise Conflict("That topic is already being watched.")
    topic = Topic(name=name.strip(), description=description, team_id=team_id)
    session.add(topic)
    session.flush()
    topic.team = team
    return topic


def delete_topic(session: Session, topic_id: uuid.UUID) -> None:
    topic = session.get(Topic, topic_id)
    if topic:
        session.delete(topic)

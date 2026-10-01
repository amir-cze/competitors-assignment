"""Daily digest per team: everything routed to `digest` since the last digest, in one Slack message."""

from __future__ import annotations

from datetime import datetime, timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session, joinedload

from radar.deliver.notifier import NotifyError, NotifyRejected
from radar.deliver.slack import SlackDeliverer, build_digest_blocks, team_webhook
from radar.logging import get_logger
from radar.models import Assessment, Delivery, DeliveryStatus, Item, Route, Team, utcnow

log = get_logger(__name__)


def digest_rows(session: Session, team: Team, since: datetime | None = None) -> list[tuple[Item, Assessment]]:
    since = since or team.last_digest_at or (utcnow() - timedelta(days=1))
    rows = session.execute(
        select(Item, Assessment)
        .join(Assessment, Assessment.item_id == Item.id)
        .options(joinedload(Item.competitor))
        .where(
            Assessment.team_id == team.id,
            Assessment.route == Route.digest.value,
            Assessment.created_at >= since,
        )
        .order_by(Assessment.relevance.desc())
    ).all()
    return [(i, a) for i, a in rows]


def is_digest_due(team: Team, now: datetime | None = None) -> bool:
    now = now or utcnow()
    if now.hour != team.digest_hour_utc:
        return False
    if team.last_digest_at and team.last_digest_at.date() == now.date():
        return False
    return True


class DigestSender:
    def __init__(self, deliverer: SlackDeliverer, settings):
        self._deliverer = deliverer
        self._settings = settings

    def send(self, session: Session, team: Team, *, force: bool = False) -> dict:
        now = utcnow()
        if not force and not is_digest_due(team, now):
            return {"team": team.key, "status": "not_due"}
        rows = digest_rows(session, team)
        key = f"digest:{team.id}:{now.date().isoformat()}"
        if not force and session.scalar(select(Delivery).where(Delivery.dedupe_key == key)):
            return {"team": team.key, "status": "already_sent"}
        if force:
            key = f"{key}:{int(now.timestamp())}"

        team.last_digest_at = now
        if not rows:
            return {"team": team.key, "status": "empty"}

        webhook = team_webhook(team)
        delivery = Delivery(
            item_id=None,
            team_id=team.id,
            channel="slack_digest",
            dedupe_key=key,
            payload={"count": len(rows)},
        )
        session.add(delivery)
        if not webhook:
            delivery.status = DeliveryStatus.skipped.value
            delivery.error = "Slack not configured"
            return {"team": team.key, "status": "skipped_no_slack", "count": len(rows)}
        payload = {
            "text": f"Radar digest for {team.name}: {len(rows)} items",
            "blocks": build_digest_blocks(self._settings, team, rows),
        }
        delivery.attempts += 1
        try:
            self._deliverer.post(webhook, payload)
            delivery.status = DeliveryStatus.sent.value
            delivery.sent_at = utcnow()
        except (NotifyError, NotifyRejected) as exc:
            delivery.status = DeliveryStatus.failed.value
            delivery.error = str(exc)
            log.warning("digest.failed", team=team.key, error=str(exc))
            return {"team": team.key, "status": "failed", "error": str(exc)}
        return {"team": team.key, "status": "sent", "count": len(rows)}

    def run_due(self, session: Session) -> list[dict]:
        return [self.send(session, team) for team in session.scalars(select(Team)).all()]


def preview(session: Session, team: Team) -> dict:
    rows = digest_rows(session, team, since=utcnow() - timedelta(days=1))
    return {
        "team": team.key,
        "since": (utcnow() - timedelta(days=1)).isoformat(),
        "next_send_utc_hour": team.digest_hour_utc,
        "items": [
            {
                "item_id": str(i.id),
                "headline": i.headline or i.title,
                "competitor": i.competitor.name,
                "relevance": a.relevance,
                "why": a.why,
                "category": a.category,
            }
            for i, a in rows
        ],
    }

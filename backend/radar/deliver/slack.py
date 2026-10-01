"""Slack message composition and idempotent delivery through the `deliveries` table."""

from __future__ import annotations

import uuid

from sqlalchemy import select
from sqlalchemy.orm import Session

from radar.assess.prompts import CATEGORY_LABELS
from radar.config import Settings
from radar.deliver.notifier import Notifier, NotifyError, NotifyRejected
from radar.logging import get_logger
from radar.models import Assessment, Delivery, DeliveryStatus, Item, Team, utcnow
from radar.security import decrypt

log = get_logger(__name__)


# --------------------------------------------------------------------------- message composition (pure)


def item_url(settings: Settings, item_id: uuid.UUID) -> str:
    return f"{settings.public_base_url.rstrip('/')}/items/{item_id}"


def feedback_url(settings: Settings, item_id: uuid.UUID, team_key: str, verdict: str) -> str:
    return f"{item_url(settings, item_id)}?team={team_key}&verdict={verdict}"


def _score_emoji(score: int) -> str:
    if score >= 90:
        return ":rotating_light:"
    if score >= 75:
        return ":large_orange_circle:"
    return ":large_yellow_circle:"


def build_immediate_blocks(settings: Settings, item: Item, assessment: Assessment, team: Team) -> list[dict]:
    category = CATEGORY_LABELS.get(assessment.category, assessment.category)
    kind = "Page change" if item.kind == "page_change" else "New"
    title = item.headline or item.title
    blocks: list[dict] = [
        {
            "type": "header",
            "text": {"type": "plain_text", "text": f"{item.competitor.name}: {title}"[:150], "emoji": True},
        },
        {
            "type": "context",
            "elements": [
                {
                    "type": "mrkdwn",
                    "text": f"{_score_emoji(assessment.relevance)} *{assessment.relevance}/100 for {team.name}*  ·  {kind}  ·  {category}",
                }
            ],
        },
        {"type": "section", "text": {"type": "mrkdwn", "text": f"*Why it matters:* {assessment.why}"}},
    ]
    if assessment.evidence_quote:
        blocks.append(
            {"type": "section", "text": {"type": "mrkdwn", "text": f"> {assessment.evidence_quote[:300]}"}}
        )
    if assessment.topics_matched:
        blocks.append(
            {
                "type": "context",
                "elements": [
                    {
                        "type": "mrkdwn",
                        "text": "Topics: " + ", ".join(f"`{t}`" for t in assessment.topics_matched[:6]),
                    }
                ],
            }
        )
    blocks.append(
        {
            "type": "actions",
            "elements": [
                {
                    "type": "button",
                    "text": {"type": "plain_text", "text": "Open source"},
                    "url": item.canonical_url,
                },
                {
                    "type": "button",
                    "text": {"type": "plain_text", "text": "Details in Radar"},
                    "url": item_url(settings, item.id),
                },
                {
                    "type": "button",
                    "text": {"type": "plain_text", "text": "👍 Useful"},
                    "style": "primary",
                    "url": feedback_url(settings, item.id, team.key, "useful"),
                },
                {
                    "type": "button",
                    "text": {"type": "plain_text", "text": "👎 Not useful"},
                    "url": feedback_url(settings, item.id, team.key, "not_useful"),
                },
            ],
        }
    )
    return blocks


def build_digest_blocks(settings: Settings, team: Team, rows: list[tuple[Item, Assessment]]) -> list[dict]:
    plural = "s" if len(rows) != 1 else ""
    blocks: list[dict] = [
        {
            "type": "header",
            "text": {
                "type": "plain_text",
                "text": f"Radar digest for {team.name}: {len(rows)} item{plural}",
                "emoji": True,
            },
        },
    ]
    for item, a in rows[:15]:
        category = CATEGORY_LABELS.get(a.category, a.category)
        blocks.append(
            {
                "type": "section",
                "text": {
                    "type": "mrkdwn",
                    "text": f"*<{item_url(settings, item.id)}|{item.headline or item.title}>*  ·  {item.competitor.name}  ·  {a.relevance}/100  ·  {category}\n{a.why}",
                },
            }
        )
    if len(rows) > 15:
        blocks.append(
            {
                "type": "context",
                "elements": [
                    {
                        "type": "mrkdwn",
                        "text": f"…and {len(rows) - 15} more in the <{settings.public_base_url}/inbox/{team.key}|Radar inbox>.",
                    }
                ],
            }
        )
    blocks.append(
        {
            "type": "context",
            "elements": [{"type": "mrkdwn", "text": "Rate items in Radar so we learn what you find useful."}],
        }
    )
    return blocks


def build_test_message(team: Team) -> dict:
    return {
        "text": f"Radar is connected to the {team.name} channel.",
        "blocks": [
            {
                "type": "section",
                "text": {
                    "type": "mrkdwn",
                    "text": f":white_check_mark: *Radar is connected.* Important competitor news for *{team.name}* will land here (score ≥ {team.immediate_threshold}). Lower-priority items go to the daily digest.",
                },
            }
        ],
    }


def team_webhook(team: Team) -> str | None:
    if not team.slack_enabled or not team.slack_webhook_encrypted:
        return None
    return decrypt(team.slack_webhook_encrypted)


# --------------------------------------------------------------------------- delivery


class SlackDeliverer:
    """Owns the deliveries table semantics: one row per (item, team, channel), never double-post."""

    def __init__(self, notifier: Notifier, settings: Settings):
        self._notifier = notifier
        self._settings = settings

    def enqueue_immediate(self, session: Session, item: Item, assessment: Assessment, team: Team) -> Delivery:
        key = f"{item.id}:{team.id}:slack_immediate"
        existing = session.scalar(select(Delivery).where(Delivery.dedupe_key == key))
        if existing:
            return existing
        delivery = Delivery(item_id=item.id, team_id=team.id, channel="slack_immediate", dedupe_key=key)
        if not team_webhook(team):
            delivery.status = DeliveryStatus.skipped.value
            delivery.error = "Slack not configured for this team; item is in the inbox."
        else:
            delivery.payload = {
                "blocks": build_immediate_blocks(self._settings, item, assessment, team),
                "text": f"{item.competitor.name}: {item.headline or item.title}",
            }
        session.add(delivery)
        session.flush()
        return delivery

    def send(self, session: Session, delivery: Delivery, team: Team) -> bool:
        if delivery.status == DeliveryStatus.sent.value:
            return True
        webhook = team_webhook(team)
        if not webhook or not delivery.payload:
            delivery.status = DeliveryStatus.skipped.value
            return False
        delivery.attempts += 1
        try:
            self._notifier.post(webhook, delivery.payload)
        except NotifyRejected as exc:
            delivery.status = DeliveryStatus.failed.value
            delivery.error = str(exc)
            log.warning("slack.rejected", team=team.key, error=str(exc))
            return False
        except NotifyError as exc:
            delivery.status = (
                DeliveryStatus.failed.value if delivery.attempts >= 5 else DeliveryStatus.pending.value
            )
            delivery.error = str(exc)
            log.warning("slack.retry_later", team=team.key, error=str(exc), attempts=delivery.attempts)
            return False
        delivery.status = DeliveryStatus.sent.value
        delivery.sent_at = utcnow()
        delivery.error = None
        return True

    def retry_pending(self, session: Session, limit: int = 20) -> int:
        rows = session.execute(
            select(Delivery, Team)
            .join(Team, Team.id == Delivery.team_id)
            .where(Delivery.status == DeliveryStatus.pending.value, Delivery.attempts > 0)
            .limit(limit)
        ).all()
        return sum(1 for delivery, team in rows if self.send(session, delivery, team))

    def post(self, webhook_url: str, payload: dict) -> None:
        """Direct post for one-off messages (digests, tests). Raises NotifyError / NotifyRejected."""
        self._notifier.post(webhook_url, payload)

    def send_test(self, team: Team, webhook_url: str) -> None:
        self.post(webhook_url, build_test_message(team))

    def notify_ops(self, text: str, *, level: str = "warn") -> None:
        """Operator alerts. Silent when no ops webhook is configured; never raises."""
        webhook = self._settings.ops_slack_webhook
        if not webhook:
            return
        icon = {"info": ":information_source:", "warn": ":warning:", "error": ":x:"}.get(level, ":warning:")
        try:
            self._notifier.post(webhook, {"text": f"{icon} Radar: {text}"})
        except Exception as exc:
            log.warning("ops_slack.failed", error=str(exc))

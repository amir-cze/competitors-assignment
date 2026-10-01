from __future__ import annotations

import uuid

from sqlalchemy.orm import Session

from radar.deliver.slack import SlackDeliverer
from radar.logging import get_logger
from radar.models import OpsEvent

log = get_logger(__name__)


def record_event(
    session: Session,
    kind: str,
    message: str,
    *,
    level: str = "info",
    source_id: uuid.UUID | None = None,
    data: dict | None = None,
    alert_via: SlackDeliverer | None = None,
) -> OpsEvent:
    """Persist an operator-facing event; optionally push it to the ops Slack channel."""
    event = OpsEvent(kind=kind, message=message, level=level, source_id=source_id, data=data)
    session.add(event)
    log.info("ops.event", kind=kind, level=level, message=message)
    if alert_via is not None:
        alert_via.notify_ops(message, level=level)
    return event

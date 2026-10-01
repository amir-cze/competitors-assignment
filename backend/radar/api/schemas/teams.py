from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel, Field

from radar.api.schemas.topics import TopicOut


class TeamOut(BaseModel):
    id: uuid.UUID
    key: str
    name: str
    lens: str
    slack_enabled: bool
    slack_webhook_masked: str | None
    immediate_threshold: int
    digest_threshold: int
    digest_hour_utc: int
    last_digest_at: datetime | None
    topics: list[TopicOut] = []


class TeamPatch(BaseModel):
    name: str | None = Field(default=None, max_length=64)
    lens: str | None = Field(default=None, max_length=4000)
    slack_enabled: bool | None = None
    slack_webhook: str | None = Field(default=None, description="Set to empty string to clear")
    immediate_threshold: int | None = Field(default=None, ge=0, le=100)
    digest_threshold: int | None = Field(default=None, ge=0, le=100)
    digest_hour_utc: int | None = Field(default=None, ge=0, le=23)

from __future__ import annotations

import uuid

from pydantic import BaseModel, Field


class TopicOut(BaseModel):
    id: uuid.UUID
    team_id: uuid.UUID | None
    team_key: str | None
    name: str
    description: str | None


class TopicIn(BaseModel):
    name: str = Field(min_length=2, max_length=120)
    description: str | None = Field(default=None, max_length=500)
    team_key: str | None = None

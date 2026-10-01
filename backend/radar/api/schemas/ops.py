from __future__ import annotations

import uuid
from typing import Literal

from pydantic import BaseModel, Field


class SourcePatch(BaseModel):
    enabled: bool | None = None
    interval_minutes: int | None = Field(default=None, ge=5, le=24 * 60)
    requires_js: bool | None = None
    label: str | None = None
    config: dict | None = None


class PromptIn(BaseModel):
    content: str = Field(min_length=50)
    notes: str | None = None


class GoldenIn(BaseModel):
    item_id: uuid.UUID
    labels: dict[str, bool] | None = None


class GoldenManualIn(BaseModel):
    competitor_name: str
    title: str
    content_text: str
    labels: dict[str, bool]
    kind: Literal["post", "page_change"] = "post"

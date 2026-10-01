from __future__ import annotations

import uuid
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field


class DiscoverIn(BaseModel):
    url: str = Field(min_length=4)


class SourceIn(BaseModel):
    kind: Literal["feed", "sitemap", "html_list", "page_watch"]
    url: str
    label: str | None = None
    config: dict = Field(default_factory=dict)


class CompetitorIn(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    homepage_url: str
    notes: str | None = None
    sources: list[SourceIn] = Field(default_factory=list)


class CompetitorPatch(BaseModel):
    name: str | None = None
    notes: str | None = None
    muted: bool | None = None


class WatchPageIn(BaseModel):
    url: str
    label: str | None = None


class SourceSummary(BaseModel):
    id: uuid.UUID
    kind: str
    url: str
    label: str | None
    enabled: bool
    health: str
    last_success_at: datetime | None
    next_run_at: datetime | None
    interval_minutes: int


class CompetitorOut(BaseModel):
    id: uuid.UUID
    name: str
    homepage_url: str
    notes: str | None
    muted: bool
    created_at: datetime
    sources: list[SourceSummary]
    item_count: int
    last_item_at: datetime | None
    health: str  # rollup: healthy | attention | checking

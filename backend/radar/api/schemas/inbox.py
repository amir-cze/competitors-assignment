from __future__ import annotations

import uuid
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field

from radar.api.schemas.teams import TeamOut


class AssessmentOut(BaseModel):
    team_key: str
    team_name: str
    relevance: int
    category: str
    category_label: str
    why: str
    evidence_quote: str | None
    topics_matched: list[str]
    route: str
    created_at: datetime


class FeedbackOut(BaseModel):
    team_key: str
    verdict: str
    reason: str | None
    created_at: datetime


class ItemCard(BaseModel):
    id: uuid.UUID
    kind: str
    competitor_id: uuid.UUID
    competitor_name: str
    title: str
    headline: str | None
    summary: str | None
    canonical_url: str
    published_at: datetime | None
    first_seen_at: datetime
    status: str
    primary_category: str | None
    max_relevance: int | None
    assessment: AssessmentOut | None = None
    feedback: FeedbackOut | None = None


class DeliveryOut(BaseModel):
    team_id: str
    channel: str
    status: str
    sent_at: str | None
    error: str | None


class ItemDetail(BaseModel):
    id: uuid.UUID
    kind: str
    competitor_id: uuid.UUID
    competitor_name: str
    title: str
    headline: str | None
    summary: str | None
    canonical_url: str
    published_at: datetime | None
    first_seen_at: datetime
    status: str
    primary_category: str | None
    max_relevance: int | None
    content_excerpt: str
    page_diff: dict | None
    assessments: list[AssessmentOut]
    feedback: list[FeedbackOut]
    sources: list[str]
    deliveries: list[DeliveryOut]


class FeedbackIn(BaseModel):
    team_key: str
    verdict: Literal["useful", "not_useful"]
    reason: str | None = Field(default=None, max_length=500)


class InboxPage(BaseModel):
    team: TeamOut
    items: list[ItemCard]
    total: int
    counts: dict[str, int]

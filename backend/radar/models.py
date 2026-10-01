from __future__ import annotations

import enum
import uuid
from datetime import UTC, datetime

from pgvector.sqlalchemy import Vector
from sqlalchemy import (
    JSON,
    Boolean,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship

EMBEDDING_DIM = 1536


def utcnow() -> datetime:
    return datetime.now(UTC)


def new_id() -> uuid.UUID:
    return uuid.uuid4()


class Base(DeclarativeBase):
    type_annotation_map = {dict: JSON, list: JSON}


class SourceKind(enum.StrEnum):
    feed = "feed"
    sitemap = "sitemap"
    html_list = "html_list"
    page_watch = "page_watch"


class HealthStatus(enum.StrEnum):
    new = "new"
    healthy = "healthy"
    degraded = "degraded"
    failing = "failing"
    structure_changed = "structure_changed"
    disabled = "disabled"


class ItemKind(enum.StrEnum):
    post = "post"
    page_change = "page_change"


class Route(enum.StrEnum):
    immediate = "immediate"
    digest = "digest"
    inbox = "inbox"
    muted = "muted"


class DeliveryStatus(enum.StrEnum):
    pending = "pending"
    sent = "sent"
    failed = "failed"
    skipped = "skipped"


# --------------------------------------------------------------------------- teams / topics


class Team(Base):
    __tablename__ = "teams"

    id: Mapped[uuid.UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True, default=new_id)
    key: Mapped[str] = mapped_column(String(32), unique=True)
    name: Mapped[str] = mapped_column(String(64))
    lens: Mapped[str] = mapped_column(Text)
    slack_webhook_encrypted: Mapped[str | None] = mapped_column(Text)
    slack_enabled: Mapped[bool] = mapped_column(Boolean, default=False)
    immediate_threshold: Mapped[int] = mapped_column(Integer, default=75)
    digest_threshold: Mapped[int] = mapped_column(Integer, default=50)
    digest_hour_utc: Mapped[int] = mapped_column(Integer, default=6)
    last_digest_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    topics: Mapped[list[Topic]] = relationship(back_populates="team", cascade="all, delete-orphan")


class Topic(Base):
    __tablename__ = "topics"

    id: Mapped[uuid.UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True, default=new_id)
    team_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("teams.id", ondelete="CASCADE"))
    name: Mapped[str] = mapped_column(String(120))
    description: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    team: Mapped[Team | None] = relationship(back_populates="topics")


# --------------------------------------------------------------------------- competitors / sources


class Competitor(Base):
    __tablename__ = "competitors"

    id: Mapped[uuid.UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True, default=new_id)
    name: Mapped[str] = mapped_column(String(120))
    homepage_url: Mapped[str] = mapped_column(String(512))
    notes: Mapped[str | None] = mapped_column(Text)
    muted: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    sources: Mapped[list[Source]] = relationship(back_populates="competitor", cascade="all, delete-orphan")
    items: Mapped[list[Item]] = relationship(back_populates="competitor", cascade="all, delete-orphan")


class Source(Base):
    __tablename__ = "sources"

    id: Mapped[uuid.UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True, default=new_id)
    competitor_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("competitors.id", ondelete="CASCADE"))
    kind: Mapped[str] = mapped_column(String(32))
    url: Mapped[str] = mapped_column(String(1024))
    label: Mapped[str | None] = mapped_column(String(160))
    config: Mapped[dict] = mapped_column(JSON, default=dict)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    requires_js: Mapped[bool] = mapped_column(Boolean, default=False)
    interval_minutes: Mapped[int] = mapped_column(Integer, default=60)
    next_run_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), default=utcnow)
    last_run_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_success_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    consecutive_failures: Mapped[int] = mapped_column(Integer, default=0)
    baseline_items_per_run: Mapped[float | None] = mapped_column(Float)
    etag: Mapped[str | None] = mapped_column(String(256))
    last_modified: Mapped[str | None] = mapped_column(String(128))
    health: Mapped[str] = mapped_column(String(32), default=HealthStatus.new.value)
    last_error: Mapped[str | None] = mapped_column(Text)
    claimed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    competitor: Mapped[Competitor] = relationship(back_populates="sources")
    runs: Mapped[list[Run]] = relationship(back_populates="source", cascade="all, delete-orphan")

    __table_args__ = (
        UniqueConstraint("competitor_id", "url", name="uq_source_competitor_url"),
        Index("ix_sources_due", "enabled", "next_run_at"),
    )


class Run(Base):
    __tablename__ = "runs"

    id: Mapped[uuid.UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True, default=new_id)
    source_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("sources.id", ondelete="CASCADE"))
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    status: Mapped[str] = mapped_column(String(24), default="running")  # running|ok|not_modified|error
    http_status: Mapped[int | None] = mapped_column(Integer)
    items_found: Mapped[int] = mapped_column(Integer, default=0)
    items_new: Mapped[int] = mapped_column(Integer, default=0)
    items_assessed: Mapped[int] = mapped_column(Integer, default=0)
    llm_cost_usd: Mapped[float] = mapped_column(Float, default=0.0)
    error: Mapped[str | None] = mapped_column(Text)
    log: Mapped[list] = mapped_column(JSON, default=list)
    trigger: Mapped[str] = mapped_column(String(16), default="schedule")  # schedule|manual

    source: Mapped[Source] = relationship(back_populates="runs")

    __table_args__ = (Index("ix_runs_source_started", "source_id", "started_at"),)


# --------------------------------------------------------------------------- items


class Item(Base):
    __tablename__ = "items"

    id: Mapped[uuid.UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True, default=new_id)
    competitor_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("competitors.id", ondelete="CASCADE"))
    kind: Mapped[str] = mapped_column(String(16), default=ItemKind.post.value)
    canonical_url: Mapped[str] = mapped_column(String(1024))
    title: Mapped[str] = mapped_column(String(512))
    headline: Mapped[str | None] = mapped_column(String(512))
    summary: Mapped[str | None] = mapped_column(Text)
    published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    first_seen_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    content_text: Mapped[str] = mapped_column(Text)
    content_hash: Mapped[str] = mapped_column(String(64))
    embedding = mapped_column(Vector(EMBEDDING_DIM), nullable=True)
    page_diff: Mapped[dict | None] = mapped_column(JSON)
    status: Mapped[str] = mapped_column(
        String(24), default="pending"
    )  # pending|assessed|archived|budget_hold|thin
    assessed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    prompt_version_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("prompt_versions.id"))
    max_relevance: Mapped[int | None] = mapped_column(Integer)
    primary_category: Mapped[str | None] = mapped_column(String(48))

    competitor: Mapped[Competitor] = relationship(back_populates="items")
    sources: Mapped[list[ItemSource]] = relationship(back_populates="item", cascade="all, delete-orphan")
    assessments: Mapped[list[Assessment]] = relationship(back_populates="item", cascade="all, delete-orphan")
    feedback: Mapped[list[Feedback]] = relationship(back_populates="item", cascade="all, delete-orphan")

    __table_args__ = (
        UniqueConstraint("competitor_id", "content_hash", name="uq_item_competitor_hash"),
        Index("ix_items_competitor_seen", "competitor_id", "first_seen_at"),
        Index("ix_items_status", "status"),
    )


class ItemSource(Base):
    __tablename__ = "item_sources"

    id: Mapped[uuid.UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True, default=new_id)
    item_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("items.id", ondelete="CASCADE"))
    source_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("sources.id", ondelete="SET NULL"))
    url: Mapped[str] = mapped_column(String(1024))
    seen_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    item: Mapped[Item] = relationship(back_populates="sources")

    __table_args__ = (UniqueConstraint("item_id", "url", name="uq_item_source_url"),)


class PageSnapshot(Base):
    __tablename__ = "page_snapshots"

    id: Mapped[uuid.UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True, default=new_id)
    source_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("sources.id", ondelete="CASCADE"))
    fetched_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    text_hash: Mapped[str] = mapped_column(String(64))
    text: Mapped[str] = mapped_column(Text)
    item_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("items.id", ondelete="SET NULL"))

    __table_args__ = (Index("ix_snapshots_source_fetched", "source_id", "fetched_at"),)


class RawDocument(Base):
    """Raw HTML kept briefly for debugging adapter breakage. Pruned by retention job."""

    __tablename__ = "raw_documents"

    id: Mapped[uuid.UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True, default=new_id)
    source_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("sources.id", ondelete="CASCADE"))
    url: Mapped[str] = mapped_column(String(1024))
    fetched_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    http_status: Mapped[int | None] = mapped_column(Integer)
    body: Mapped[str | None] = mapped_column(Text)


# --------------------------------------------------------------------------- assessment / delivery / feedback


class PromptVersion(Base):
    __tablename__ = "prompt_versions"

    id: Mapped[uuid.UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True, default=new_id)
    name: Mapped[str] = mapped_column(String(64), default="assess")
    version: Mapped[int] = mapped_column(Integer)
    content: Mapped[str] = mapped_column(Text)
    notes: Mapped[str | None] = mapped_column(Text)
    active: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    __table_args__ = (UniqueConstraint("name", "version", name="uq_prompt_name_version"),)


class Assessment(Base):
    __tablename__ = "assessments"

    id: Mapped[uuid.UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True, default=new_id)
    item_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("items.id", ondelete="CASCADE"))
    team_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("teams.id", ondelete="CASCADE"))
    relevance: Mapped[int] = mapped_column(Integer)
    category: Mapped[str] = mapped_column(String(48))
    why: Mapped[str] = mapped_column(Text)
    evidence_quote: Mapped[str | None] = mapped_column(Text)
    topics_matched: Mapped[list] = mapped_column(JSON, default=list)
    route: Mapped[str] = mapped_column(String(16), default=Route.inbox.value)
    prompt_version_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("prompt_versions.id"))
    model: Mapped[str | None] = mapped_column(String(64))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    item: Mapped[Item] = relationship(back_populates="assessments")
    team: Mapped[Team] = relationship()

    __table_args__ = (
        UniqueConstraint("item_id", "team_id", name="uq_assessment_item_team"),
        Index("ix_assessments_team_created", "team_id", "created_at"),
        Index("ix_assessments_team_route", "team_id", "route"),
    )


class Delivery(Base):
    __tablename__ = "deliveries"

    id: Mapped[uuid.UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True, default=new_id)
    item_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("items.id", ondelete="CASCADE"))
    team_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("teams.id", ondelete="CASCADE"))
    channel: Mapped[str] = mapped_column(String(32))  # slack_immediate | slack_digest
    dedupe_key: Mapped[str] = mapped_column(String(160), unique=True)
    status: Mapped[str] = mapped_column(String(16), default=DeliveryStatus.pending.value)
    attempts: Mapped[int] = mapped_column(Integer, default=0)
    payload: Mapped[dict | None] = mapped_column(JSON)
    error: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    sent_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class Feedback(Base):
    __tablename__ = "feedback"

    id: Mapped[uuid.UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True, default=new_id)
    item_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("items.id", ondelete="CASCADE"))
    team_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("teams.id", ondelete="CASCADE"))
    verdict: Mapped[str] = mapped_column(String(16))  # useful | not_useful
    reason: Mapped[str | None] = mapped_column(Text)
    promoted_to_golden: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    item: Mapped[Item] = relationship(back_populates="feedback")
    team: Mapped[Team] = relationship()

    __table_args__ = (UniqueConstraint("item_id", "team_id", name="uq_feedback_item_team"),)


# --------------------------------------------------------------------------- evaluation


class EvalItem(Base):
    """Golden set: items with human labels per team. Source of truth for 'is the output useful'."""

    __tablename__ = "eval_items"

    id: Mapped[uuid.UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True, default=new_id)
    item_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("items.id", ondelete="SET NULL"))
    competitor_name: Mapped[str] = mapped_column(String(120))
    title: Mapped[str] = mapped_column(String(512))
    content_text: Mapped[str] = mapped_column(Text)
    kind: Mapped[str] = mapped_column(String(16), default=ItemKind.post.value)
    labels: Mapped[dict] = mapped_column(JSON)  # {team_key: bool}
    origin: Mapped[str] = mapped_column(String(16), default="seed")  # seed | feedback
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class EvalRun(Base):
    __tablename__ = "eval_runs"

    id: Mapped[uuid.UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True, default=new_id)
    run_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    prompt_version_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("prompt_versions.id"))
    model: Mapped[str | None] = mapped_column(String(64))
    n_items: Mapped[int] = mapped_column(Integer, default=0)
    metrics: Mapped[dict] = mapped_column(
        JSON, default=dict
    )  # {team_key: {precision, recall, f1, tp, fp, fn, tn}}
    details: Mapped[list] = mapped_column(JSON, default=list)
    cost_usd: Mapped[float] = mapped_column(Float, default=0.0)
    trigger: Mapped[str] = mapped_column(String(16), default="schedule")


# --------------------------------------------------------------------------- ops


class LLMUsage(Base):
    __tablename__ = "llm_usage"

    id: Mapped[uuid.UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True, default=new_id)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    model: Mapped[str] = mapped_column(String(64))
    purpose: Mapped[str] = mapped_column(String(32))
    prompt_tokens: Mapped[int] = mapped_column(Integer, default=0)
    completion_tokens: Mapped[int] = mapped_column(Integer, default=0)
    cost_usd: Mapped[float] = mapped_column(Float, default=0.0)

    __table_args__ = (Index("ix_llm_usage_created", "created_at"),)


class SystemState(Base):
    """Tiny key-value table for heartbeats and one-off state (last prune, last health alert...)."""

    __tablename__ = "system_state"

    key: Mapped[str] = mapped_column(String(64), primary_key=True)
    value: Mapped[dict] = mapped_column(JSON, default=dict)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)


class OpsEvent(Base):
    """Operator-facing event log: health transitions, alerts, budget holds."""

    __tablename__ = "ops_events"

    id: Mapped[uuid.UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True, default=new_id)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    level: Mapped[str] = mapped_column(String(8), default="info")  # info|warn|error
    kind: Mapped[str] = mapped_column(String(32))
    message: Mapped[str] = mapped_column(Text)
    source_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("sources.id", ondelete="CASCADE"))
    data: Mapped[dict | None] = mapped_column(JSON)

    __table_args__ = (Index("ix_ops_events_created", "created_at"),)

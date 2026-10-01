from __future__ import annotations

from datetime import datetime, timedelta

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from radar import __version__
from radar.assess.llm import LLM
from radar.config import Settings
from radar.db import ping
from radar.models import Item, LLMUsage, Run, Source, SystemState, Team, utcnow

DEFAULT_BUSINESS_PASSWORD = Settings.model_fields["business_password"].default
DEFAULT_OPS_TOKEN = Settings.model_fields["ops_token"].default


def status(session: Session, *, settings: Settings, llm: LLM) -> dict:
    now = utcnow()
    hb = session.get(SystemState, "worker_heartbeat")
    hb_at = datetime.fromisoformat(hb.value["at"]) if hb and hb.value.get("at") else None
    due = (
        session.scalar(
            select(func.count())
            .select_from(Source)
            .where(Source.enabled.is_(True), Source.next_run_at <= now)
        )
        or 0
    )
    pending_items = (
        session.scalar(
            select(func.count()).select_from(Item).where(Item.status.in_(["pending", "budget_hold"]))
        )
        or 0
    )
    by_health = dict(session.execute(select(Source.health, func.count()).group_by(Source.health)).all())
    runs_24h = dict(
        session.execute(
            select(Run.status, func.count())
            .where(Run.started_at >= now - timedelta(days=1))
            .group_by(Run.status)
        ).all()
    )
    teams = session.scalars(select(Team)).all()
    return {
        "version": __version__,
        "environment": settings.environment,
        "worker": {
            "heartbeat_at": hb_at.isoformat() if hb_at else None,
            "alive": bool(hb_at and now - hb_at < timedelta(minutes=3)),
            "meta": hb.value if hb else None,
        },
        "queue": {"due_sources": int(due), "pending_items": int(pending_items)},
        "sources_by_health": {k: int(v) for k, v in by_health.items()},
        "runs_24h": {k: int(v) for k, v in runs_24h.items()},
        "llm": llm.usage_summary(session),
        "checks": {
            "database": ping(),
            "openai_key_present": llm.configured,
            "model": llm.model,
            "healthcheck_url_set": bool(settings.healthcheck_url),
            "ops_slack_set": bool(settings.ops_slack_webhook),
            "public_base_url": settings.public_base_url,
            "teams_with_slack": [t.key for t in teams if t.slack_enabled and t.slack_webhook_encrypted],
            "business_password_is_default": settings.business_password == DEFAULT_BUSINESS_PASSWORD,
            "ops_token_is_default": settings.ops_token == DEFAULT_OPS_TOKEN,
        },
        "config": {
            "worker_tick_seconds": settings.worker_tick_seconds,
            "worker_concurrency": settings.worker_concurrency,
            "default_source_interval_minutes": settings.default_source_interval_minutes,
            "page_watch_interval_minutes": settings.page_watch_interval_minutes,
            "backfill_days": settings.backfill_days,
            "llm_daily_budget_usd": settings.llm_daily_budget_usd,
            "dedup_similarity_threshold": settings.dedup_similarity_threshold,
            "page_change_min_chars": settings.page_change_min_chars,
        },
    }


def live_checks(llm: LLM) -> dict:
    ok, msg = llm.ping()
    return {"database": ping(), "openai": {"ok": ok, "message": msg}}


def llm_usage_by_day(session: Session, days: int) -> list[dict]:
    since = utcnow() - timedelta(days=days)
    rows = session.execute(
        select(
            func.date_trunc("day", LLMUsage.created_at).label("day"),
            LLMUsage.purpose,
            func.sum(LLMUsage.cost_usd),
            func.count(),
        )
        .where(LLMUsage.created_at >= since)
        .group_by("day", LLMUsage.purpose)
        .order_by("day")
    ).all()
    return [
        {"day": d.date().isoformat(), "purpose": p, "cost_usd": float(c or 0), "calls": int(n)}
        for d, p, c, n in rows
    ]

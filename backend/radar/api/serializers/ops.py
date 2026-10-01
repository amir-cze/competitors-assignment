from radar.models import EvalItem, EvalRun, OpsEvent, PromptVersion, Run, Source


def source_row(source: Source, recent_runs: list[Run]) -> dict:
    return {
        "id": str(source.id),
        "competitor_id": str(source.competitor_id),
        "competitor": source.competitor.name,
        "kind": source.kind,
        "url": source.url,
        "label": source.label,
        "enabled": source.enabled,
        "requires_js": source.requires_js,
        "interval_minutes": source.interval_minutes,
        "health": source.health,
        "last_error": source.last_error,
        "consecutive_failures": source.consecutive_failures,
        "baseline_items_per_run": source.baseline_items_per_run,
        "last_run_at": source.last_run_at.isoformat() if source.last_run_at else None,
        "last_success_at": source.last_success_at.isoformat() if source.last_success_at else None,
        "next_run_at": source.next_run_at.isoformat() if source.next_run_at else None,
        "claimed_at": source.claimed_at.isoformat() if source.claimed_at else None,
        "etag": source.etag,
        "config": source.config or {},
        "yield_trend": [
            {"at": row.started_at.isoformat(), "found": row.items_found, "new": row.items_new, "status": row.status}
            for row in recent_runs
        ],
    }


def run(row: Run, *, with_log: bool = False, with_source: bool = False) -> dict:
    payload = {
        "id": str(row.id),
        "source_id": str(row.source_id),
        "started_at": row.started_at.isoformat(),
        "finished_at": row.finished_at.isoformat() if row.finished_at else None,
        "duration_ms": int((row.finished_at - row.started_at).total_seconds() * 1000) if row.finished_at else None,
        "status": row.status,
        "http_status": row.http_status,
        "items_found": row.items_found,
        "items_new": row.items_new,
        "items_assessed": row.items_assessed,
        "llm_cost_usd": row.llm_cost_usd,
        "error": row.error,
        "trigger": row.trigger,
    }
    if with_log:
        payload["log"] = row.log
    if with_source:
        payload.update(
            {
                "competitor": row.source.competitor.name,
                "source_label": row.source.label or row.source.url,
                "source_url": row.source.url,
                "kind": row.source.kind,
            }
        )
    return payload


def prompt(row: PromptVersion) -> dict:
    return {
        "id": str(row.id),
        "name": row.name,
        "version": row.version,
        "content": row.content,
        "notes": row.notes,
        "active": row.active,
        "created_at": row.created_at.isoformat(),
    }


def ops_event(row: OpsEvent) -> dict:
    return {
        "id": str(row.id),
        "created_at": row.created_at.isoformat(),
        "level": row.level,
        "kind": row.kind,
        "message": row.message,
        "source_id": str(row.source_id) if row.source_id else None,
        "data": row.data,
    }


def eval_run(row: EvalRun, *, with_details: bool = False) -> dict:
    payload = {
        "id": str(row.id),
        "run_at": row.run_at.isoformat(),
        "n_items": row.n_items,
        "metrics": row.metrics,
        "cost_usd": row.cost_usd,
        "trigger": row.trigger,
        "model": row.model,
    }
    if with_details:
        payload["details"] = row.details
    return payload


def golden_item(row: EvalItem) -> dict:
    return {
        "id": str(row.id),
        "item_id": str(row.item_id) if row.item_id else None,
        "competitor": row.competitor_name,
        "title": row.title,
        "labels": row.labels,
        "origin": row.origin,
        "kind": row.kind,
        "created_at": row.created_at.isoformat(),
    }

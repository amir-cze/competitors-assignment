from radar.api.schemas.competitors import CompetitorOut, SourceSummary
from radar.models import Competitor, Source
from radar.services.competitors import CompetitorStats


def source_summary(source: Source) -> SourceSummary:
    return SourceSummary(
        id=source.id,
        kind=source.kind,
        url=source.url,
        label=source.label,
        enabled=source.enabled,
        health=source.health,
        last_success_at=source.last_success_at,
        next_run_at=source.next_run_at,
        interval_minutes=source.interval_minutes,
    )


def competitor(row: Competitor, stats: CompetitorStats) -> CompetitorOut:
    return CompetitorOut(
        id=row.id,
        name=row.name,
        homepage_url=row.homepage_url,
        notes=row.notes,
        muted=row.muted,
        created_at=row.created_at,
        sources=[source_summary(source) for source in row.sources],
        item_count=stats.item_count,
        last_item_at=stats.last_item_at,
        health=stats.health,
    )

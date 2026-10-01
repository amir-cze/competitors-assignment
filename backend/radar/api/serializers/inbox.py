from radar.api.schemas.inbox import (
    AssessmentOut,
    DeliveryOut,
    FeedbackOut,
    ItemCard,
    ItemDetail,
)
from radar.api.serializers.teams import team
from radar.assess.prompts import CATEGORY_LABELS
from radar.models import Assessment, Delivery, Feedback, Item, Team
from radar.services.inbox import Overview


def assessment(row: Assessment) -> AssessmentOut:
    return AssessmentOut(
        team_key=row.team.key,
        team_name=row.team.name,
        relevance=row.relevance,
        category=row.category,
        category_label=CATEGORY_LABELS.get(row.category, row.category),
        why=row.why,
        evidence_quote=row.evidence_quote,
        topics_matched=row.topics_matched or [],
        route=row.route,
        created_at=row.created_at,
    )


def feedback(row: Feedback) -> FeedbackOut:
    return FeedbackOut(
        team_key=row.team.key, verdict=row.verdict, reason=row.reason, created_at=row.created_at
    )


def item_card(item: Item, for_team: Team | None) -> ItemCard:
    scored = next((row for row in item.assessments if for_team and row.team_id == for_team.id), None)
    rated = next((row for row in item.feedback if for_team and row.team_id == for_team.id), None)
    return ItemCard(
        id=item.id,
        kind=item.kind,
        competitor_id=item.competitor_id,
        competitor_name=item.competitor.name,
        title=item.title,
        headline=item.headline,
        summary=item.summary,
        canonical_url=item.canonical_url,
        published_at=item.published_at,
        first_seen_at=item.first_seen_at,
        status=item.status,
        primary_category=item.primary_category,
        max_relevance=item.max_relevance,
        assessment=assessment(scored) if scored else None,
        feedback=feedback(rated) if rated else None,
    )


def item_detail(item: Item, deliveries: list[Delivery]) -> ItemDetail:
    return ItemDetail(
        id=item.id,
        kind=item.kind,
        competitor_id=item.competitor_id,
        competitor_name=item.competitor.name,
        title=item.title,
        headline=item.headline,
        summary=item.summary,
        canonical_url=item.canonical_url,
        published_at=item.published_at,
        first_seen_at=item.first_seen_at,
        status=item.status,
        primary_category=item.primary_category,
        max_relevance=item.max_relevance,
        content_excerpt=item.content_text[:3000],
        page_diff=item.page_diff,
        assessments=sorted((assessment(row) for row in item.assessments), key=lambda row: -row.relevance),
        feedback=[feedback(row) for row in item.feedback],
        sources=[source.url for source in item.sources],
        deliveries=[
            DeliveryOut(
                team_id=str(row.team_id),
                channel=row.channel,
                status=row.status,
                sent_at=row.sent_at.isoformat() if row.sent_at else None,
                error=row.error,
            )
            for row in deliveries
        ],
    )


def overview(data: Overview) -> dict:
    return {
        "teams": [
            {
                "team": team(highlight.team).model_dump(mode="json"),
                "surfaced_7d": highlight.surfaced_7d,
                "items": [item_card(item, highlight.team).model_dump(mode="json") for item in highlight.items],
            }
            for highlight in data.teams
        ],
        "competitor_count": data.competitor_count,
        "items_7d": data.items_7d,
        "attention": data.attention,
        "monitoring": {
            "running": data.monitoring_running,
            "last_check": data.last_check.isoformat() if data.last_check else None,
        },
        "recent_changes": [item_card(item, None).model_dump(mode="json") for item in data.recent_changes],
    }

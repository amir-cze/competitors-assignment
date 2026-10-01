from radar.api.schemas.teams import TeamOut
from radar.api.schemas.topics import TopicOut
from radar.models import Team, Topic
from radar.security import decrypt, mask_secret


def topic(row: Topic, team_key: str | None = None) -> TopicOut:
    return TopicOut(
        id=row.id,
        team_id=row.team_id,
        team_key=team_key or (row.team.key if row.team else None),
        name=row.name,
        description=row.description,
    )


def team(row: Team) -> TeamOut:
    return TeamOut(
        id=row.id,
        key=row.key,
        name=row.name,
        lens=row.lens,
        slack_enabled=row.slack_enabled,
        slack_webhook_masked=mask_secret(decrypt(row.slack_webhook_encrypted))
        if row.slack_webhook_encrypted
        else None,
        immediate_threshold=row.immediate_threshold,
        digest_threshold=row.digest_threshold,
        digest_hour_utc=row.digest_hour_utc,
        last_digest_at=row.last_digest_at,
        topics=[topic(item, row.key) for item in row.topics],
    )

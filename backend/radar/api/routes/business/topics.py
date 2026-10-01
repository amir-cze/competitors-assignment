from uuid import UUID

from fastapi import APIRouter, Response

from radar.api.deps import DB, BusinessRole
from radar.api.schemas import TopicIn, TopicOut
from radar.api.serializers.teams import topic as serialize_topic
from radar.services import teams as teams_svc

router = APIRouter(prefix="/topics", tags=["topics"])


@router.get("", response_model=list[TopicOut])
def list_topics(db: DB, _: BusinessRole):
    return [serialize_topic(row) for row in teams_svc.list_topics(db)]


@router.post("", response_model=TopicOut, status_code=201)
def create_topic(body: TopicIn, db: DB, _: BusinessRole):
    topic = teams_svc.create_topic(db, name=body.name, description=body.description, team_key=body.team_key)
    return serialize_topic(topic)


@router.delete("/{topic_id}", status_code=204)
def delete_topic(topic_id: UUID, db: DB, _: BusinessRole):
    teams_svc.delete_topic(db, topic_id)
    return Response(status_code=204)

"""Versioned scoring prompt."""

from uuid import UUID

from fastapi import APIRouter, Query

from radar.api.deps import DB, OpsRole
from radar.api.schemas import PromptIn
from radar.api.serializers.ops import prompt as serialize_prompt
from radar.services import prompts as prompts_svc

router = APIRouter(prefix="/prompts", tags=["ops-prompts"])


@router.get("")
def list_prompts(db: DB, _: OpsRole):
    return [serialize_prompt(row) for row in prompts_svc.list_prompts(db)]


@router.post("", status_code=201)
def create_prompt(body: PromptIn, db: DB, _: OpsRole, activate: bool = Query(False)):
    return serialize_prompt(prompts_svc.create_prompt(db, content=body.content, notes=body.notes, activate=activate))


@router.post("/{prompt_id}/activate")
def activate_prompt(prompt_id: UUID, db: DB, _: OpsRole):
    return serialize_prompt(prompts_svc.activate_prompt(db, prompt_id))

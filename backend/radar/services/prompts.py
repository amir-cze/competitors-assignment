from __future__ import annotations

import uuid

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from radar.assess.prompts import active_prompt
from radar.errors import InvalidInput, NotFound
from radar.models import PromptVersion

REQUIRED_PLACEHOLDERS = ("{teams_block}", "{topics_block}", "{examples_block}")


def list_prompts(session: Session, name: str = "assess") -> list[PromptVersion]:
    active_prompt(session, name)  # guarantees v1 exists on a fresh database
    return list(
        session.scalars(
            select(PromptVersion).where(PromptVersion.name == name).order_by(PromptVersion.version.desc())
        ).all()
    )


def create_prompt(
    session: Session, *, content: str, notes: str | None, activate: bool, name: str = "assess"
) -> PromptVersion:
    missing = [p for p in REQUIRED_PLACEHOLDERS if p not in content]
    if missing:
        raise InvalidInput(f"Prompt must include the placeholder(s): {', '.join(missing)}")
    latest = session.scalar(select(func.max(PromptVersion.version)).where(PromptVersion.name == name)) or 0
    pv = PromptVersion(name=name, version=latest + 1, content=content, notes=notes, active=False)
    session.add(pv)
    session.flush()
    if activate:
        activate_prompt(session, pv.id)
    return pv


def activate_prompt(session: Session, prompt_id: uuid.UUID) -> PromptVersion:
    pv = session.get(PromptVersion, prompt_id)
    if pv is None:
        raise NotFound("Prompt not found")
    for other in session.scalars(select(PromptVersion).where(PromptVersion.name == pv.name)).all():
        other.active = other.id == pv.id
    session.flush()
    return pv

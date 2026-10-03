"""The company's own profile: what we sell and what we do not.

One row in system_state. The business edits it in Settings; the scorer injects it into every assessment so that
"capabilities they have that we do not" is judged against something the business controls, not a sentence an
engineer hard-coded.
"""

from __future__ import annotations

from sqlalchemy.orm import Session

from radar.assess.prompts import DEFAULT_COMPANY_PROFILE
from radar.errors import InvalidInput
from radar.models import SystemState, utcnow

KEY = "company_profile"
MAX_CHARS = 4000


def get_profile(session: Session) -> str:
    row = session.get(SystemState, KEY)
    text = (row.value or {}).get("text", "") if row else ""
    return text.strip() or DEFAULT_COMPANY_PROFILE


def is_default(session: Session) -> bool:
    row = session.get(SystemState, KEY)
    return not (row and (row.value or {}).get("text", "").strip())


def set_profile(session: Session, text: str) -> str:
    text = text.strip()
    if len(text) > MAX_CHARS:
        raise InvalidInput(f"Keep the profile under {MAX_CHARS} characters")
    row = session.get(SystemState, KEY) or SystemState(key=KEY, value={})
    row.value = {"text": text, "updated_at": utcnow().isoformat()}
    session.add(row)
    session.flush()
    return get_profile(session)

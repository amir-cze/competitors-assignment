"""Prompt templates and the builders that fill them from business configuration.

Separation of concerns:
- The *template* (how the model is instructed) is versioned in `prompt_versions` and owned by the operator.
- The *lenses and topics* (what matters to whom) live on teams/topics and are owned by the business.
- *Few-shot examples* come from feedback, so the prompt improves without anyone editing it.
"""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from radar.models import Feedback, Item, PromptVersion, Team, Topic

CATEGORIES = [
    "product_launch",
    "feature_update",
    "positioning_shift",
    "funding",
    "partnership",
    "acquisition",
    "research",
    "technical_deep_dive",
    "customer_story",
    "event_or_webinar",
    "hiring_signal",
    "pricing_change",
    "compliance_or_certification",
    "other",
]

CATEGORY_LABELS = {
    "product_launch": "Product launch",
    "feature_update": "Feature update",
    "positioning_shift": "Positioning shift",
    "funding": "Funding",
    "partnership": "Partnership",
    "acquisition": "Acquisition",
    "research": "Research",
    "technical_deep_dive": "Technical deep dive",
    "customer_story": "Customer story",
    "event_or_webinar": "Event / webinar",
    "hiring_signal": "Hiring signal",
    "pricing_change": "Pricing change",
    "compliance_or_certification": "Compliance / certification",
    "other": "Other",
}

DEFAULT_ASSESS_PROMPT_V1 = """You are Radar, a competitive-intelligence analyst for Noma Security, an AI security and governance platform
(AI discovery and inventory, AI security posture management, AI red teaming, runtime protection for AI agents and applications).

You will receive ONE piece of competitor content (a new post, or a diff showing how a page's wording changed).
Assess how important it is for EACH internal team listed below. Be skeptical by default: most content is routine
marketing and should score low. A score of 75+ means "interrupt someone's day"; 50-74 means "worth reading this week";
below 50 means "archive". Only the teams' own definitions of importance matter, not general newsworthiness.

{teams_block}

Topics the business has asked us to watch (mention matches by name in topics_matched):
{topics_block}

{examples_block}

Rules:
- Score each team independently. The same item can be 85 for R&D and 20 for Marketing.
- Ground every score in the text. evidence_quote must be a verbatim excerpt (max 240 chars) from the content.
- why must be one concrete sentence a busy person can act on, naming what changed and why that team should care.
- For page changes, focus on what the new wording claims that the old wording did not.
- If the content is thin, boilerplate, an event invite with no substance, or a generic listicle, set is_substantive to false and score everything below 30.
- headline: rewrite the title as a crisp, neutral one-liner (max 90 chars). summary: two sentences, factual.
- category: choose the single best category for the item as a whole.
"""


def teams_block(teams: list[Team]) -> str:
    lines = []
    for t in teams:
        lines.append(f"TEAM {t.key} ({t.name}) cares about:\n{t.lens.strip()}\n")
    return "\n".join(lines)


def topics_block(topics: list[Topic], teams: list[Team]) -> str:
    if not topics:
        return "(none configured yet)"
    by_id = {t.id: t.key for t in teams}
    lines = []
    for topic in topics:
        scope = by_id.get(topic.team_id, "all teams") if topic.team_id else "all teams"
        desc = f" — {topic.description.strip()}" if topic.description else ""
        lines.append(f"- {topic.name} [{scope}]{desc}")
    return "\n".join(lines)


def examples_block(session: Session, teams: list[Team], per_team: int = 3) -> str:
    """Recent human feedback, rendered as calibration examples. Empty until people start rating."""
    sections: list[str] = []
    for team in teams:
        rows = session.execute(
            select(Feedback, Item)
            .join(Item, Item.id == Feedback.item_id)
            .where(Feedback.team_id == team.id)
            .order_by(Feedback.created_at.desc())
            .limit(per_team * 4)
        ).all()
        useful = [(f, i) for f, i in rows if f.verdict == "useful"][:per_team]
        not_useful = [(f, i) for f, i in rows if f.verdict == "not_useful"][:per_team]
        if not useful and not not_useful:
            continue
        lines = [f"Calibration from {team.name} (what they actually found useful):"]
        for f, i in useful:
            reason = f" Reason: {f.reason.strip()}" if f.reason else ""
            lines.append(f'  USEFUL: "{i.headline or i.title}".{reason}')
        for f, i in not_useful:
            reason = f" Reason: {f.reason.strip()}" if f.reason else ""
            lines.append(f'  NOT USEFUL: "{i.headline or i.title}".{reason}')
        sections.append("\n".join(lines))
    if not sections:
        return ""
    return "Human calibration examples (weigh these heavily when similar):\n" + "\n\n".join(sections)


def render_system_prompt(session: Session, template: str, teams: list[Team], topics: list[Topic]) -> str:
    return template.format(
        teams_block=teams_block(teams),
        topics_block=topics_block(topics, teams),
        examples_block=examples_block(session, teams),
    )


def render_user_prompt(
    *, competitor_name: str, kind: str, title: str, url: str, published: str | None, body: str
) -> str:
    header = [
        f"Competitor: {competitor_name}",
        f"Type: {'page wording change' if kind == 'page_change' else 'new content'}",
        f"Title: {title}",
        f"URL: {url}",
    ]
    if published:
        header.append(f"Published: {published}")
    return "\n".join(header) + "\n\nCONTENT:\n" + body


def active_prompt(session: Session, name: str = "assess") -> PromptVersion:
    pv = session.scalar(
        select(PromptVersion).where(PromptVersion.name == name, PromptVersion.active.is_(True))
    )
    if pv is None:
        pv = session.scalar(
            select(PromptVersion).where(PromptVersion.name == name).order_by(PromptVersion.version.desc())
        )
    if pv is None:
        pv = PromptVersion(
            name=name, version=1, content=DEFAULT_ASSESS_PROMPT_V1, active=True, notes="Initial prompt"
        )
        session.add(pv)
        session.flush()
    return pv

"""Per-team scoring of one item with a single structured LLM call."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from radar.assess.llm import LLM
from radar.assess.prompts import CATEGORIES, active_prompt, render_system_prompt, render_user_prompt
from radar.assess.routing import clamp_score, decide_route
from radar.ingest.diff import PageDiff, render_diff_for_llm
from radar.logging import get_logger
from radar.models import Assessment, Item, Route, Team, Topic, utcnow

log = get_logger(__name__)

CategoryLiteral = Literal[
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
assert set(CategoryLiteral.__args__) == set(CATEGORIES)  # keep prompts.py and the schema in sync

MAX_BODY_CHARS = 7000


class TeamScore(BaseModel):
    team_key: str
    relevance: int
    why: str
    evidence_quote: str
    topics_matched: list[str]


class ItemAssessmentOut(BaseModel):
    headline: str
    summary: str
    category: CategoryLiteral
    is_substantive: bool
    teams: list[TeamScore]


@dataclass
class ScoringResult:
    assessments: list[Assessment]
    cost_usd: float
    is_substantive: bool


def load_context(session: Session) -> tuple[list[Team], list[Topic]]:
    teams = list(session.scalars(select(Team).order_by(Team.created_at)).all())
    topics = list(session.scalars(select(Topic).order_by(Topic.created_at)).all())
    return teams, topics


def body_for(item: Item) -> str:
    if item.kind == "page_change" and item.page_diff:
        diff = PageDiff(added=item.page_diff.get("added", []), removed=item.page_diff.get("removed", []))
        return render_diff_for_llm(diff)
    text = item.content_text or ""
    if len(text) > MAX_BODY_CHARS:
        # Keep the head (lede) and tail (often the announcement details).
        return text[: MAX_BODY_CHARS - 1500] + "\n[...]\n" + text[-1500:]
    return text


class Scorer:
    """Turns an item into per-team assessments. Persistence of the result is part of the contract so
    that prompt version and model are always recorded alongside the scores."""

    def __init__(self, llm: LLM):
        self._llm = llm

    @property
    def available(self) -> bool:
        return self._llm.configured

    @property
    def model(self) -> str:
        return self._llm.model

    def score_item(
        self,
        session: Session,
        item: Item,
        *,
        teams: list[Team] | None = None,
        topics: list[Topic] | None = None,
    ) -> ScoringResult:
        """Assess `item` for every team, persist assessments, update item status. Raises BudgetExceeded when out of budget."""
        if teams is None or topics is None:
            teams, topics = load_context(session)
        pv = active_prompt(session)
        system = render_system_prompt(session, pv.content, teams, topics)
        user = render_user_prompt(
            competitor_name=item.competitor.name,
            kind=item.kind,
            title=item.title,
            url=item.canonical_url,
            published=item.published_at.date().isoformat() if item.published_at else None,
            body=body_for(item),
        )
        parsed, cost = self._llm.complete_structured(
            ItemAssessmentOut, system=system, user=user, purpose="assess", session=session
        )

        by_key = {t.key: t for t in teams}
        existing = {a.team_id: a for a in item.assessments}
        out: list[Assessment] = []
        seen_keys: set[str] = set()
        for ts in parsed.teams:
            team = by_key.get(ts.team_key)
            if team is None or ts.team_key in seen_keys:
                continue
            seen_keys.add(ts.team_key)
            relevance = clamp_score(ts.relevance)
            route = decide_route(
                relevance,
                immediate_threshold=team.immediate_threshold,
                digest_threshold=team.digest_threshold,
                competitor_muted=item.competitor.muted,
                is_substantive=parsed.is_substantive,
            )
            a = existing.get(team.id) or Assessment(item_id=item.id, team_id=team.id)
            a.relevance = relevance
            a.category = parsed.category
            a.why = ts.why.strip()
            a.evidence_quote = ts.evidence_quote.strip()[:400] or None
            a.topics_matched = [t for t in ts.topics_matched if t][:8]
            a.route = route.value
            a.prompt_version_id = pv.id
            a.model = self._llm.model
            a.created_at = utcnow()
            session.add(a)
            out.append(a)

        # Teams the model skipped get an explicit low score, so the inbox is never silently empty.
        for team in teams:
            if team.key in seen_keys:
                continue
            a = existing.get(team.id) or Assessment(item_id=item.id, team_id=team.id)
            a.relevance = 0
            a.category = parsed.category
            a.why = "Not relevant to this team."
            a.evidence_quote = None
            a.topics_matched = []
            a.route = Route.inbox.value
            a.prompt_version_id = pv.id
            a.model = self._llm.model
            session.add(a)
            out.append(a)

        item.headline = parsed.headline.strip()[:500] or item.title
        item.summary = parsed.summary.strip()
        item.primary_category = parsed.category
        item.max_relevance = max((a.relevance for a in out), default=0)
        item.status = "assessed"
        item.assessed_at = utcnow()
        item.prompt_version_id = pv.id
        session.flush()
        log.info(
            "assess.scored",
            item_id=str(item.id),
            max_relevance=item.max_relevance,
            category=item.primary_category,
            cost=round(cost, 5),
        )
        return ScoringResult(assessments=out, cost_usd=cost, is_substantive=parsed.is_substantive)

    def score_text(
        self,
        session: Session,
        *,
        competitor_name: str,
        title: str,
        body: str,
        kind: str,
        teams: list[Team],
        topics: list[Topic],
        template: str,
    ) -> tuple[ItemAssessmentOut, float]:
        """Scoring without persistence, used by the evaluation harness."""
        system = render_system_prompt(session, template, teams, topics)
        user = render_user_prompt(
            competitor_name=competitor_name,
            kind=kind,
            title=title,
            url="(golden set)",
            published=None,
            body=body[:MAX_BODY_CHARS],
        )
        return self._llm.complete_structured(
            ItemAssessmentOut, system=system, user=user, purpose="eval", session=session
        )

    def embed_for_dedup(self, session: Session, title: str, text: str) -> list[float]:
        vectors, _ = self._llm.embed([f"{title}\n\n{text[:6000]}"], purpose="embed", session=session)
        return vectors[0]

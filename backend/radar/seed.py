"""Seed the database with teams, default topics, the v1 prompt, a starter golden set and (optionally) competitors.

uv run radar-seed                 # teams, topics, prompt, golden set (idempotent)
uv run radar-seed --competitors   # also add the default competitor watchlist (uses live discovery, falls back to static)
"""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path

from sqlalchemy import select

from radar.assess.prompts import active_prompt
from radar.config import get_settings
from radar.db import session_scope
from radar.ingest.extract import canonicalize_url
from radar.logging import configure_logging, get_logger
from radar.models import Competitor, EvalItem, Source, Team, Topic, utcnow

log = get_logger(__name__)

TEAMS = [
    {
        "key": "marketing",
        "name": "Marketing",
        "lens": (
            "Positioning and language. Which claims a competitor leads with, how they name and frame what they sell, "
            "whether they are pushing a particular term (e.g. 'AI-SPM', 'AI firewall', 'agentic security') or trying to "
            "define a category around themselves. New taglines, homepage messaging changes, analyst mentions, awards, "
            "category reports, funding announcements they will use in sales conversations, and campaigns aimed at our buyers."
        ),
        "immediate_threshold": 75,
        "digest_threshold": 50,
    },
    {
        "key": "product",
        "name": "Product",
        "lens": (
            "Coverage and direction. Capabilities they have that we do not (or claim to), segments or markets they are moving "
            "into, integrations and platform support, pricing and packaging changes, and where their roadmap appears to be "
            "heading. Product launches, feature updates, new modules, compliance certifications, and customer stories that "
            "reveal which use cases they win on."
        ),
        "immediate_threshold": 75,
        "digest_threshold": 50,
    },
    {
        "key": "rnd",
        "name": "R&D",
        "lens": (
            "Technical substance. How something was actually built or integrated: architectures, detection approaches, "
            "models used, interfaces (SDKs, APIs, MCP servers, proxies, browser extensions), open-source releases, "
            "vulnerability research and novel attack techniques, benchmarks and evaluation methods. Approaches, interfaces "
            "or technologies we were not aware of. Marketing fluff without technical detail is not interesting."
        ),
        "immediate_threshold": 75,
        "digest_threshold": 50,
    },
]

TOPICS = [
    {
        "name": "AI agent security",
        "description": "Securing autonomous agents, agent runtime protection, agent identity",
    },
    {"name": "MCP", "description": "Model Context Protocol servers, gateways, tool-call security"},
    {"name": "AI red teaming", "description": "Automated adversarial testing of models and applications"},
    {
        "name": "AI-SPM / AI posture management",
        "description": "Discovery and inventory of AI assets, posture scoring",
    },
    {"name": "Prompt injection", "description": "Direct and indirect prompt injection, jailbreaks, defenses"},
    {"name": "Shadow AI", "description": "Unsanctioned AI usage discovery and governance"},
    {
        "name": "EU AI Act / compliance",
        "description": "Regulatory frameworks: EU AI Act, ISO 42001, NIST AI RMF",
        "team_key": "product",
    },
    {
        "name": "Funding and M&A",
        "description": "Rounds, valuations, acquisitions in AI security",
        "team_key": "marketing",
    },
    {
        "name": "Supply chain / model security",
        "description": "Malicious models, pickle scanning, dependency attacks",
        "team_key": "rnd",
    },
]

STATIC_COMPETITORS = [
    {
        "name": "Prompt Security",
        "homepage_url": "https://www.prompt.security",
        "sources": [
            {"kind": "html_list", "url": "https://www.prompt.security/blog", "label": "Blog"},
            {"kind": "page_watch", "url": "https://www.prompt.security", "label": "Homepage"},
        ],
    },
    {
        "name": "Lakera",
        "homepage_url": "https://www.lakera.ai",
        "sources": [
            {"kind": "html_list", "url": "https://www.lakera.ai/blog", "label": "Blog"},
            {"kind": "page_watch", "url": "https://www.lakera.ai", "label": "Homepage"},
        ],
    },
    {
        "name": "Zenity",
        "homepage_url": "https://zenity.io",
        "sources": [
            {"kind": "html_list", "url": "https://zenity.io/blog", "label": "Blog"},
            {"kind": "page_watch", "url": "https://zenity.io", "label": "Homepage"},
        ],
    },
    {
        "name": "HiddenLayer",
        "homepage_url": "https://www.hiddenlayer.com",
        "sources": [
            {
                "kind": "html_list",
                "url": "https://www.hiddenlayer.com/innovation-hub/insights",
                "label": "Insights",
            },
            {"kind": "page_watch", "url": "https://www.hiddenlayer.com", "label": "Homepage"},
        ],
    },
    {
        "name": "Pillar Security",
        "homepage_url": "https://www.pillar.security",
        "sources": [
            {"kind": "html_list", "url": "https://www.pillar.security/blog", "label": "Blog"},
            {"kind": "page_watch", "url": "https://www.pillar.security", "label": "Homepage"},
        ],
    },
    {
        "name": "Aim Security",
        "homepage_url": "https://www.aim.security",
        "sources": [
            {"kind": "html_list", "url": "https://www.aim.security/blog", "label": "Blog"},
            {"kind": "page_watch", "url": "https://www.aim.security", "label": "Homepage"},
        ],
    },
]


def seed_core(session) -> None:
    by_key: dict[str, Team] = {}
    for t in TEAMS:
        team = session.scalar(select(Team).where(Team.key == t["key"]))
        if team is None:
            team = Team(**t)
            session.add(team)
            log.info("seed.team", key=t["key"])
        by_key[t["key"]] = team
    session.flush()

    for topic in TOPICS:
        team = by_key.get(topic.get("team_key")) if topic.get("team_key") else None
        exists = session.scalar(select(Topic).where(Topic.name == topic["name"]))
        if exists is None:
            session.add(
                Topic(
                    name=topic["name"],
                    description=topic.get("description"),
                    team_id=team.id if team else None,
                )
            )
    active_prompt(session)

    evals_dir = Path(os.environ.get("RADAR_EVALS_DIR") or Path(__file__).resolve().parents[2] / "evals")
    golden_path = evals_dir / "golden_seed.jsonl"
    if golden_path.exists():
        existing_titles = {g.title for g in session.scalars(select(EvalItem)).all()}
        added = 0
        for line in golden_path.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            row = json.loads(line)
            if row["title"] in existing_titles:
                continue
            session.add(
                EvalItem(
                    competitor_name=row["competitor"],
                    title=row["title"],
                    content_text=row["content"],
                    labels=row["labels"],
                    kind=row.get("kind", "post"),
                    origin="seed",
                )
            )
            added += 1
        log.info("seed.golden", added=added)


def seed_competitors(session, *, use_discovery: bool) -> None:
    settings = get_settings()
    for comp in STATIC_COMPETITORS:
        if session.scalar(select(Competitor).where(Competitor.name == comp["name"])):
            continue
        sources = comp["sources"]
        if use_discovery:
            try:
                from radar.ingest.discovery import discover

                result = discover(comp["homepage_url"])
                recommended = [c for c in result.candidates if c.recommended]
                if recommended:
                    sources = [{"kind": c.kind, "url": c.url, "label": c.label} for c in recommended]
                    log.info("seed.discovered", competitor=comp["name"], sources=[c.url for c in recommended])
            except Exception as exc:
                log.warning("seed.discovery_failed", competitor=comp["name"], error=str(exc))
        c = Competitor(name=comp["name"], homepage_url=canonicalize_url(comp["homepage_url"]))
        session.add(c)
        session.flush()
        seen = set()
        for s in sources:
            url = canonicalize_url(s["url"])
            if url in seen:
                continue
            seen.add(url)
            interval = (
                settings.page_watch_interval_minutes
                if s["kind"] == "page_watch"
                else settings.default_source_interval_minutes
            )
            session.add(
                Source(
                    competitor_id=c.id,
                    kind=s["kind"],
                    url=url,
                    label=s.get("label"),
                    interval_minutes=interval,
                    next_run_at=utcnow(),
                )
            )
        log.info("seed.competitor", name=comp["name"], sources=len(seen))


def run() -> None:
    configure_logging()
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--competitors", action="store_true", help="also add the default competitor watchlist"
    )
    parser.add_argument(
        "--no-discovery", action="store_true", help="use the static source list instead of live discovery"
    )
    args = parser.parse_args()
    with session_scope() as session:
        seed_core(session)
        if args.competitors:
            seed_competitors(session, use_discovery=not args.no_discovery)
    log.info("seed.done")


if __name__ == "__main__":
    run()

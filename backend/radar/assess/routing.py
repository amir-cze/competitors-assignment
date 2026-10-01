"""Decide where an assessment goes. Pure function, unit tested, no I/O."""

from __future__ import annotations

from radar.models import Route


def decide_route(
    relevance: int,
    *,
    immediate_threshold: int,
    digest_threshold: int,
    competitor_muted: bool = False,
    is_substantive: bool = True,
) -> Route:
    if competitor_muted:
        return Route.muted
    if not is_substantive:
        return Route.inbox
    if relevance >= immediate_threshold:
        return Route.immediate
    if relevance >= digest_threshold:
        return Route.digest
    return Route.inbox


def clamp_score(value: int) -> int:
    return max(0, min(100, int(value)))

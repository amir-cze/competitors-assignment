"""Duplicate detection: exact hash first, then embedding similarity within the same competitor."""

from __future__ import annotations

import uuid
from datetime import timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from radar.models import Item, ItemSource, utcnow


def find_exact(session: Session, competitor_id: uuid.UUID, content_hash: str) -> Item | None:
    return session.scalar(
        select(Item).where(Item.competitor_id == competitor_id, Item.content_hash == content_hash)
    )


def find_by_url(session: Session, competitor_id: uuid.UUID, canonical_url: str) -> Item | None:
    """Match on the item's canonical URL *or* any alias URL we linked to it earlier (a near-duplicate
    seen under another address, a second source listing the same post). Without the alias check every
    run would re-fetch and re-embed the same duplicates."""
    item = session.scalar(
        select(Item).where(Item.competitor_id == competitor_id, Item.canonical_url == canonical_url)
    )
    if item:
        return item
    return session.scalar(
        select(Item)
        .join(ItemSource, ItemSource.item_id == Item.id)
        .where(Item.competitor_id == competitor_id, ItemSource.url == canonical_url)
        .limit(1)
    )


def find_near_duplicate(
    session: Session,
    competitor_id: uuid.UUID,
    embedding: list[float],
    *,
    threshold: float,
    window_days: int = 90,
) -> tuple[Item, float] | None:
    """Nearest item by cosine distance. Returns (item, similarity) if above threshold."""
    since = utcnow() - timedelta(days=window_days)
    distance = Item.embedding.cosine_distance(embedding)
    row = session.execute(
        select(Item, distance.label("distance"))
        .where(Item.competitor_id == competitor_id, Item.embedding.isnot(None), Item.first_seen_at >= since)
        .order_by(distance)
        .limit(1)
    ).first()
    if not row:
        return None
    item, dist = row
    similarity = 1.0 - float(dist)
    if similarity >= threshold:
        return item, similarity
    return None


def cosine_similarity(a: list[float], b: list[float]) -> float:
    dot = sum(x * y for x, y in zip(a, b, strict=False))
    na = sum(x * x for x in a) ** 0.5
    nb = sum(y * y for y in b) ** 0.5
    if na == 0 or nb == 0:
        return 0.0
    return dot / (na * nb)

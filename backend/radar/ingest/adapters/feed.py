from __future__ import annotations

import time
from datetime import UTC, datetime

import feedparser

from radar.ingest.adapters.base import AdapterResult, RawItem, SourceContext
from radar.ingest.extract import canonicalize_url, parse_date


def _entry_date(entry) -> datetime | None:
    for key in ("published_parsed", "updated_parsed", "created_parsed"):
        value = entry.get(key)
        if value:
            try:
                return datetime.fromtimestamp(time.mktime(value), tz=UTC)
            except (OverflowError, ValueError):
                continue
    for key in ("published", "updated", "created"):
        if entry.get(key):
            return parse_date(entry.get(key))
    return None


def parse_feed(body: str, max_items: int = 40) -> list[RawItem]:
    parsed = feedparser.parse(body)
    items: list[RawItem] = []
    for entry in parsed.entries[:max_items]:
        link = entry.get("link")
        if not link:
            continue
        html = None
        if entry.get("content"):
            html = entry["content"][0].get("value")
        elif entry.get("summary_detail", {}).get("type") == "text/html":
            html = entry.get("summary")
        items.append(
            RawItem(
                url=canonicalize_url(link),
                title=(entry.get("title") or "").strip() or None,
                published_at=_entry_date(entry),
                summary=(entry.get("summary") or "")[:1000] or None,
                html=html,
            )
        )
    return items


def looks_like_feed(body: str | None, content_type: str = "") -> bool:
    if not body:
        return False
    head = body[:2000].lower()
    return (
        "<rss" in head
        or "<feed" in head
        or "<rdf:rdf" in head
        or "xml" in content_type
        and "<channel" in head
    )


class FeedAdapter:
    kind = "feed"

    def fetch(self, ctx: SourceContext) -> AdapterResult:
        res = ctx.get()
        if res.not_modified:
            return AdapterResult(
                http_status=304, not_modified=True, etag=ctx.etag, last_modified=ctx.last_modified
            )
        if not res.ok:
            return AdapterResult(http_status=res.status, error=f"HTTP {res.status}")
        if not looks_like_feed(res.body, res.content_type):
            return AdapterResult(http_status=res.status, error="Response is not an RSS/Atom feed")
        items = parse_feed(res.body or "", ctx.max_items)
        return AdapterResult(
            items=items, http_status=res.status, etag=res.etag, last_modified=res.last_modified
        )

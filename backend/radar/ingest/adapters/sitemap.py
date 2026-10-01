from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import UTC, datetime

from bs4 import BeautifulSoup

from radar.ingest.adapters.base import AdapterResult, RawItem, SourceContext
from radar.ingest.extract import canonicalize_url, parse_date

CONTENT_PATH_HINTS = (
    "/blog",
    "/news",
    "/newsroom",
    "/press",
    "/insights",
    "/resources",
    "/research",
    "/articles",
    "/post",
    "/announcements",
    "/updates",
)
NON_CONTENT_HINTS = (
    "/tag/",
    "/tags/",
    "/category/",
    "/categories/",
    "/author/",
    "/page/",
    "/wp-content/",
    "/feed",
    ".xml",
    "/search",
)


@dataclass
class SitemapEntry:
    url: str
    lastmod: datetime | None


def parse_sitemap(body: str) -> tuple[list[SitemapEntry], list[str]]:
    """Returns (url entries, child sitemap urls)."""
    soup = BeautifulSoup(body, "xml")
    children = [loc.get_text(strip=True) for loc in soup.select("sitemap > loc")]
    entries: list[SitemapEntry] = []
    for node in soup.select("url"):
        loc = node.find("loc")
        if not loc:
            continue
        lastmod = node.find("lastmod")
        entries.append(
            SitemapEntry(
                url=loc.get_text(strip=True),
                lastmod=parse_date(lastmod.get_text(strip=True)) if lastmod else None,
            )
        )
    return entries, children


def is_content_url(url: str, include_pattern: str | None = None) -> bool:
    lower = url.lower()
    if any(h in lower for h in NON_CONTENT_HINTS):
        return False
    if include_pattern:
        return re.search(include_pattern, url) is not None
    return any(h in lower for h in CONTENT_PATH_HINTS)


def _looks_like_index_page(url: str) -> bool:
    path = url.split("://", 1)[-1].split("/", 1)[-1] if "://" in url else url
    return path.strip("/").count("/") == 0  # e.g. /blog itself


class SitemapAdapter:
    """Reads a sitemap (or sitemap index), keeps content-looking URLs, newest lastmod first."""

    kind = "sitemap"

    def fetch(self, ctx: SourceContext) -> AdapterResult:
        res = ctx.get()
        if res.not_modified:
            return AdapterResult(
                http_status=304, not_modified=True, etag=ctx.etag, last_modified=ctx.last_modified
            )
        if not res.ok or not res.body:
            return AdapterResult(http_status=res.status, error=f"HTTP {res.status}")

        include = ctx.config.get("include_pattern")
        entries, children = parse_sitemap(res.body)
        notes: list[str] = []
        # Follow child sitemaps that look content-related (bounded).
        for child in children[:12]:
            if children and not any(
                h in child.lower() for h in ("post", "blog", "news", "article", "page", "resource", "press")
            ):
                continue
            child_res = ctx.fetcher.fetch(child)
            if child_res.ok and child_res.body:
                child_entries, _ = parse_sitemap(child_res.body)
                entries.extend(child_entries)
            else:
                notes.append(f"child sitemap {child} -> HTTP {child_res.status}")

        content = [e for e in entries if is_content_url(e.url, include) and not _looks_like_index_page(e.url)]
        epoch = datetime.min.replace(tzinfo=UTC)
        content.sort(key=lambda e: e.lastmod or epoch, reverse=True)
        items = [
            RawItem(url=canonicalize_url(e.url), published_at=e.lastmod) for e in content[: ctx.max_items]
        ]
        return AdapterResult(
            items=items, http_status=res.status, etag=res.etag, last_modified=res.last_modified, notes=notes
        )

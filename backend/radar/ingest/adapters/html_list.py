"""HTML listing adapter.

Strategy (cheapest first):
1. If the source has a cached CSS "recipe" (item/link/title/date selectors), use it.
2. Otherwise use a structural heuristic: same-site links with headline-like text, grouped by path shape.
3. If both yield too little on a 200 response, ask the LLM once to derive a new recipe from a trimmed
   HTML sample and cache it (self-healing). The run is flagged so the operator can see what happened.
"""

from __future__ import annotations

import re
from datetime import UTC, datetime
from urllib.parse import urljoin, urlparse

import tldextract
from bs4 import BeautifulSoup, Tag

from radar.assess.llm import LLM, derive_list_recipe
from radar.ingest.adapters.base import AdapterResult, RawItem, SourceContext
from radar.ingest.adapters.sitemap import NON_CONTENT_HINTS
from radar.ingest.extract import canonicalize_url, parse_date
from radar.logging import get_logger

log = get_logger(__name__)

MIN_TITLE_LEN = 18
MIN_YIELD = 2
DATE_RE = re.compile(
    r"\b(?:\d{1,2}\s+)?(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Sept|Oct|Nov|Dec)[a-z]*\.?\s+\d{1,2}(?:st|nd|rd|th)?,?\s+\d{4}\b|\b\d{4}-\d{2}-\d{2}\b",
    re.IGNORECASE,
)
SKIP_ANCESTORS = ("nav", "footer", "header", "aside")
SKIP_TEXT = {
    "read more",
    "learn more",
    "view all",
    "see all",
    "next",
    "previous",
    "home",
    "blog",
    "contact",
    "login",
    "sign in",
    "sign up",
    "get a demo",
    "request a demo",
    "book a demo",
}


def _registrable(url: str) -> str:
    ext = tldextract.extract(url)
    return f"{ext.domain}.{ext.suffix}" if ext.suffix else ext.domain


def _in_skipped_region(tag: Tag) -> bool:
    for parent in tag.parents:
        if not isinstance(parent, Tag):
            continue
        if parent.name in SKIP_ANCESTORS:
            return True
        role = (parent.get("role") or "").lower()
        if role in ("navigation", "banner", "contentinfo"):
            return True
    return False


def _card_for(link: Tag, depth: int = 3) -> Tag:
    node: Tag = link
    for _ in range(depth):
        if node.parent and isinstance(node.parent, Tag) and node.parent.name not in ("body", "html", "main"):
            node = node.parent
        else:
            break
    return node


LEADING_DATE_RE = re.compile(
    r"^(?:(?:Mon|Tue|Wed|Thu|Fri|Sat|Sun)[a-z]*,?\s+)?(?:\d{1,2}\s+)?(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Sept|Oct|Nov|Dec)[a-z]*\.?\s+\d{1,2}(?:st|nd|rd|th)?,?\s+\d{4}\s*[|·•-]?\s*",
    re.IGNORECASE,
)
TRAILING_CTA_RE = re.compile(
    r"\s*(?:read (?:more|article|post|now)|learn more|continue reading|view (?:more|post)|watch now|download|→|»|>)\s*$",
    re.IGNORECASE,
)
PLACEHOLDER_TITLES = {
    "title of post",
    "post title",
    "blog post title",
    "lorem ipsum",
    "heading",
    "card title",
}
HEADINGS = ("h1", "h2", "h3", "h4")


def clean_title(text: str) -> str:
    text = re.sub(r"\s+", " ", text).strip()
    text = LEADING_DATE_RE.sub("", text)
    for _ in range(2):
        text = TRAILING_CTA_RE.sub("", text)
    return text.strip(" -–—|·•").strip()


def _title_from(link: Tag, card: Tag) -> str:
    """Prefer a heading over raw link text: link text often glues date, author and CTA together."""
    candidates: list[str] = []
    inner_heading = link.find(HEADINGS)
    if inner_heading:
        candidates.append(inner_heading.get_text(" ", strip=True))
    card_heading = card.find(HEADINGS)
    if card_heading:
        candidates.append(card_heading.get_text(" ", strip=True))
    candidates.append(link.get_text(" ", strip=True))
    for attr in ("title", "aria-label"):
        if link.get(attr):
            candidates.append(str(link[attr]))
    for raw in candidates:
        title = clean_title(raw)
        if (
            len(title) >= MIN_TITLE_LEN
            and title.lower() not in SKIP_TEXT
            and title.lower() not in PLACEHOLDER_TITLES
        ):
            return title
    return clean_title(candidates[-1]) if candidates else ""


def title_quality_ok(items: list[RawItem]) -> bool:
    """A listing whose titles are mostly identical is a template, a post page, or a nav block."""
    titles = [i.title.lower() for i in items if i.title]
    if len(titles) < 2:
        return bool(titles)
    return len(set(titles)) / len(titles) >= 0.6


def _date_from(card: Tag) -> datetime | None:
    t = card.find("time")
    if t:
        return parse_date(t.get("datetime") or t.get_text(strip=True))
    m = DATE_RE.search(card.get_text(" ", strip=True)[:600])
    return parse_date(m.group(0)) if m else None


def extract_links_heuristic(html: str, page_url: str, max_items: int = 40) -> list[RawItem]:
    soup = BeautifulSoup(html, "lxml")
    site = _registrable(page_url)
    page_canon = canonicalize_url(page_url)
    page_path = urlparse(page_canon).path.rstrip("/")
    seen: dict[str, RawItem] = {}

    for a in soup.find_all("a", href=True):
        href = a["href"].strip()
        if not href or href.startswith(("#", "mailto:", "tel:", "javascript:")):
            continue
        absolute = urljoin(page_url, href)
        if not absolute.startswith(("http://", "https://")) or _registrable(absolute) != site:
            continue
        canon = canonicalize_url(absolute)
        path = urlparse(canon).path
        if canon == page_canon or path in ("", "/"):
            continue
        lower = path.lower()
        if any(h in lower for h in NON_CONTENT_HINTS):
            continue
        # Prefer links that go deeper than the listing page (e.g. /blog/some-post vs /blog).
        if page_path and not lower.startswith(page_path.lower() + "/") and lower.count("/") < 2:
            continue
        if _in_skipped_region(a):
            continue
        card = _card_for(a)
        title = _title_from(a, card)
        if len(title) < MIN_TITLE_LEN or title.lower() in SKIP_TEXT or title.lower() in PLACEHOLDER_TITLES:
            continue
        if canon in seen:
            if len(title) > len(seen[canon].title or "") and seen[canon].published_at is None:
                seen[canon].title = title
            continue
        seen[canon] = RawItem(url=canon, title=title[:300], published_at=_date_from(card))
        if len(seen) >= max_items * 2:
            break

    items = list(seen.values())
    # Grouping: keep URL shapes that appear at least twice, unless everything is unique.
    shapes: dict[str, int] = {}
    for it in items:
        shape = "/".join(urlparse(it.url).path.split("/")[:2])
        shapes[shape] = shapes.get(shape, 0) + 1
    if shapes and max(shapes.values()) >= 3:
        items = [it for it in items if shapes["/".join(urlparse(it.url).path.split("/")[:2])] >= 2]
    items = items[:max_items]
    return items if title_quality_ok(items) else []


def extract_links_with_recipe(html: str, page_url: str, recipe: dict, max_items: int = 40) -> list[RawItem]:
    soup = BeautifulSoup(html, "lxml")
    site = _registrable(page_url)
    items: list[RawItem] = []
    seen: set[str] = set()
    item_sel = recipe.get("item_selector") or "article"
    link_sel = recipe.get("link_selector") or "a"
    title_sel = recipe.get("title_selector")
    date_sel = recipe.get("date_selector")
    for card in soup.select(item_sel):
        link = card.select_one(link_sel) if link_sel else card.find("a", href=True)
        if not link or not link.get("href"):
            continue
        absolute = urljoin(page_url, link["href"])
        if _registrable(absolute) != site:
            continue
        canon = canonicalize_url(absolute)
        if canon in seen:
            continue
        title_node = card.select_one(title_sel) if title_sel else None
        title = clean_title(title_node.get_text(" ", strip=True)) if title_node else _title_from(link, card)
        if len(title) < 6 or title.lower() in PLACEHOLDER_TITLES:
            continue
        date_node = card.select_one(date_sel) if date_sel else None
        published = (
            parse_date(date_node.get("datetime") or date_node.get_text(strip=True))
            if date_node
            else _date_from(card)
        )
        seen.add(canon)
        items.append(RawItem(url=canon, title=title[:300], published_at=published))
        if len(items) >= max_items:
            break
    return items


def trimmed_html_sample(html: str, limit: int = 12000) -> str:
    """A compact HTML sample for the LLM: main content, no scripts/styles, attributes reduced."""
    soup = BeautifulSoup(html, "lxml")
    for tag in soup(["script", "style", "noscript", "svg", "iframe", "head", "footer", "nav"]):
        tag.decompose()
    keep_attrs = {"href", "class", "datetime", "id"}
    for tag in soup.find_all(True):
        for attr in list(tag.attrs):
            if attr not in keep_attrs:
                del tag.attrs[attr]
            elif attr == "class":
                tag.attrs["class"] = tag.attrs["class"][:2]
    root = soup.find("main") or soup.body or soup
    text = str(root)
    text = re.sub(r"\s+", " ", text)
    return text[:limit]


class HtmlListAdapter:
    kind = "html_list"

    def __init__(self, llm: LLM):
        self._llm = llm

    def fetch(self, ctx: SourceContext) -> AdapterResult:
        res = ctx.get()
        if res.not_modified:
            return AdapterResult(
                http_status=304, not_modified=True, etag=ctx.etag, last_modified=ctx.last_modified
            )
        if not res.ok or not res.body:
            return AdapterResult(http_status=res.status, error=f"HTTP {res.status}")

        html = res.body
        notes: list[str] = []
        config_updates: dict = {}
        recipe = ctx.config.get("recipe")
        items: list[RawItem] = []

        if recipe:
            items = extract_links_with_recipe(html, res.final_url, recipe, ctx.max_items)
            notes.append(f"recipe yielded {len(items)}")
        if len(items) < MIN_YIELD:
            heuristic = extract_links_heuristic(html, res.final_url, ctx.max_items)
            notes.append(f"heuristic yielded {len(heuristic)}")
            if len(heuristic) >= MIN_YIELD:
                items = heuristic
        if len(items) < MIN_YIELD and ctx.config.get("allow_llm_recipe", True) and ctx.session is not None:
            new_recipe = self._derive_recipe_safely(ctx.session, html, res.final_url)
            if new_recipe:
                derived = extract_links_with_recipe(html, res.final_url, new_recipe, ctx.max_items)
                notes.append(f"llm recipe yielded {len(derived)}")
                if len(derived) >= MIN_YIELD:
                    items = derived
                    config_updates["recipe"] = new_recipe
                    config_updates["recipe_derived_at"] = datetime.now(UTC).isoformat()
                    notes.append("structure_changed:recipe_rederived" if recipe else "recipe_learned")
        return AdapterResult(
            items=items,
            http_status=res.status,
            etag=res.etag,
            last_modified=res.last_modified,
            notes=notes,
            config_updates=config_updates,
            page_html=html,
        )

    def _derive_recipe_safely(self, session, html: str, url: str) -> dict | None:
        try:
            return derive_list_recipe(self._llm, session, trimmed_html_sample(html), url)
        except Exception as exc:  # LLM unavailable, budget exhausted, etc.
            log.warning("html_list.recipe_derivation_failed", url=url, error=str(exc))
            return None

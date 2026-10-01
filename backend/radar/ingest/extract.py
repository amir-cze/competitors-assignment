"""Turn fetched HTML into normalized text + metadata."""

from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass
from datetime import UTC, datetime
from urllib.parse import parse_qsl, urlencode, urlparse, urlunparse

import trafilatura
from bs4 import BeautifulSoup
from dateutil import parser as dateparser

TRACKING_PARAMS = {
    "utm_source",
    "utm_medium",
    "utm_campaign",
    "utm_term",
    "utm_content",
    "gclid",
    "fbclid",
    "ref",
    "mc_cid",
    "mc_eid",
}


@dataclass
class ExtractedDoc:
    title: str
    text: str
    published_at: datetime | None
    canonical_url: str
    description: str | None = None


def canonicalize_url(url: str) -> str:
    parsed = urlparse(url.strip())
    query = [
        (k, v)
        for k, v in parse_qsl(parsed.query, keep_blank_values=False)
        if k.lower() not in TRACKING_PARAMS
    ]
    path = parsed.path or "/"
    if path != "/" and path.endswith("/"):
        path = path[:-1]
    return urlunparse((parsed.scheme.lower(), parsed.netloc.lower(), path, "", urlencode(query), ""))


def normalize_text(text: str) -> str:
    text = text.replace("\r", "")
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def content_hash(text: str) -> str:
    collapsed = re.sub(r"\W+", " ", text.lower()).strip()
    return hashlib.sha256(collapsed.encode()).hexdigest()


def parse_date(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        dt = dateparser.parse(value)
    except (ValueError, OverflowError, TypeError):
        return None
    if dt is None:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=UTC)
    return dt.astimezone(UTC)


def _meta(soup: BeautifulSoup, *names: str) -> str | None:
    for name in names:
        tag = soup.find("meta", attrs={"property": name}) or soup.find("meta", attrs={"name": name})
        if tag and tag.get("content"):
            return tag["content"].strip()
    return None


def extract_document(html: str, url: str) -> ExtractedDoc:
    soup = BeautifulSoup(html, "lxml")
    canonical = soup.find("link", rel=lambda v: v and "canonical" in v)
    canonical_url = (
        canonicalize_url(canonical["href"])
        if canonical and canonical.get("href", "").startswith("http")
        else canonicalize_url(url)
    )

    title = _meta(soup, "og:title", "twitter:title") or (
        soup.title.string.strip() if soup.title and soup.title.string else ""
    )
    description = _meta(soup, "og:description", "description", "twitter:description")
    published = parse_date(
        _meta(
            soup,
            "article:published_time",
            "og:article:published_time",
            "datePublished",
            "date",
            "pubdate",
            "publish_date",
        )
    )
    if published is None:
        time_tag = soup.find("time", attrs={"datetime": True})
        if time_tag:
            published = parse_date(time_tag["datetime"])

    text = (
        trafilatura.extract(
            html, url=url, include_comments=False, include_tables=True, favor_recall=True, output_format="txt"
        )
        or ""
    )
    if not text:
        # Fallback: strip boilerplate tags and use body text.
        for tag in soup(["script", "style", "nav", "footer", "header", "noscript", "svg"]):
            tag.decompose()
        body = soup.body or soup
        text = body.get_text("\n")
    text = normalize_text(text)

    if not title and text:
        title = text.split("\n", 1)[0][:200]
    return ExtractedDoc(
        title=title[:500],
        text=text,
        published_at=published,
        canonical_url=canonical_url,
        description=description,
    )


def page_text_for_watch(html: str, url: str) -> str:
    """Text used for change detection. Favors recall so navigation/hero copy is included."""
    soup = BeautifulSoup(html, "lxml")
    for tag in soup(["script", "style", "noscript", "svg", "iframe", "form"]):
        tag.decompose()
    body = soup.body or soup
    lines = [normalize_text(line) for line in body.get_text("\n").split("\n")]
    lines = [line for line in lines if len(line) > 1]
    return "\n".join(lines)

"""Turn a homepage URL into a set of monitorable sources, with a preview the business can understand.

The business user pastes one URL. We look for, in order of reliability:
  feeds (RSS/Atom)  >  HTML listing pages  >  sitemaps  >  pages worth watching for changes
and return candidates with sample titles so the user can confirm with one click.

This is interactive, so it has a time budget: probes run in parallel without the per-host politeness
gate (a one-off burst of ~25 requests), with short timeouts.
"""

from __future__ import annotations

import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import asdict, dataclass, field
from urllib.parse import urljoin, urlparse

import tldextract
from bs4 import BeautifulSoup

from radar.ingest.adapters.feed import looks_like_feed, parse_feed
from radar.ingest.adapters.html_list import extract_links_heuristic
from radar.ingest.adapters.sitemap import is_content_url, parse_sitemap
from radar.ingest.extract import canonicalize_url
from radar.ingest.http import Fetcher, HttpFetcher, sitemaps_from_robots
from radar.logging import get_logger

log = get_logger(__name__)

PROBE_TIMEOUT = 8.0
TIME_BUDGET_SECONDS = 40.0

FEED_PATHS = ("/feed", "/rss.xml", "/feed.xml", "/atom.xml", "/blog/feed", "/blog/rss.xml", "/index.xml")
LISTING_PATHS = (
    "/blog",
    "/news",
    "/newsroom",
    "/press",
    "/press-releases",
    "/insights",
    "/resources/blog",
    "/research",
    "/company/news",
    "/company/blog",
    "/articles",
    "/updates",
    "/announcements",
    "/labs",
    "/resources",
)
WATCH_PATHS = (
    ("/", "Homepage"),
    ("/pricing", "Pricing page"),
    ("/platform", "Platform page"),
    ("/product", "Product page"),
)

# How much we like a listing path as a *news* source. Events and media are noise for most teams.
LISTING_SCORE = {
    "blog": 10,
    "news": 10,
    "newsroom": 10,
    "press": 9,
    "press-releases": 9,
    "announcements": 9,
    "updates": 8,
    "research": 8,
    "labs": 8,
    "insights": 7,
    "articles": 7,
    "resources": 3,
    "events": 0,
    "webinars": 0,
    "videos": 0,
    "podcasts": 0,
    "ebooks": 1,
    "white-papers": 2,
    "case-studies": 2,
}


@dataclass
class SourceCandidate:
    kind: str
    url: str
    label: str
    confidence: float
    sample_titles: list[str] = field(default_factory=list)
    item_count: int = 0
    recommended: bool = False
    note: str | None = None

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class DiscoveryResult:
    homepage_url: str
    site_name: str
    candidates: list[SourceCandidate]
    warnings: list[str] = field(default_factory=list)
    elapsed_ms: int = 0

    def to_dict(self) -> dict:
        return {
            "homepage_url": self.homepage_url,
            "site_name": self.site_name,
            "candidates": [c.to_dict() for c in self.candidates],
            "warnings": self.warnings,
            "elapsed_ms": self.elapsed_ms,
        }


def _registrable(url: str) -> str:
    ext = tldextract.extract(url)
    return f"{ext.domain}.{ext.suffix}" if ext.suffix else ext.domain


def _site_name(soup: BeautifulSoup | None, url: str) -> str:
    if soup is not None:
        og = soup.find("meta", attrs={"property": "og:site_name"})
        if og and og.get("content"):
            return og["content"].strip()
        if soup.title and soup.title.string:
            title = soup.title.string.strip()
            for sep in (" | ", " - ", " – ", " — ", ": "):
                if sep in title:
                    parts = [p.strip() for p in title.split(sep) if p.strip()]
                    if parts:
                        return min(parts, key=len)
            return title[:60]
    host = urlparse(url).netloc.replace("www.", "")
    return host.split(".")[0].capitalize()


def _listing_score(url: str) -> int:
    parts = [p for p in urlparse(url).path.lower().split("/") if p]
    if not parts:
        return 0
    # Use the most specific segment we know, else the first.
    for seg in reversed(parts):
        if seg in LISTING_SCORE:
            return LISTING_SCORE[seg]
    return LISTING_SCORE.get(parts[0], 4)


def _label_for_listing(url: str) -> str:
    parts = [p for p in urlparse(url).path.split("/") if p]
    return (" / ".join(p.replace("-", " ").title() for p in parts) if parts else "Home") + " page"


# --------------------------------------------------------------------------- probes


def _probe_feed(fetcher: Fetcher, url: str) -> SourceCandidate | None:
    res = fetcher.fetch(url, timeout=PROBE_TIMEOUT, polite=False)
    if not res.ok or not looks_like_feed(res.body, res.content_type):
        return None
    items = parse_feed(res.body or "", 10)
    if not items:
        return None
    return SourceCandidate(
        kind="feed",
        url=res.final_url,
        label="RSS/Atom feed",
        confidence=0.95,
        sample_titles=[i.title for i in items[:5] if i.title],
        item_count=len(items),
        note="Feeds are the most reliable source: structured, dated, and rarely change format.",
    )


def _probe_sitemap(fetcher: Fetcher, url: str) -> SourceCandidate | None:
    res = fetcher.fetch(url, timeout=PROBE_TIMEOUT, polite=False)
    if not res.ok or not res.body:
        return None
    head = res.body[:3000]
    if "<urlset" not in head and "<sitemapindex" not in head:
        return None
    entries, children = parse_sitemap(res.body)
    content = [e for e in entries if is_content_url(e.url)]
    for child in children[:6]:
        if not any(h in child.lower() for h in ("post", "blog", "news", "article", "resource", "press")):
            continue
        cres = fetcher.fetch(child, timeout=PROBE_TIMEOUT, polite=False)
        if cres.ok and cres.body:
            centries, _ = parse_sitemap(cres.body)
            content.extend(e for e in centries if is_content_url(e.url))
    if len(content) < 3:
        return None
    sample = [urlparse(e.url).path.rsplit("/", 1)[-1].replace("-", " ")[:80] for e in content[:5]]
    return SourceCandidate(
        kind="sitemap",
        url=res.final_url,
        label="Sitemap (content pages)",
        confidence=0.7,
        sample_titles=sample,
        item_count=len(content),
        note="Sitemaps tell us when pages change but rarely include titles; we fetch each page for details.",
    )


def _probe_listing(fetcher: Fetcher, url: str, site: str) -> SourceCandidate | None:
    res = fetcher.fetch(url, timeout=PROBE_TIMEOUT, polite=False)
    if not res.ok or not res.body or _registrable(res.final_url) != site:
        return None
    if looks_like_feed(res.body, res.content_type):
        return None
    # A listing must still be a listing after redirects (e.g. /news -> /blog is fine, /blog -> /blog/post is not).
    if len([p for p in urlparse(res.final_url).path.split("/") if p]) > 2:
        return None
    items = extract_links_heuristic(res.body, res.final_url, 20)
    if len(items) < 3:
        return None
    return SourceCandidate(
        kind="html_list",
        url=res.final_url,
        label=_label_for_listing(res.final_url),
        confidence=0.6,
        sample_titles=[i.title for i in items[:5] if i.title],
        item_count=len(items),
    )


def _probe_watch(fetcher: Fetcher, url: str, label: str, site: str) -> SourceCandidate | None:
    res = fetcher.fetch(url, timeout=PROBE_TIMEOUT, polite=False)
    if not res.ok or not res.body or _registrable(res.final_url) != site:
        return None
    return SourceCandidate(
        kind="page_watch",
        url=res.final_url,
        label=label,
        confidence=0.5,
        note="We'll tell you when the wording on this page changes.",
    )


# --------------------------------------------------------------------------- main


def discover(homepage_url: str, fetcher: Fetcher | None = None) -> DiscoveryResult:
    fetcher = fetcher or HttpFetcher()
    started = time.monotonic()
    if not homepage_url.startswith(("http://", "https://")):
        homepage_url = "https://" + homepage_url
    warnings: list[str] = []

    requested_origin = f"{urlparse(homepage_url).scheme}://{urlparse(homepage_url).netloc}"
    requested_site = _registrable(homepage_url)
    home = fetcher.fetch(homepage_url, timeout=12.0, polite=False)
    if not home.ok or not home.body:
        raise ValueError(
            f"Could not load {homepage_url} (HTTP {home.status}). Check the address and try again."
        )

    soup = BeautifulSoup(home.body, "lxml")
    # If the homepage now redirects to another company, that is intelligence in itself. Keep probing the
    # original domain (blogs often survive acquisitions) but tell the user what happened.
    if _registrable(home.final_url) != requested_site:
        warnings.append(
            f"{urlparse(homepage_url).netloc} now redirects to {urlparse(home.final_url).netloc}. "
            "This usually means an acquisition or rebrand. We will still look for content on the original domain."
        )
        base = homepage_url
        origin = requested_origin
        site_name = _site_name(None, homepage_url)
        nav_soup = None
    else:
        base = home.final_url
        origin = f"{urlparse(base).scheme}://{urlparse(base).netloc}"
        site_name = _site_name(soup, base)
        nav_soup = soup
    site = requested_site

    feed_urls: list[str] = []
    if nav_soup is not None:
        for link in nav_soup.find_all("link", attrs={"rel": True, "href": True}):
            rel = " ".join(link.get("rel") or []).lower()
            typ = (link.get("type") or "").lower()
            if "alternate" in rel and ("rss" in typ or "atom" in typ or "xml" in typ):
                feed_urls.append(urljoin(base, link["href"]))
    feed_urls += [urljoin(origin, p) for p in FEED_PATHS]
    feed_urls = list(dict.fromkeys(canonicalize_url(u) for u in feed_urls))[:8]

    sitemap_urls = list(dict.fromkeys(sitemaps_from_robots(origin) + [urljoin(origin, "/sitemap.xml")]))[:2]

    # Listing pages: linked-from-homepage first (depth <= 2), then well-known paths.
    nav_links: list[str] = []
    if nav_soup is not None:
        for a in nav_soup.find_all("a", href=True):
            absolute = canonicalize_url(urljoin(base, a["href"]))
            parsed = urlparse(absolute)
            if _registrable(absolute) != site:
                continue
            segments = [p for p in parsed.path.lower().split("/") if p]
            if not segments or len(segments) > 2:
                continue
            if any(
                parsed.path.lower() == p or parsed.path.lower().startswith(p + "/") for p in LISTING_PATHS
            ):
                nav_links.append(absolute)
    listing_urls = list(dict.fromkeys(nav_links + [urljoin(origin, p) for p in LISTING_PATHS]))[:12]
    watch_targets = [(urljoin(origin, p), label) for p, label in WATCH_PATHS]

    candidates: list[SourceCandidate] = []
    with ThreadPoolExecutor(max_workers=8) as pool:
        futures = (
            [pool.submit(_probe_feed, fetcher, u) for u in feed_urls]
            + [pool.submit(_probe_sitemap, fetcher, u) for u in sitemap_urls]
            + [pool.submit(_probe_listing, fetcher, u, site) for u in listing_urls]
            + [pool.submit(_probe_watch, fetcher, u, label, site) for u, label in watch_targets]
        )
        try:
            for fut in as_completed(futures, timeout=TIME_BUDGET_SECONDS):
                try:
                    cand = fut.result()
                except Exception as exc:  # one bad probe must not sink discovery
                    log.warning("discovery.probe_failed", error=str(exc))
                    continue
                if cand:
                    candidates.append(cand)
        except TimeoutError:
            warnings.append("Some checks timed out; the site is slow. You can add more sources later.")
            for fut in futures:
                fut.cancel()

    # Dedupe by URL, keep the highest-confidence kind.
    by_url: dict[str, SourceCandidate] = {}
    for cand in candidates:
        key = canonicalize_url(cand.url)
        if key not in by_url or cand.confidence > by_url[key].confidence:
            by_url[key] = cand

    feeds = sorted((c for c in by_url.values() if c.kind == "feed"), key=lambda c: -c.item_count)
    listings = sorted(
        (c for c in by_url.values() if c.kind == "html_list"),
        key=lambda c: (-_listing_score(c.url), -c.item_count),
    )
    sitemaps = [c for c in by_url.values() if c.kind == "sitemap"]
    watches = [c for c in by_url.values() if c.kind == "page_watch"]

    # Recommendations: one good feed, else up to two news-like listings, else the sitemap. Plus homepage/pricing watch.
    if feeds:
        feeds[0].recommended = True
    else:
        good = [c for c in listings if _listing_score(c.url) >= 5]
        for c in good[:2]:
            c.recommended = True
        if not good and sitemaps:
            sitemaps[0].recommended = True
    for c in watches:
        if c.label in ("Homepage", "Pricing page"):
            c.recommended = True

    if not feeds and not listings and not sitemaps:
        if watches:
            warnings.append(
                "No feed or news page found automatically. You can still watch specific pages for changes."
            )
        else:
            warnings.append(
                "This site may render entirely in the browser. Ask the operator to enable JavaScript rendering for it."
            )

    ordered = feeds + listings + sitemaps + watches
    elapsed = int((time.monotonic() - started) * 1000)
    log.info("discovery.done", url=homepage_url, candidates=len(ordered), elapsed_ms=elapsed)
    return DiscoveryResult(
        homepage_url=base, site_name=site_name, candidates=ordered, warnings=warnings, elapsed_ms=elapsed
    )

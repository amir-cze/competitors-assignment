"""Polite HTTP fetching: per-host serialization + minimum delay, robots.txt, conditional GET."""

from __future__ import annotations

import threading
import time
import urllib.robotparser
from dataclasses import dataclass, field
from functools import lru_cache
from typing import Protocol
from urllib.parse import urlparse

import httpx

from radar.config import get_settings
from radar.logging import get_logger

log = get_logger(__name__)

ACCEPT = (
    "text/html,application/xhtml+xml,application/xml,application/rss+xml,application/atom+xml;q=0.9,*/*;q=0.8"
)


@dataclass
class FetchResult:
    url: str
    final_url: str
    status: int
    body: str | None
    headers: dict[str, str] = field(default_factory=dict)
    not_modified: bool = False
    elapsed_ms: int = 0

    @property
    def ok(self) -> bool:
        return 200 <= self.status < 300

    @property
    def etag(self) -> str | None:
        return self.headers.get("etag")

    @property
    def last_modified(self) -> str | None:
        return self.headers.get("last-modified")

    @property
    def content_type(self) -> str:
        return self.headers.get("content-type", "")


class Fetcher(Protocol):
    """The network boundary. Adapters and discovery only ever talk to this."""

    def fetch(
        self,
        url: str,
        *,
        etag: str | None = None,
        last_modified: str | None = None,
        timeout: float | None = None,
        polite: bool = True,
    ) -> FetchResult: ...

    def fetch_rendered(self, url: str) -> FetchResult: ...


class HttpFetcher:
    """Real implementation: httpx with robots.txt, per-host politeness and optional Playwright rendering."""

    def fetch(
        self,
        url: str,
        *,
        etag: str | None = None,
        last_modified: str | None = None,
        timeout: float | None = None,
        polite: bool = True,
    ) -> FetchResult:
        return fetch(url, etag=etag, last_modified=last_modified, timeout=timeout, polite=polite)

    def fetch_rendered(self, url: str) -> FetchResult:
        return fetch_rendered(url)


class _HostGate:
    """One request at a time per host, with a minimum spacing between requests."""

    def __init__(self, min_delay: float):
        self._min_delay = min_delay
        self._locks: dict[str, threading.Lock] = {}
        self._last: dict[str, float] = {}
        self._guard = threading.Lock()

    def _lock_for(self, host: str) -> threading.Lock:
        with self._guard:
            if host not in self._locks:
                self._locks[host] = threading.Lock()
            return self._locks[host]

    def acquire(self, host: str) -> None:
        self._lock_for(host).acquire()
        last = self._last.get(host, 0.0)
        wait = self._min_delay - (time.monotonic() - last)
        if wait > 0:
            time.sleep(wait)

    def release(self, host: str) -> None:
        self._last[host] = time.monotonic()
        self._lock_for(host).release()


@lru_cache
def _gate() -> _HostGate:
    return _HostGate(get_settings().per_host_min_delay_seconds)


# --------------------------------------------------------------------------- robots.txt

_robots_cache: dict[str, tuple[float, urllib.robotparser.RobotFileParser | None]] = {}
_robots_lock = threading.Lock()
ROBOTS_TTL = 6 * 3600


def _robots_for(scheme: str, host: str) -> urllib.robotparser.RobotFileParser | None:
    key = f"{scheme}://{host}"
    now = time.time()
    with _robots_lock:
        cached = _robots_cache.get(key)
        if cached and now - cached[0] < ROBOTS_TTL:
            return cached[1]
    rp: urllib.robotparser.RobotFileParser | None = urllib.robotparser.RobotFileParser()
    try:
        resp = httpx.get(
            f"{key}/robots.txt",
            timeout=8.0,
            headers={"User-Agent": get_settings().user_agent},
            follow_redirects=True,
        )
        if resp.status_code == 200 and rp is not None:
            rp.parse(resp.text.splitlines())
        else:
            rp = None
    except Exception:
        rp = None
    with _robots_lock:
        _robots_cache[key] = (now, rp)
    return rp


def allowed_by_robots(url: str) -> bool:
    parsed = urlparse(url)
    rp = _robots_for(parsed.scheme, parsed.netloc)
    if rp is None:
        return True
    try:
        return rp.can_fetch(get_settings().user_agent, url) or rp.can_fetch("*", url)
    except Exception:
        return True


def sitemaps_from_robots(base_url: str) -> list[str]:
    parsed = urlparse(base_url)
    rp = _robots_for(parsed.scheme, parsed.netloc)
    if rp is None:
        return []
    try:
        return list(rp.site_maps() or [])
    except Exception:
        return []


# --------------------------------------------------------------------------- fetch


def fetch(
    url: str,
    *,
    etag: str | None = None,
    last_modified: str | None = None,
    timeout: float | None = None,
    respect_robots: bool = True,
    polite: bool = True,
) -> FetchResult:
    """Fetch one URL.

    `polite=True` serializes requests per host with a minimum spacing (the scheduled crawler).
    `polite=False` skips that gate for short interactive bursts such as the discovery preview.
    """
    settings = get_settings()
    host = urlparse(url).netloc
    if respect_robots and not allowed_by_robots(url):
        return FetchResult(
            url=url, final_url=url, status=999, body=None, headers={"x-radar": "robots-disallow"}
        )

    headers = {"User-Agent": settings.user_agent, "Accept": ACCEPT, "Accept-Language": "en-US,en;q=0.9"}
    if etag:
        headers["If-None-Match"] = etag
    if last_modified:
        headers["If-Modified-Since"] = last_modified

    if polite:
        _gate().acquire(host)
    started = time.monotonic()
    try:
        with httpx.Client(timeout=timeout or settings.fetch_timeout_seconds, follow_redirects=True) as client:
            resp = client.get(url, headers=headers)
        elapsed = int((time.monotonic() - started) * 1000)
        lowered = {k.lower(): v for k, v in resp.headers.items()}
        if resp.status_code == 304:
            return FetchResult(
                url=url,
                final_url=str(resp.url),
                status=304,
                body=None,
                headers=lowered,
                not_modified=True,
                elapsed_ms=elapsed,
            )
        body = resp.text if resp.content else ""
        return FetchResult(
            url=url,
            final_url=str(resp.url),
            status=resp.status_code,
            body=body,
            headers=lowered,
            elapsed_ms=elapsed,
        )
    except httpx.HTTPError as exc:
        elapsed = int((time.monotonic() - started) * 1000)
        log.warning("fetch.error", url=url, error=str(exc))
        return FetchResult(
            url=url,
            final_url=url,
            status=0,
            body=None,
            headers={"x-radar-error": str(exc)},
            elapsed_ms=elapsed,
        )
    finally:
        if polite:
            _gate().release(host)


def fetch_rendered(url: str, *, timeout_ms: int = 30000) -> FetchResult:
    """Render with headless Chromium. Only used when a source is flagged requires_js."""
    try:
        from playwright.sync_api import sync_playwright
    except ImportError as exc:  # pragma: no cover - optional dependency
        raise RuntimeError(
            "Playwright not installed. Install with `uv sync --extra js` and `playwright install chromium`."
        ) from exc

    host = urlparse(url).netloc
    _gate().acquire(host)
    started = time.monotonic()
    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            try:
                page = browser.new_page(user_agent=get_settings().user_agent)
                resp = page.goto(url, wait_until="networkidle", timeout=timeout_ms)
                html = page.content()
                status = resp.status if resp else 200
                final_url = page.url
            finally:
                browser.close()
        return FetchResult(
            url=url,
            final_url=final_url,
            status=status,
            body=html,
            headers={"content-type": "text/html; rendered=playwright"},
            elapsed_ms=int((time.monotonic() - started) * 1000),
        )
    finally:
        _gate().release(host)

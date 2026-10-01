from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Protocol

from sqlalchemy.orm import Session

from radar.ingest.http import Fetcher, FetchResult


@dataclass
class SourceContext:
    """Everything an adapter needs, decoupled from the ORM so adapters are testable with fixtures.

    `session` is only present when an adapter may need the database (e.g. to record LLM usage while
    deriving a recipe). Adapters must not write domain rows; that is the pipeline's job.
    """

    url: str
    fetcher: Fetcher
    config: dict = field(default_factory=dict)
    etag: str | None = None
    last_modified: str | None = None
    requires_js: bool = False
    max_items: int = 40
    session: Session | None = None

    def get(self, *, conditional: bool = True) -> FetchResult:
        if self.requires_js:
            return self.fetcher.fetch_rendered(self.url)
        return self.fetcher.fetch(
            self.url,
            etag=self.etag if conditional else None,
            last_modified=self.last_modified if conditional else None,
        )


@dataclass
class RawItem:
    url: str
    title: str | None = None
    published_at: datetime | None = None
    summary: str | None = None
    html: str | None = None  # full content when the source provides it (feeds)


@dataclass
class AdapterResult:
    items: list[RawItem] = field(default_factory=list)
    http_status: int = 0
    not_modified: bool = False
    etag: str | None = None
    last_modified: str | None = None
    notes: list[str] = field(default_factory=list)
    page_text: str | None = None  # page_watch only
    page_html: str | None = None
    config_updates: dict = field(default_factory=dict)  # persisted back onto the source (e.g. recipe)
    error: str | None = None

    @property
    def ok(self) -> bool:
        return self.error is None and (self.not_modified or 200 <= self.http_status < 300)


class Adapter(Protocol):
    kind: str

    def fetch(self, ctx: SourceContext) -> AdapterResult: ...

from __future__ import annotations

from radar.assess.llm import LLM
from radar.ingest.adapters.base import Adapter, AdapterResult, RawItem, SourceContext
from radar.ingest.adapters.feed import FeedAdapter
from radar.ingest.adapters.html_list import HtmlListAdapter
from radar.ingest.adapters.page_watch import PageWatchAdapter
from radar.ingest.adapters.sitemap import SitemapAdapter


class AdapterRegistry:
    """Maps `Source.kind` to an adapter instance. Built once by the container."""

    def __init__(self, llm: LLM):
        self._adapters: dict[str, Adapter] = {
            FeedAdapter.kind: FeedAdapter(),
            SitemapAdapter.kind: SitemapAdapter(),
            HtmlListAdapter.kind: HtmlListAdapter(llm),
            PageWatchAdapter.kind: PageWatchAdapter(),
        }

    def get(self, kind: str) -> Adapter:
        try:
            return self._adapters[kind]
        except KeyError as exc:
            raise ValueError(f"Unknown source kind: {kind}") from exc

    @property
    def kinds(self) -> list[str]:
        return list(self._adapters)


__all__ = ["Adapter", "AdapterRegistry", "AdapterResult", "RawItem", "SourceContext"]

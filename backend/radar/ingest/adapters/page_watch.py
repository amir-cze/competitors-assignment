from __future__ import annotations

from radar.ingest.adapters.base import AdapterResult, SourceContext
from radar.ingest.extract import page_text_for_watch


class PageWatchAdapter:
    """Snapshots a page's visible text. Change detection happens in the pipeline (needs history)."""

    kind = "page_watch"

    def fetch(self, ctx: SourceContext) -> AdapterResult:
        res = ctx.get()
        if res.not_modified:
            return AdapterResult(
                http_status=304, not_modified=True, etag=ctx.etag, last_modified=ctx.last_modified
            )
        if not res.ok or not res.body:
            return AdapterResult(http_status=res.status, error=f"HTTP {res.status}")
        text = page_text_for_watch(res.body, res.final_url)
        return AdapterResult(
            http_status=res.status,
            etag=res.etag,
            last_modified=res.last_modified,
            page_text=text,
            page_html=res.body,
        )

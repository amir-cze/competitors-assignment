from radar.ingest.adapters.base import SourceContext
from radar.ingest.adapters.feed import FeedAdapter, parse_feed
from radar.ingest.adapters.html_list import extract_links_heuristic
from radar.ingest.adapters.page_watch import PageWatchAdapter
from radar.ingest.adapters.sitemap import SitemapAdapter, is_content_url, parse_sitemap
from radar.ingest.http import FetchResult
from tests.fakes import FixtureFetcher

RSS = """<?xml version="1.0"?>
<rss version="2.0">
  <channel>
    <title>Acme Blog</title>
    <item>
      <title>We launched an MCP gateway</title>
      <link>https://acme.test/blog/mcp-gateway</link>
      <pubDate>Mon, 20 Sep 2026 10:00:00 GMT</pubDate>
      <description>Per-tool policies.</description>
    </item>
    <item>
      <title>Join our webinar</title>
      <link>https://acme.test/blog/webinar</link>
    </item>
  </channel>
</rss>
"""

SITEMAP = """<?xml version="1.0"?>
<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">
  <url><loc>https://acme.test/blog/mcp-gateway</loc><lastmod>2026-09-20</lastmod></url>
  <url><loc>https://acme.test/blog</loc><lastmod>2026-09-20</lastmod></url>
  <url><loc>https://acme.test/tag/security</loc><lastmod>2026-09-01</lastmod></url>
  <url><loc>https://acme.test/pricing</loc><lastmod>2026-09-18</lastmod></url>
</urlset>
"""

LISTING = """
<html><body><main>
  <article><h2><a href="/blog/mcp-gateway-launch">We launched an MCP gateway with per-tool policies</a></h2></article>
  <article><h2><a href="/blog/series-b">Acme raises $40M Series B to secure AI agents</a></h2></article>
  <nav><a href="/about">About</a></nav>
</main></body></html>
"""


def test_parse_feed_extracts_items():
    items = parse_feed(RSS)
    assert len(items) == 2
    assert items[0].url.endswith("/blog/mcp-gateway")
    assert "MCP" in (items[0].title or "")


def test_feed_adapter_rejects_html():
    fetcher = FixtureFetcher(pages={"https://acme.test/feed": "<html><body>not a feed</body></html>"})
    result = FeedAdapter().fetch(SourceContext(url="https://acme.test/feed", fetcher=fetcher))
    assert result.error and "not an RSS" in result.error


def test_feed_adapter_respects_not_modified():
    fetcher = FixtureFetcher(
        pages={"https://acme.test/feed": FetchResult(url="https://acme.test/feed", final_url="https://acme.test/feed", status=304, body=None, not_modified=True)}
    )
    result = FeedAdapter().fetch(SourceContext(url="https://acme.test/feed", fetcher=fetcher, etag="abc"))
    assert result.not_modified and result.ok


def test_html_list_heuristic_keeps_article_links():
    items = extract_links_heuristic(LISTING, "https://acme.test/blog")
    urls = {i.url for i in items}
    assert any("mcp-gateway" in u for u in urls)
    assert any("series-b" in u for u in urls)
    assert not any(u.endswith("/about") for u in urls)


def test_sitemap_keeps_content_urls():
    entries, children = parse_sitemap(SITEMAP)
    assert children == []
    content = [e.url for e in entries if is_content_url(e.url)]
    assert "https://acme.test/blog/mcp-gateway" in content
    assert "https://acme.test/tag/security" not in content
    assert "https://acme.test/pricing" not in content

    fetcher = FixtureFetcher(pages={"https://acme.test/sitemap.xml": SITEMAP})
    result = SitemapAdapter().fetch(SourceContext(url="https://acme.test/sitemap.xml", fetcher=fetcher))
    assert result.ok
    assert any("mcp-gateway" in i.url for i in result.items)


def test_page_watch_returns_visible_text():
    html = "<html><body><h1>Total AI Security</h1><p>Govern every agent.</p><footer>© 2026</footer></body></html>"
    fetcher = FixtureFetcher(pages={"https://acme.test": html})
    result = PageWatchAdapter().fetch(SourceContext(url="https://acme.test", fetcher=fetcher))
    assert result.ok
    assert result.page_text and "Total AI Security" in result.page_text
    assert result.page_html == html

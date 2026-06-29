"""
factories.py — single point of truth for building test inputs.
"""
from datetime import datetime, timezone
from unittest.mock import MagicMock

from nexora_crawler.items import NexoraPageItem


def make_request(url: str, meta: dict | None = None):
    from scrapy.http import Request
    return Request(url, meta=meta or {})


def make_full_item(
    url: str = "https://x.com/test",
    title: str = "T",
    author: str = "A",
    framework: str = "next.js",
    theme: str = "dark",
    layout_type: str = "grid",
    has_animations: bool = True,
    fonts=("Inter", "Roboto"),
    html: str = "<html><body><p>hi</p></body></html>",
    canonical: str | None = None,
) -> NexoraPageItem:
    item = NexoraPageItem()
    item["url"] = url
    item["title"] = title
    item["author"] = author
    item["html"] = html
    item["status"] = 200
    item["depth"] = 0
    item["spider_name"] = "nexora"
    item["crawled_at"] = datetime.now(timezone.utc).isoformat()
    item["playwright_used"] = False
    item["styles"] = {
        "framework": framework,
        "theme": theme,
        "layout_type": layout_type,
        "has_animations": has_animations,
        "fonts": list(fonts),
    }
    item["fingerprint"] = "1234"
    item["language_iso"] = "en"
    item["language_confidence"] = 0.99
    item["structured_schema"] = []
    item["social_graphs"] = {}
    item["graph_relations"] = {"canonical_url": canonical or url}
    item["image_assets"] = []
    item["description"] = "Example"
    item["keywords"] = ""
    item["meta_tags"] = {}
    item["headings"] = {"h1": ["Heading"], "h2": [], "h3": []}
    item["images"] = [{"src": "https://x.com/a.png", "alt": "a"}]
    item["internal_links"] = [{"url": "https://x.com/y", "text": "y"}]
    item["word_count_raw"] = 3
    item["clean_text"] = "Hello world"
    item["word_count_clean"] = 2
    item["date"] = ""
    item["language"] = "en"
    item["sitename"] = "x"
    item["tags"] = []
    item["response_time_ms"] = 0
    item["sitemap_lastmod"] = ""
    item["sitemap_priority"] = ""
    item["sitemap_changefreq"] = ""
    item["from_sitemap"] = False
    item["saved_json"] = ""
    item["saved_csv"] = ""
    return item


def make_minimal_item(**overrides) -> NexoraPageItem:
    item = make_full_item(**overrides)
    return item


def make_html_response(url: str, body: str, status: int = 200):
    from scrapy.http import HtmlResponse
    return HtmlResponse(url=url, body=body.encode("utf-8"), status=status)


def make_settings(playwright: bool = False, **extra):
    s = MagicMock()
    s.getbool.side_effect = lambda k, d=False: {"NEXORA_PLAYWRIGHT_ENABLED": playwright}.get(k, d)
    s.get.side_effect = lambda k, d=None: extra.get(k, d)
    return s


def make_crawler(settings_obj=None):
    c = MagicMock()
    c.settings = settings_obj or make_settings()
    return c


def make_spider(urls="https://x.com", **kwargs):
    from nexora_crawler.spiders.nexora_spider import NexoraSpider
    return NexoraSpider(urls=urls, **kwargs)

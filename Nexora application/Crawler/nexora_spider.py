"""
nexora_crawler/spiders/nexora_spider.py
========================================
The main Scrapy spider for Phase 2 multi-page crawling.

Responsibilities:
  1. Accept seed URLs (via command-line or config)
  2. Fetch each page and yield a NexoraPageItem with raw HTML
  3. Follow internal links up to DEPTH_LIMIT
  4. Route JS-heavy domains to Playwright (Phase 3 hook — currently a flag only)
  5. Respect allow/deny domain rules

Usage (from inside crawler/ directory):
  scrapy crawl nexora -a urls="https://example.com,https://realpython.com"
  scrapy crawl nexora -a urls="https://example.com" -a depth=1
  scrapy crawl nexora  # uses DEFAULT_SEED_URLS below

The spider itself never parses HTML — that stays entirely in Phase 1.
It only: fetches → wraps in NexoraPageItem → yields.
The pipeline chain does the rest.
"""

import logging
from datetime import datetime, timezone
from urllib.parse import urlparse

import scrapy
from nexora_crawler.items import NexoraPageItem

log = logging.getLogger("nexora.spider")

# ── Default seeds (used when no -a urls= is provided) ────────────────────────
DEFAULT_SEED_URLS = [
    "https://realpython.com",
    "https://en.wikipedia.org/wiki/Web_scraping",
]

# ── JS-heavy domain rules (Phase 3 hook) ─────────────────────────────────────
# Domains listed here will have meta['playwright'] = True set on their requests.
# In Phase 2 this flag is informational only.
# In Phase 3 the PlaywrightRoutingMiddleware will intercept it.
JS_HEAVY_DOMAINS = {
    "youtube.com",
    "twitter.com",
    "x.com",
    "instagram.com",
    "facebook.com",
    "reddit.com",
    "airbnb.com",
    "linkedin.com",
}


class NexoraSpider(scrapy.Spider):
    name              = "nexora"
    custom_settings   = {
        "DEPTH_LIMIT": 2,   # override per-spider if needed
    }

    # ── Initialisation ────────────────────────────────────────────────────
    def __init__(self, urls: str = "", depth: int = None, *args, **kwargs):
        super().__init__(*args, **kwargs)

        # Accept comma-separated URLs from command line: -a urls="url1,url2"
        if urls:
            self.start_urls = [u.strip() for u in urls.split(",") if u.strip()]
        else:
            self.start_urls = DEFAULT_SEED_URLS

        # Optional depth override: -a depth=1
        if depth is not None:
            self.custom_settings["DEPTH_LIMIT"] = int(depth)

        log.info(f"Seeds: {self.start_urls}")
        log.info(f"Depth limit: {self.custom_settings['DEPTH_LIMIT']}")

    # ── Entry point: build initial requests ──────────────────────────────
    def start_requests(self):
        for url in self.start_urls:
            needs_js = self._needs_playwright(url)
            if needs_js:
                log.info(f"[JS-heavy] flagged for Playwright (Phase 3): {url}")

            yield scrapy.Request(
                url=url,
                callback=self.parse,
                errback=self.handle_error,
                meta={
                    "playwright":    needs_js,   # Phase 3 hook
                    "playwright_used": needs_js,
                    "seed_url":      url,
                },
                dont_filter=False,
            )

    # ── Main parse callback ───────────────────────────────────────────────
    def parse(self, response):
        """
        Called for every successfully fetched page.

        This method does ONE thing: wrap the response in a NexoraPageItem
        and yield it. The pipeline chain handles all extraction and saving.

        Then it follows internal links (within depth limit — Scrapy enforces
        this automatically via DEPTH_LIMIT and the depth meta key).
        """
        url   = response.url
        depth = response.meta.get("depth", 0)

        log.info(f"[depth={depth}] Parsing: {url}")

        # ── Build item ────────────────────────────────────────────────────
        item = NexoraPageItem()
        item["url"]            = url
        item["html"]           = response.text
        item["depth"]          = depth
        item["spider_name"]    = self.name
        item["crawled_at"]     = datetime.now(timezone.utc).isoformat()
        item["playwright_used"] = response.meta.get("playwright_used", False)

        yield item

        # ── Follow internal links ─────────────────────────────────────────
        # response.follow() automatically:
        #   - resolves relative URLs
        #   - respects DEPTH_LIMIT (Scrapy injects depth meta)
        #   - deduplicates via DUPEFILTER
        base_domain = urlparse(url).netloc

        for href in response.css("a::attr(href)").getall():
            # Skip non-page anchors
            if not href or href.startswith(("#", "mailto:", "tel:", "javascript:")):
                continue

            # Only follow links that stay on the same domain
            abs_url = response.urljoin(href)
            if urlparse(abs_url).netloc != base_domain:
                continue

            needs_js = self._needs_playwright(abs_url)
            yield response.follow(
                abs_url,
                callback=self.parse,
                errback=self.handle_error,
                meta={
                    "playwright":     needs_js,
                    "playwright_used": needs_js,
                },
            )

    # ── Error handler ─────────────────────────────────────────────────────
    def handle_error(self, failure):
        """
        Logs failed requests without crashing the crawl.
        Common causes: timeout, 403, 404, SSL error, DNS failure.
        """
        url = failure.request.url
        log.error(f"Request failed [{failure.type.__name__}]: {url}")
        # Yield nothing — Scrapy continues to the next URL in the queue.

    # ── Helpers ───────────────────────────────────────────────────────────
    @staticmethod
    def _needs_playwright(url: str) -> bool:
        """
        Returns True if the URL belongs to a known JS-heavy domain.

        Phase 2: this is informational only (the flag travels through the
                 pipeline but no browser is launched).
        Phase 3: PlaywrightRoutingMiddleware intercepts True-flagged requests.
        """
        host = urlparse(url).netloc.lower()
        # Strip 'www.' prefix for matching
        host = host.removeprefix("www.")
        return host in JS_HEAVY_DOMAINS

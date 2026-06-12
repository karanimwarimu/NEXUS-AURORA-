"""
nexora_crawler/spiders/nexora_spider.py
========================================
Nexora's main Scrapy spider — Phase 2.

DEFAULT BEHAVIOUR: fetches the seed URL only (depth=0).
Crawling is opt-in — pass -a depth=1 or -a crawl=true to follow links.

This prevents the runaway crawl issue where a single site with hundreds
of links (e.g. realpython.com) queues thousands of pages unexpectedly.

Usage:
  # Single page (default — safe)
  scrapy crawl nexora -a urls="https://realpython.com"

  # Follow links one hop (opt-in)
  scrapy crawl nexora -a urls="https://realpython.com" -a depth=1

  # Full crawl up to settings.py DEPTH_LIMIT ceiling
  scrapy crawl nexora -a urls="https://realpython.com" -a crawl=true

The spider never parses HTML — it only fetches and packages.
All extraction happens in the pipeline (Phase 1 functions).
"""

import logging
from datetime import datetime, timezone
from urllib.parse import urlparse

import scrapy
from w3lib.url import canonicalize_url
from nexora_crawler.items import NexoraPageItem

log = logging.getLogger("nexora.spider")

# ── Default seed (used when no -a urls= is passed) ────────────────────────────
DEFAULT_SEED_URLS = [
    "https://realpython.com",
]

# ── JS-heavy domain rules (Phase 3 hook — flag only in Phase 2) ───────────────
JS_HEAVY_DOMAINS = {
    "youtube.com", "twitter.com", "x.com", "instagram.com",
    "facebook.com", "reddit.com", "airbnb.com", "linkedin.com",
}

# ── UTM / tracking params to strip from URLs before queuing ──────────────────
# Fixes assessment issue 2.2 — prevents tracking variants being crawled separately
STRIP_PARAMS = {
    "utm_source", "utm_medium", "utm_campaign", "utm_content", "utm_term",
    "ref", "fbclid", "gclid", "mc_cid", "mc_eid",
}


class NexoraSpider(scrapy.Spider):
    name = "nexora"

    def __init__(
        self,
        urls: str = "",
        depth: int = None,
        crawl: str = "false",
        *args,
        **kwargs,
    ):
        super().__init__(*args, **kwargs)

        # ── Seed URLs ─────────────────────────────────────────────────────
        if urls:
            self.start_urls = [u.strip() for u in urls.split(",") if u.strip()]
        else:
            self.start_urls = DEFAULT_SEED_URLS

        # ── Crawl mode ────────────────────────────────────────────────────
        # crawl=false (default) → depth=0, no link following
        # crawl=true            → use depth argument (default 1 if not set)
        # depth=N               → explicit depth, implies crawl=true
        crawl_enabled = crawl.lower() in ("true", "1", "yes")

        if depth is not None:
            self._depth = int(depth)
            crawl_enabled = True
        elif crawl_enabled:
            self._depth = 1   # sensible default when crawl=true but no depth given
        else:
            self._depth = 0   # single page — the safe default

        # Enforce depth via custom_settings so it takes effect for THIS run.
        # This fixes the assessment bug where -a depth=1 was ignored because
        # settings.py DEPTH_LIMIT=2 was the actual ceiling Scrapy used.
        self.custom_settings = {"DEPTH_LIMIT": self._depth}

        self._crawl_enabled = crawl_enabled

        log.info(f"Mode     : {'crawl' if crawl_enabled else 'single-page'}")
        log.info(f"Seeds    : {self.start_urls}")
        log.info(f"Depth    : {self._depth}")

    # ── Entry point ───────────────────────────────────────────────────────────
    def start_requests(self):
        for url in self.start_urls:
            url = self._canonicalize(url)
            needs_js = self._needs_playwright(url)
            if needs_js:
                log.info(f"[JS-heavy] flagged for Phase 3 Playwright: {url}")

            yield scrapy.Request(
                url=url,
                callback=self.parse,
                errback=self.handle_error,
                meta={
                    "playwright":      needs_js,
                    "playwright_used": needs_js,
                    "seed_url":        url,
                },
            )

    # ── Parse callback ────────────────────────────────────────────────────────
    def parse(self, response):
        url   = response.url
        depth = response.meta.get("depth", 0)

        log.info(f"[depth={depth}] Parsed: {url}")

        # ── Yield item — pipeline does all the extraction ─────────────────
        item = NexoraPageItem()
        item["url"]             = url
        item["html"]            = response.text
        item["depth"]           = depth
        item["spider_name"]     = self.name
        item["crawled_at"]      = datetime.now(timezone.utc).isoformat()
        item["playwright_used"] = response.meta.get("playwright_used", False)

        yield item

        # ── Link following — only when crawl mode is active ───────────────
        if not self._crawl_enabled:
            return  # single-page mode — stop here

        base_domain = urlparse(url).netloc

        for href in response.css("a::attr(href)").getall():
            if not href or href.startswith(("#", "mailto:", "tel:", "javascript:")):
                continue

            abs_url = self._canonicalize(response.urljoin(href))

            # Stay on same domain (fixes assessment issue 2.4 — offsite leaking)
            if urlparse(abs_url).netloc != base_domain:
                continue

            needs_js = self._needs_playwright(abs_url)
            yield response.follow(
                abs_url,
                callback=self.parse,
                errback=self.handle_error,
                meta={
                    "playwright":      needs_js,
                    "playwright_used": needs_js,
                },
            )

    # ── Error handler ─────────────────────────────────────────────────────────
    def handle_error(self, failure):
        log.error(f"Request failed [{failure.type.__name__}]: {failure.request.url}")

    # ── Helpers ───────────────────────────────────────────────────────────────
    @staticmethod
    def _canonicalize(url: str) -> str:
        """
        Strip tracking parameters and normalise URL before queuing.
        Fixes assessment issue 2.2 — prevents UTM variants being treated
        as separate pages.
        """
        from urllib.parse import urlparse, urlencode, parse_qs, urlunparse
        parsed = urlparse(url)
        params = {
            k: v for k, v in parse_qs(parsed.query).items()
            if k.lower() not in STRIP_PARAMS
        }
        clean = parsed._replace(query=urlencode(params, doseq=True), fragment="")
        return urlunparse(clean)

    @staticmethod
    def _needs_playwright(url: str) -> bool:
        host = urlparse(url).netloc.lower().removeprefix("www.")
        return host in JS_HEAVY_DOMAINS

"""
nexora_crawler/spiders/nexora_spider.py
========================================
Nexora main spider — Phase 2.5

Depth Strategy Mapping (user-facing):
  1. "Just this page"          → depth=0, single-page
  2. "This page + linked"      → depth=1, multi-page
  3. "The whole website"       → auto-detect sitemap, fallback depth=3
  4. "Everything connected"    → depth=5, domain-locked

Modes
-----
  sitemap    -a sitemap="https://example.com/sitemap.xml"
  auto       -a urls="https://example.com" -a strategy="whole-website"
  multi-page -a urls="https://example.com" -a depth=2
  single-page (default)

Debug
-----
  scrapy crawl nexora -a urls="..." -a strategy="whole-website" --loglevel=INFO
"""

import logging
from datetime import datetime, timezone
from urllib.parse import urlparse

import scrapy
from parsel import Selector

from nexora_crawler.items import NexoraPageItem


logger = logging.getLogger("nexora.spider")

# ── User-facing strategy → internal mapping ──────────────────────────────
STRATEGY_MAP = {
    "single-page":      {"depth": 0, "mode": "single-page", "auto_sitemap": False, "domain_lock": False},
    "linked-pages":     {"depth": 1, "mode": "multi-page",  "auto_sitemap": False, "domain_lock": False},
    "whole-website":    {"depth": 3, "mode": "auto",        "auto_sitemap": True,  "domain_lock": False},
    "everything":       {"depth": 5, "mode": "multi-page",  "auto_sitemap": False, "domain_lock": True},
}

# Backwards-compat: numeric depth still works
DEPTH_PRESETS = {
    0: "single-page",
    1: "linked-pages",
    3: "whole-website",
    5: "everything",
}


class NexoraSpider(scrapy.Spider):
    name = "nexora"

    handle_httpstatus_list = [301, 302]

    # ------------------------------------------------------------------ #
    # Init                                                                 #
    # ------------------------------------------------------------------ #
    def __init__(
        self,
        urls: str = "",
        sitemap: str = "",
        depth: int = 0,
        strategy: str = "",     # NEW: user-friendly strategy name
        max_pages: int = 1000,  # NEW: safety cap
        *args,
        **kwargs,
    ):
        super().__init__(*args, **kwargs)

        self.seeds = [u.strip() for u in urls.split(",") if u.strip()]
        self.raw_depth = int(depth)
        self.raw_strategy = strategy.strip().lower()
        self.max_pages = int(max_pages)
        self.pages_crawled = 0

        # Resolve strategy
        self._resolve_strategy(sitemap)

        logger.info("Mode      : %s", self.mode)
        logger.info("Strategy  : %s", self.strategy_name)
        logger.info("Seeds     : %s", self.seeds)
        logger.info("Depth     : %s", self.max_depth)
        logger.info("Max pages : %s", self.max_pages)
        logger.info("Domain lock: %s", self.domain_lock)
        if self.sitemap_url:
            logger.info("Sitemap   : %s", self.sitemap_url)

    def _resolve_strategy(self, explicit_sitemap: str):
        """Resolve user input into internal mode/depth/settings."""
        # Explicit sitemap always wins
        if explicit_sitemap:
            self.mode = "sitemap"
            self.sitemap_url = explicit_sitemap.strip()
            self.strategy_name = "explicit-sitemap"
            self.max_depth = 0
            self.domain_lock = False
            return

        # Strategy keyword takes precedence over raw depth
        if self.raw_strategy and self.raw_strategy in STRATEGY_MAP:
            cfg = STRATEGY_MAP[self.raw_strategy]
            self.mode = cfg["mode"]
            self.max_depth = cfg["depth"]
            self.auto_sitemap = cfg["auto_sitemap"]
            self.domain_lock = cfg["domain_lock"]
            self.strategy_name = self.raw_strategy
            self.sitemap_url = ""
            return

        # Backwards-compat: depth-only mode
        if self.raw_depth > 0:
            self.mode = "multi-page"
            self.max_depth = self.raw_depth
            self.strategy_name = DEPTH_PRESETS.get(self.raw_depth, f"depth-{self.raw_depth}")
            self.auto_sitemap = False
            self.domain_lock = False
            self.sitemap_url = ""
            return

        # Default: single-page
        self.mode = "single-page"
        self.max_depth = 0
        self.strategy_name = "single-page"
        self.auto_sitemap = False
        self.domain_lock = False
        self.sitemap_url = ""

    # ------------------------------------------------------------------ #
    # start() — Scrapy 2.16+ entry point                                  #
    # ------------------------------------------------------------------ #
    async def start(self):
        """
        Scrapy 2.13+ calls start() exclusively.
        MUST be async — Scrapy 2.16 wraps this in 'async for'.
        """
        count = 0

        # ── Auto-detect sitemap for "whole-website" strategy ────────────
        if self.mode == "auto" and self.auto_sitemap and self.seeds:
            seed = self.seeds[0]
            discovered = await self._try_discover_sitemap(seed)
            if discovered:
                self.mode = "sitemap"
                self.sitemap_url = discovered[0]
                logger.info("🗺️  Auto-detected sitemap — switching to sitemap mode")
            else:
                self.mode = "multi-page"
                logger.info("🔗 No sitemap found — falling back to link-following (depth=%s)", self.max_depth)

        # ── Sitemap mode ──────────────────────────────────────────────────
        if self.mode == "sitemap":
            logger.debug("[start] dispatching sitemap fetch → %s", self.sitemap_url)
            yield scrapy.Request(
                self.sitemap_url,
                callback=self.parse_sitemap,
                errback=self.on_error,
                dont_filter=True,
                meta={"from_sitemap": True, "depth": 0},
            )
            count = 1

        # ── Single / Multi-page mode ────────────────────────────────────
        elif self.mode in ("single-page", "multi-page"):
            for url in self.seeds:
                logger.debug("[start] dispatching seed → %s", url)
                yield scrapy.Request(
                    url,
                    callback=self.parse_page,
                    errback=self.on_error,
                    meta={"depth": 0},
                )
                count += 1

        else:
            logger.error("[start] unknown mode %r — 0 requests generated", self.mode)

        logger.debug("[start] yielded %d request(s)", count)

    # ------------------------------------------------------------------ #
    # Sitemap auto-discovery                                              #
    # ------------------------------------------------------------------ #
    async def _try_discover_sitemap(self, url: str) -> list[str]:
        """Async sitemap discovery using SitemapDetector."""
        try:
            from nexora_crawler.sitemap_detector import SitemapDetector
            detector = SitemapDetector()
            await detector.__aenter__()
            try:
                return await detector.discover(url)
            finally:
                await detector.__aexit__(None, None, None)
        except Exception as exc:
            logger.warning("Sitemap discovery failed: %s", exc)
            return []

    # ------------------------------------------------------------------ #
    # Sitemap parsing                                                      #
    # ------------------------------------------------------------------ #
    def parse_sitemap(self, response):
        """
        Handle both sitemap index (<sitemapindex>) and leaf (<urlset>).
        Uses local-name() XPath so namespace prefixes don't matter.
        """
        try:
            sel = Selector(text=response.text, type="xml")
        except Exception as exc:
            logger.error("[sitemap] XML parse failed at %s: %s", response.url, exc)
            return

        # Sitemap index — recurse into sub-sitemaps
        sub_sitemaps = sel.xpath(
            "//*[local-name()='sitemap']/*[local-name()='loc']/text()"
        ).getall()
        if sub_sitemaps:
            logger.info("[sitemap-index] %d sub-sitemaps found at %s",
                        len(sub_sitemaps), response.url)
            for url in sub_sitemaps:
                logger.debug("[sitemap-index] → %s", url.strip())
                yield scrapy.Request(
                    url.strip(),
                    callback=self.parse_sitemap,
                    errback=self.on_error,
                    dont_filter=True,
                    meta={"from_sitemap": True, "depth": 0},
                )
            return

        # Leaf urlset — extract page URLs
        page_urls = sel.xpath(
            "//*[local-name()='url']/*[local-name()='loc']/text()"
        ).getall()
        logger.info("[sitemap-leaf] %d URLs to crawl from %s",
                    len(page_urls), response.url)

        # Safety cap for sitemap mode
        if len(page_urls) > self.max_pages:
            logger.warning(
                "[sitemap] %d URLs found, capping to max_pages=%d",
                len(page_urls), self.max_pages,
            )
            page_urls = page_urls[:self.max_pages]

        for url in page_urls:
            logger.debug("[sitemap-leaf] → %s", url.strip())
            yield scrapy.Request(
                url.strip(),
                callback=self.parse_page,
                errback=self.on_error,
                meta={"depth": 0},
            )

        if not sub_sitemaps and not page_urls:
            logger.warning("[sitemap] no URLs found in %s — body preview: %s",
                           response.url, response.text[:200])

    # ------------------------------------------------------------------ #
    # Page parsing                                                         #
    # ------------------------------------------------------------------ #
    def parse_page(self, response):
        current_depth = response.meta.get("depth", 0)
        domain = urlparse(response.url).netloc
        seed_domain = urlparse(self.seeds[0]).netloc if self.seeds else domain

        logger.debug("[page] depth=%d status=%d → %s",
                     current_depth, response.status, response.url)

        # Safety cap
        self.pages_crawled += 1
        if self.pages_crawled > self.max_pages:
            logger.warning("[page] Max pages cap (%d) reached — stopping.", self.max_pages)
            return

        yield NexoraPageItem(
            url=response.url,
            status=response.status,
            html=response.text,
            depth=current_depth,
            spider_name=self.name,
            crawled_at=datetime.now(timezone.utc).isoformat(),
            playwright_used=False,
        )

        # Follow internal links in multi-page mode
        if self.mode == "multi-page" and current_depth < self.max_depth:
            followed = 0
            for href in response.css("a::attr(href)").getall():
                abs_url = response.urljoin(href)
                link_domain = urlparse(abs_url).netloc

                # Domain lock for "everything connected" strategy
                if self.domain_lock and link_domain != seed_domain:
                    continue

                yield scrapy.Request(
                    abs_url,
                    callback=self.parse_page,
                    errback=self.on_error,
                    meta={"depth": current_depth + 1},
                )
                followed += 1
            logger.debug("[page] followed %d internal links", followed)

    # ------------------------------------------------------------------ #
    # Error handler                                                        #
    # ------------------------------------------------------------------ #
    def on_error(self, failure):
        logger.error("[error] %s — %s", failure.request.url, failure.type.__name__)

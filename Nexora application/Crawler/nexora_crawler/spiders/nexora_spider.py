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

import ipaddress
import logging
from datetime import datetime, timezone
from urllib.parse import urlparse

import scrapy
from parsel import Selector
from scrapy.exceptions import CloseSpider

from nexora_crawler.items import NexoraPageItem


logger = logging.getLogger("nexora.spider")

# ── User-facing strategy → internal mapping ──────────────────────────────
STRATEGY_MAP = {
    "single-page":      {"depth": 0, "mode": "single-page", "auto_sitemap": False, "domain_lock": False},
    "linked-pages":     {"depth": 1, "mode": "multi-page",  "auto_sitemap": False, "domain_lock": False},
    "whole-website":    {"depth": 3, "mode": "auto",        "auto_sitemap": True,  "domain_lock": True},
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

    @staticmethod
    def _is_private_or_local_host(hostname: str) -> bool:
        if not hostname:
            return True

        host = hostname.strip().lower()
        if host in {"localhost", "localhost.localdomain"} or host.endswith(".local"):
            return True

        try:
            ip = ipaddress.ip_address(host)
        except ValueError:
            return False

        return (
            ip.is_private
            or ip.is_loopback
            or ip.is_link_local
            or ip.is_multicast
            or ip.is_reserved
            or ip.is_unspecified
        )

    def _is_allowed_url(self, url: str) -> bool:
        parsed = urlparse(url)
        if parsed.scheme not in {"http", "https"}:
            return False

        hostname = parsed.hostname or ""
        if not hostname:
            return False

        return not self._is_private_or_local_host(hostname)

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
        self._update_allowed_domains()

        logger.info("Mode      : %s", self.mode)
        logger.info("Strategy  : %s", self.strategy_name)
        logger.info("Seeds     : %s", self.seeds)
        logger.info("Depth     : %s", self.max_depth)
        logger.info("Max pages : %s", self.max_pages)
        logger.info("Domain lock: %s", self.domain_lock)
        logger.info("Allowed domains: %s", self.allowed_domains)
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

    def _update_allowed_domains(self):
        """Maintain allowed_domains from seed URL(s) and sitemap URL(s)."""
        domains = set()
        for url in self.seeds:
            host = urlparse(url).hostname
            if host:
                domains.add(host)
        if getattr(self, "sitemap_url", None):
            host = urlparse(self.sitemap_url).hostname
            if host:
                domains.add(host)

        self.allowed_domains = sorted(domains)
        if not self.allowed_domains:
            self.allowed_domains = []

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
                self._update_allowed_domains()
                logger.info("🗺️  Auto-detected sitemap — switching to sitemap mode")
            else:
                self.mode = "multi-page"
                logger.info("🔗 No sitemap found — falling back to link-following (depth=%s)", self.max_depth)

        # ── Sitemap mode ──────────────────────────────────────────────────
        if self.mode == "sitemap":
            if not self._is_allowed_url(self.sitemap_url):
                logger.warning("[start] skipping disallowed sitemap URL: %s", self.sitemap_url)
                return
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
                if not self._is_allowed_url(url):
                    logger.warning("[start] skipping disallowed seed URL: %s", url)
                    continue
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

        # Leaf urlset — extract page URLs with optional sitemap metadata
        # Using parsel Selector with local-name() XPath for namespace-agnostic extraction
        url_nodes = sel.xpath("//*[local-name()='url']")
        logger.info("[sitemap-leaf] %d URLs to crawl from %s",
                    len(url_nodes), response.url)

        if not url_nodes:
            # Fallback: direct text extraction if node-level parsing fails
            page_urls = sel.xpath(
                "//*[local-name()='url']/*[local-name()='loc']/text()"
            ).getall()
            for url in page_urls[:self.max_pages]:
                url = url.strip()
                if not self._is_allowed_url(url):
                    logger.debug("[sitemap] skipping disallowed fallback URL: %s", url)
                    continue
                logger.debug("[sitemap-leaf] → %s", url)
                yield scrapy.Request(
                    url,
                    callback=self.parse_page,
                    errback=self.on_error,
                    meta={"depth": 0, "from_sitemap": True},
                )
            logger.warning("[sitemap] extracted URLs via fallback — no metadata available")
            return

        entries = []
        for node in url_nodes:
            loc = node.xpath("*[local-name()='loc']/text()").get("")
            if not loc:
                continue
            loc = loc.strip()
            if not self._is_allowed_url(loc):
                logger.debug("[sitemap] skipping disallowed URL: %s", loc)
                continue

            # Extract optional sitemap metadata
            meta = {
                "depth": 0,
                "from_sitemap": True,
            }

            lastmod = node.xpath("*[local-name()='lastmod']/text()").get("")
            if lastmod:
                meta["sitemap_lastmod"] = lastmod.strip()

            priority = node.xpath("*[local-name()='priority']/text()").get("")
            if priority:
                meta["sitemap_priority"] = priority.strip()

            changefreq = node.xpath("*[local-name()='changefreq']/text()").get("")
            if changefreq:
                meta["sitemap_changefreq"] = changefreq.strip()

            entries.append((loc.strip(), meta))

        if not entries:
            logger.warning("[sitemap] no URLs found in %s — body preview: %s",
                           response.url, response.text[:200])
            return

        # Safety cap
        if len(entries) > self.max_pages:
            logger.warning(
                "[sitemap] %d URLs found, capping to max_pages=%d",
                len(entries), self.max_pages,
            )
            entries = entries[:self.max_pages]

        for url, meta in entries:
            logger.debug("[sitemap-leaf] → %s (lastmod=%s, priority=%s, changefreq=%s)",
                         url, meta.get("sitemap_lastmod", "—"),
                         meta.get("sitemap_priority", "—"),
                         meta.get("sitemap_changefreq", "—"))
            yield scrapy.Request(
                url,
                callback=self.parse_page,
                errback=self.on_error,
                meta=meta,
            )

        # Note: no "page_urls" check needed here — the node-based parsing above
        # already handles the case where no URLs were found

    # ------------------------------------------------------------------ #
    # Page parsing                                                         #
    # ------------------------------------------------------------------ #
    def parse_page(self, response):
        current_depth = response.meta.get("depth", 0)
        domain = urlparse(response.url).hostname or ""
        seed_domain = urlparse(self.seeds[0]).hostname if self.seeds else domain

        logger.debug("[page] depth=%d status=%d → %s",
                     current_depth, response.status, response.url)

        # Safety cap: accept pages only until max_pages is reached, then stop.
        if self.pages_crawled >= self.max_pages:
            logger.warning("[page] Max pages cap (%d) reached — rejecting %s", self.max_pages, response.url)
            return

        self.pages_crawled += 1

        # Detect if Playwright was used by checking request meta
        # DynamicDetectionMiddleware sets playwright=True if rendering was needed
        pw_used = bool(response.meta.get("playwright", False))

        yield NexoraPageItem(
            url=response.url,
            status=response.status,
            html=response.text,
            depth=current_depth,
            spider_name=self.name,
            crawled_at=datetime.now(timezone.utc).isoformat(),
            playwright_used=pw_used,
        )

        if self.pages_crawled >= self.max_pages:
            logger.info("[page] max_pages reached (%d) — closing spider", self.max_pages)
            raise CloseSpider("max_pages_reached")

        # Follow internal links in multi-page mode
        if self.mode == "multi-page" and current_depth < self.max_depth:
            followed = 0
            for href in response.css("a::attr(href)").getall():
                abs_url = response.urljoin(href)
                if not self._is_allowed_url(abs_url):
                    logger.debug("[page] skipping disallowed link: %s", abs_url)
                    continue
                parsed = urlparse(abs_url)
                link_domain = parsed.hostname or ""

                # Domain lock for "everything connected" and "whole-website" strategies
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

"""
nexora_crawler/spiders/nexora_spider.py
========================================
Nexora main spider — Phase 2.

Modes
-----
  sitemap    -a sitemap="https://example.com/sitemap.xml"
  multi-page -a urls="https://example.com" -a depth=2
  single-page (default when seeds provided without depth)

Debug
-----
  scrapy crawl nexora -a sitemap="..." --loglevel=DEBUG
  → logs every request dispatched, each sitemap URL discovered,
    and exactly how many requests were yielded from start().

Phase 3 hook
------------
  The `playwright` meta flag is already wired into _make_page_request().
  Uncomment PlaywrightRoutingMiddleware in settings.py when ready.
"""

import logging
from datetime import datetime, timezone
from urllib.parse import urlparse

import scrapy
from parsel import Selector

from nexora_crawler.items import NexoraPageItem


logger = logging.getLogger("nexora.spider")


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
        *args,
        **kwargs,
    ):
        super().__init__(*args, **kwargs)

        self.seeds = [u.strip() for u in urls.split(",") if u.strip()]

        if sitemap:
            self.mode = "sitemap"
            self.sitemap_url = sitemap.strip()
        elif self.seeds and int(depth) > 0:
            self.mode = "multi-page"
            self.sitemap_url = ""
        else:
            self.mode = "single-page"
            self.sitemap_url = ""

        self.max_depth = int(depth)

        logger.info("Mode     : %s", self.mode)
        logger.info("Seeds    : %s", self.seeds)
        logger.info("Depth    : %s", self.max_depth)
        if self.sitemap_url:
            logger.info("Sitemap  : %s", self.sitemap_url)

    # ------------------------------------------------------------------ #
    # start() — Scrapy 2.13+ entry point                                  #
    # ------------------------------------------------------------------ #
    async def start(self):
        """
        Scrapy 2.13+ calls start() exclusively; start_requests() is no
        longer invoked by the engine in 2.16+.

        MUST be async — Scrapy 2.16 wraps this in 'async for' and expects
        an async generator (object with __aiter__). Using 'async def' with
        'yield' creates an async generator automatically.
        """
        count = 0

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
    # Sitemap parsing                                                      #
    # ------------------------------------------------------------------ #
    def parse_sitemap(self, response):
        """
        Handle both sitemap index (<sitemapindex>) and leaf (<urlset>).
        Uses local-name() XPath so namespace prefixes don't matter.

        WHY explicit Selector(type="xml"):
        response.xpath() uses the response Content-Type to pick a parser.
        Sites like GitHub serve sitemaps with unexpected Content-Types
        (text/plain, application/octet-stream, even text/html), which
        causes parsel/lxml to pick the HTML parser → XMLSyntaxError.
        Forcing type="xml" bypasses Content-Type entirely.
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

        logger.debug("[page] depth=%d status=%d → %s",
                     current_depth, response.status, response.url)

        # Yield a proper NexoraPageItem instead of a plain dict.
        # This ensures all fields are validated and pipelines receive
        # the correct item type with all expected attributes.
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
                if urlparse(abs_url).netloc == domain:
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

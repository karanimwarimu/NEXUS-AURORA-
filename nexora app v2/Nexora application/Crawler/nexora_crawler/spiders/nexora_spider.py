"""
nexora_crawler/spiders/nexora_spider.py
========================================
Nexora's main Scrapy spider — Phase 2.

DEFAULT BEHAVIOUR: fetches the seed URL only (depth=0).
Crawling is opt-in — pass -a depth=1 or -a crawl=true to follow links.

Sitemap mode: pass -a sitemap="https://.../sitemap.xml" to crawl from sitemap.
Auto-discovery: pass -a auto_sitemap=true to discover sitemap from seed domain.

Usage:
  # Single page (default — safe)
  scrapy crawl nexora -a urls="https://realpython.com"

  # Follow links one hop (opt-in)
  scrapy crawl nexora -a urls="https://realpython.com" -a depth=1

  # Sitemap mode (explicit sitemap URL)
  scrapy crawl nexora -a sitemap="https://www.bbc.com/sitemap.xml"

  # Auto-discovery mode (find sitemap from seed)
  scrapy crawl nexora -a urls="https://www.bbc.com" -a auto_sitemap=true

  # Full crawl up to settings.py DEPTH_LIMIT ceiling
  scrapy crawl nexora -a urls="https://realpython.com" -a crawl=true
"""

import logging
from datetime import datetime, timezone
from urllib.parse import urlparse

import scrapy
from w3lib.url import canonicalize_url
from nexora_crawler.items import NexoraPageItem

log = logging.getLogger("nexora.spider")

DEFAULT_SEED_URLS = []

JS_HEAVY_DOMAINS = {
    "youtube.com", "twitter.com", "x.com", "instagram.com",
    "facebook.com", "reddit.com", "airbnb.com", "linkedin.com",
}

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
        sitemap: str = "",
        auto_sitemap: str = "false",
        *args,
        **kwargs,
    ):
        super().__init__(*args, **kwargs)

        # Store sitemap URL (explicit or auto-discover later)
        self.sitemap_url = sitemap.strip() if sitemap else None
        self.auto_sitemap = auto_sitemap.lower() in ("true", "1", "yes")

        # Seed URLs
        if urls:
            self.start_urls = [u.strip() for u in urls.split(",") if u and u.strip()]
        else:
            self.start_urls = list(DEFAULT_SEED_URLS)

        # Crawl mode logic
        crawl_enabled = crawl.lower() in ("true", "1", "yes")

        if depth is not None:
            self._depth = int(depth)
            crawl_enabled = self._depth > 0
        elif crawl_enabled:
            self._depth = 1
        else:
            self._depth = 0

        if self._depth <= 0:
            crawl_enabled = False

        self.custom_settings = {"DEPTH_LIMIT": self._depth}
        self._crawl_enabled = crawl_enabled

        log.info(f"Mode     : {'crawl' if crawl_enabled else 'single-page'}")
        log.info(f"Seeds    : {self.start_urls}")
        log.info(f"Depth    : {self._depth}")
        if self.sitemap_url:
            log.info(f"Sitemap  : {self.sitemap_url}")
        if self.auto_sitemap:
            log.info(f"Auto-sitemap discovery enabled")

    def start_requests(self):
        # ── Mode 1: Explicit sitemap URL ──────────────────────────────────
        if self.sitemap_url:
            log.info(f"[sitemap] Starting sitemap crawl from: {self.sitemap_url}")

            from Extractor.sitemap_parser import crawl_sitemap_index, sitemap_to_requests

            try:
                urls = crawl_sitemap_index(self.sitemap_url, max_depth=2)
                log.info(f"[sitemap] Discovered {len(urls)} URLs from {self.sitemap_url}")

                if urls:
                    log.info(f"[sitemap] Scheduling up to 1000 requests from sitemap")
                    for req in sitemap_to_requests(urls, self, max_urls=1000):
                        yield req
                    return
                else:
                    log.warning("[sitemap] No URLs found from sitemap")
            except Exception as e:
                log.error(f"[sitemap] Failed to process sitemap: {e}")

        # ── Mode 2: Auto-discovery from seed domain ───────────────────────
        if self.auto_sitemap and self.start_urls:
            from Extractor.sitemap_parser import discover_sitemap_urls, crawl_sitemap_index, sitemap_to_requests

            seed = self.start_urls[0]
            log.info(f"[auto-sitemap] Discovering sitemap for: {seed}")

            try:
                discovered = discover_sitemap_urls(seed)

                if discovered:
                    log.info(f"[auto-sitemap] Discovered candidates: {discovered[:3]}")
                    urls = crawl_sitemap_index(seed, max_depth=2)

                    if urls:
                        log.info(f"[auto-sitemap] Yielding {len(urls)} URLs from sitemap")
                        for req in sitemap_to_requests(urls, self, max_urls=1000):
                            yield req
                        return
                    else:
                        log.info("[auto-sitemap] No URLs found — using seed crawling")
                else:
                    log.info("[auto-sitemap] No sitemap discovered — using seed crawling")
            except Exception as e:
                log.error(f"[auto-sitemap] Failed: {e}")

        # ── Mode 3: Normal seed-based crawling ────────────────────────────
        for url in self.start_urls:
            if not url:
                continue
            url = self._canonicalize(url)
            needs_js = self._needs_playwright(url)

            if needs_js:
                log.info(f"[JS-heavy] flagged for Phase 3 Playwright: {url}")

            yield scrapy.Request(
                url=url,
                callback=self.parse,
                errback=self.handle_error,
                meta={
                    "playwright": needs_js,
                    "playwright_used": needs_js,
                    "seed_url": url,
                    "depth": 0,
                },
            )

        # ── Mode 4: Sitemap discovery when crawling enabled ──────────────
        if not self._crawl_enabled or self._depth <= 0:
            return

        # Only discover sitemap for additional URLs if not already in sitemap mode
        if self.sitemap_url or self.auto_sitemap:
            return  # Already handled above

        sitemap_url_cap = 50
        seed_domains = {urlparse(u).netloc for u in self.start_urls if u}

        for domain in seed_domains:
            if not domain:
                continue

            sitemap_url = f"https://{domain}/sitemap.xml"
            for item_url in self._discover_urls_from_sitemap(sitemap_url, limit=sitemap_url_cap):
                item_url = self._canonicalize(item_url)

                if urlparse(item_url).netloc != domain:
                    continue

                needs_js = self._needs_playwright(item_url)
                yield scrapy.Request(
                    url=item_url,
                    callback=self.parse,
                    errback=self.handle_error,
                    meta={
                        "depth": 0,
                        "playwright": needs_js,
                        "playwright_used": needs_js,
                        "seed_url": item_url,
                    },
                )

    def parse(self, response):
        url = response.url
        depth = response.meta.get("depth", 0) or 0

        log.info(f"[depth={depth}] Parsed: {url}")

        item = NexoraPageItem()
        item["url"] = url
        item["html"] = response.text
        item["depth"] = depth
        item["spider_name"] = self.name
        item["crawled_at"] = datetime.now(timezone.utc).isoformat()
        item["playwright_used"] = response.meta.get("playwright_used", False)
        item["from_sitemap"] = response.meta.get("from_sitemap", False)
        item["sitemap_lastmod"] = response.meta.get("sitemap_lastmod", "")
        item["sitemap_priority"] = response.meta.get("sitemap_priority", "")

        yield item

        if not self._crawl_enabled:
            return

        base_domain = urlparse(url).netloc
        next_depth = depth + 1

        for href in response.css("a::attr(href)").getall():
            if not href or href.startswith(("#", "mailto:", "tel:", "javascript:")):
                continue

            abs_url = self._canonicalize(response.urljoin(href))

            if urlparse(abs_url).netloc != base_domain:
                continue

            if next_depth > self._depth:
                continue

            needs_js = self._needs_playwright(abs_url)
            yield response.follow(
                abs_url,
                callback=self.parse,
                errback=self.handle_error,
                meta={
                    "depth": next_depth,
                    "playwright": needs_js,
                    "playwright_used": needs_js,
                },
            )

    def handle_error(self, failure):
        log.error(f"Request failed [{failure.type.__name__}]: {failure.request.url}")

    def _discover_urls_from_sitemap(self, sitemap_url: str, limit: int = 50) -> list:
        import xml.etree.ElementTree as ET

        try:
            import requests
            r = requests.get(sitemap_url, timeout=15, headers={"User-Agent": "NexoraBot/1.0"})
            if r.status_code >= 400:
                log.warning(f"Sitemap fetch failed [{r.status_code}] {sitemap_url}")
                return []

            xml_text = r.text
            root = ET.fromstring(xml_text)

            ns = ""
            if root.tag.startswith("{"):
                ns = root.tag.split("}")[0] + "}"

            if root.find(f"{ns}sitemap") is not None:
                urls = []
                for sitemap in root.findall(f"{ns}sitemap"):
                    loc = sitemap.find(f"{ns}loc")
                    if loc is None or not (loc.text and loc.text.strip()):
                        continue
                    child = loc.text.strip()
                    urls.extend(self._discover_urls_from_sitemap(child, limit=limit - len(urls)))
                    if len(urls) >= limit:
                        break
                return urls[:limit]

            locs = root.findall(f".//{ns}loc")
            urls = []
            for loc in locs:
                if loc is None or not loc.text:
                    continue
                u = loc.text.strip()
                if u:
                    urls.append(u)
                    if len(urls) >= limit:
                        break
            return urls

        except Exception as e:
            log.warning(f"Sitemap parsing failed for {sitemap_url}: {e}")
            return []

    @staticmethod
    def _canonicalize(url: str) -> str:
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
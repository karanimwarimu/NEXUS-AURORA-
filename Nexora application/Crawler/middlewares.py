"""
nexora_crawler/middlewares.py
==============================
Downloader middlewares that sit between Scrapy's engine and the internet.

Phase 2: Only the NexoraUserAgentMiddleware is active — it rotates
         User-Agent strings to reduce blocking.

Phase 3 hook: The PlaywrightRoutingMiddleware stub is here and documented.
              When scrapy-playwright is installed, simply uncomment it in
              settings.py DOWNLOADER_MIDDLEWARES and it will intercept any
              Request that has meta['playwright'] = True.

Middleware execution order (lower number = runs first on request,
last on response):
    500  NexoraUserAgentMiddleware   ← always active
    600  PlaywrightRoutingMiddleware ← Phase 3, currently a no-op stub
"""

import logging
import random
from scrapy import signals

log = logging.getLogger("nexora.middleware")

# ── User-Agent pool ───────────────────────────────────────────────────────────
USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/123.0.0.0 Safari/537.36",
    "Mozilla/5.0 (X11; Linux x86_64; rv:125.0) Gecko/20100101 Firefox/125.0",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:124.0) Gecko/20100101 Firefox/124.0",
]


class NexoraUserAgentMiddleware:
    """
    Rotates User-Agent on every request.
    Helps avoid simple bot-detection filters that block repeated identical agents.
    """

    def process_request(self, request, spider):
        agent = random.choice(USER_AGENTS)
        request.headers["User-Agent"] = agent
        log.debug(f"User-Agent set → {agent[:50]}…")
        return None  # continue processing


# ── Phase 3 stub ──────────────────────────────────────────────────────────────
class PlaywrightRoutingMiddleware:
    """
    PHASE 3 HOOK — currently a no-op pass-through.

    In Phase 3:
      1. pip install scrapy-playwright && playwright install chromium
      2. Uncomment in settings.py DOWNLOADER_MIDDLEWARES
      3. This middleware intercepts requests with meta['playwright'] = True
         and hands them to a real Chromium browser via scrapy-playwright.

    The spider already sets meta['playwright'] = True for JS-heavy domains.
    The pipeline already handles both paths identically because it receives
    rendered HTML either way.  Nothing else needs to change.
    """

    def process_request(self, request, spider):
        if request.meta.get("playwright"):
            log.debug(
                f"[Phase 3 stub] Would launch Playwright for: {request.url}"
            )
            # Phase 3: return None here to let scrapy-playwright handle it.
            # For now we fall through to the normal Scrapy downloader.
        return None


class NexoraSpiderMiddleware:
    """
    Spider-level middleware stub.
    Currently passes everything through; add custom logic here in later phases
    (e.g. retry logic, response filtering, custom error pages).
    """

    @classmethod
    def from_crawler(cls, crawler):
        s = cls()
        crawler.signals.connect(s.spider_opened, signal=signals.spider_opened)
        return s

    def process_spider_output(self, response, result, spider):
        yield from result

    def process_spider_exception(self, response, exception, spider):
        pass

    def spider_opened(self, spider):
        log.info(f"Spider opened: {spider.name}")

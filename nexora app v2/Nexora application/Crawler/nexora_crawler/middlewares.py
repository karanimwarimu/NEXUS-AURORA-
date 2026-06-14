"""
nexora_crawler/middlewares.py
==============================
Downloader and spider middlewares.

Active in Phase 2:
    500  NexoraUserAgentMiddleware      — rotates User-Agent strings
    510  ContentTypeFilterMiddleware    — rejects non-HTML before pipeline (NEW)

Stubbed for Phase 3:
    600  PlaywrightRoutingMiddleware    — routes JS-heavy requests to browser
"""

import logging
import random
import re
from scrapy import signals
from scrapy.exceptions import IgnoreRequest

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

# ── URL patterns to always skip ───────────────────────────────────────────────
BLOCKED_PATH_PATTERNS = [
    r"/account/",
    r"/login",
    r"/logout",
    r"/signup",
    r"/register",
    r"/admin/",
    r"/search\?",
    r"/feedback",
    r"/cart",
    r"/checkout",
    r"\.pdf$",
    r"\.zip$",
    r"\.exe$",
    r"\.dmg$",
    r"\.(jpg|jpeg|png|gif|webp|svg|ico)$",
    r"\.(mp4|mp3|avi|mov|wmv)$",
    r"\.(css|js|woff|woff2|ttf)$",
]
_BLOCKED_RE = re.compile("|".join(BLOCKED_PATH_PATTERNS), re.IGNORECASE)


class NexoraUserAgentMiddleware:
    """Rotates User-Agent on every outgoing request."""

    # Scrapy 2.16+ may call these without passing `spider`.
    def process_request(self, request, spider=None):
        agent = random.choice(USER_AGENTS)
        request.headers["User-Agent"] = agent
        return None



class ContentTypeFilterMiddleware:
    """Rejects non-HTML responses before they reach the spider."""

    # Scrapy 2.16+ may call these without passing `spider`.
    def process_request(self, request, spider=None):

        from urllib.parse import urlparse
        path = urlparse(request.url).path

        if _BLOCKED_RE.search(path):
            log.debug(f"Blocked by URL pattern: {request.url}")
            raise IgnoreRequest(f"Blocked URL pattern: {request.url}")
        return None

    def process_response(self, request, response, spider=None):

        content_type = response.headers.get("Content-Type", b"").decode(
            "utf-8", "ignore"
        ).lower()

        if "text/html" in content_type or "xhtml" in content_type:
            return response
        if not content_type:
            return response

        log.warning(f"Skipping non-HTML [{content_type}]: {response.url}")
        raise IgnoreRequest(f"Non-HTML content-type: {content_type}")


class PlaywrightRoutingMiddleware:
    """
    PHASE 3 HOOK — currently a no-op pass-through.
    """

    def process_request(self, request, spider):
        if request.meta.get("playwright"):
            log.debug(f"[Phase 3 stub] Would launch browser for: {request.url}")
        return None


class NexoraSpiderMiddleware:

    """
    Spider-level middleware.

    CRITICAL FIX: process_spider_output must be SYNCHRONOUS (not async) in Scrapy 2.x.
    Using async here silently breaks start_requests() generator chain.
    """

    @classmethod
    def from_crawler(cls, crawler):
        s = cls()
        crawler.signals.connect(s.spider_opened, signal=signals.spider_opened)
        return s

    def process_spider_input(self, response, spider):
        return None

    async def process_spider_output_async(self, response, result, spider):
        for x in result:
            yield x


    def process_spider_exception(self, response, exception, spider):
        return None

    def spider_opened(self, spider):
        log.info(f"Spider opened: {spider.name}")
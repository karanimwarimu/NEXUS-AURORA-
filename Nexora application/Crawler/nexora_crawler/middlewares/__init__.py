"""
nexora_crawler/middlewares.py
==============================
Downloader and spider middlewares (Phase 3).

Active middlewares:
     50  NexoraUserAgentMiddleware       — rotates User-Agent strings
    510  ContentTypeFilterMiddleware     — rejects non-HTML before pipeline
    542  DynamicDetectionMiddleware      — decides HTTP vs Playwright routing
    550  PlaywrightCleanupMiddleware     — closes Playwright pages to prevent leaks

Spider middlewares:
    543  NexoraSpiderMiddleware          — spider lifecycle + output passthrough

Debug mode:
    Run with --loglevel=DEBUG to see every middleware decision with reason.
    e.g.  scrapy crawl nexora -a sitemap="..." --loglevel=DEBUG
"""


import logging
import random
import re
from urllib.parse import urlparse

from scrapy import signals
from scrapy.exceptions import IgnoreRequest


log = logging.getLogger("nexora.middleware")


USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/123.0.0.0 Safari/537.36",
    "Mozilla/5.0 (X11; Linux x86_64; rv:125.0) Gecko/20100101 Firefox/125.0",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:124.0) Gecko/20100101 Firefox/124.0",
]


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
_BLOCKED_RE = re.compile("|".join(BLOCKED_PATH_PATTERNS), re.IGNORECASE) # what regex does is : it compiles the regex patterns into a single regex object that can be used to match against URLs. The re.IGNORECASE flag makes the matching case-insensitive, so it will match patterns regardless of whether they are in uppercase or lowercase. This is useful for filtering out unwanted paths in web crawling, such as login pages, admin pages, and certain file types like images and videos.


class NexoraUserAgentMiddleware:
    """Rotates User-Agent strings on every request."""

    def __init__(self, crawler=None):
        self.crawler = crawler

    @classmethod
    def from_crawler(cls, crawler):
        return cls(crawler)

    async def process_request(self, request):
        """Scrapy 2.16+ async signature — no spider argument."""
        ua = random.choice(USER_AGENTS)
        request.headers["User-Agent"] = ua
        log.debug("[UA] %s -> %s", _short(request.url), ua[:40])
        return None


class ContentTypeFilterMiddleware:
    """Rejects non-HTML responses and blocked URL patterns.

    NOTE: Requests already marked for Playwright (playwright=True) are
    allowed through, since Playwright handles its own sub-resource loading.
    """

    def __init__(self, crawler=None):
        self.crawler = crawler

    @classmethod
    def from_crawler(cls, crawler):
        return cls(crawler)
    
    
    # the initiallizing of the middleware class, which takes an optional crawler argument and assigns it to the instance variable self.crawler. This allows the middleware to access the Scrapy crawler object if needed.
    # from crawler_class method is a factory method that creates an instance of the middleware class from the Scrapy crawler. It takes the crawler as an argument and returns an instance of the middleware class, allowing it to be integrated into the Scrapy framework.

    async def process_request(self, request):
        """Block requests to URLs matching blocked patterns.
        Allows Playwright-routed requests through regardless of path.
        """
        # Allow Playwright-routed requests through — the browser handles sub-resources
        if request.meta.get("playwright"):
            log.debug("[ALLOW-PW] %s", _short(request.url))
            return None

        path = urlparse(request.url).path # urlparse here is used to extract the path component of the URL from the request. The path is the part of the URL that comes after the domain name and before any query parameters or fragments. For example, in the URL "https://example.com/account/login?next=/dashboard", the path would be "/account/login". This path is then checked against a list of blocked patterns to determine if the request should be allowed or blocked.
        if _BLOCKED_RE.search(path):
            log.debug("[BLOCK-req] pattern match -> %s", request.url)
            raise IgnoreRequest(f"Blocked URL pattern: {request.url}")
        log.debug("[ALLOW-req] %s", _short(request.url))
        return None

    async def process_response(self, request, response):
        """Scrapy 2.16+ async signature — no spider argument."""
        url = request.url

        # sitemap XML must reach parse_sitemap_index (text/xml / application/xml)
        if request.meta.get("from_sitemap"):
            log.debug("[ALLOW-resp] sitemap pass-through -> %s", _short(url))
            return response

        ct = response.headers.get(b"Content-Type", b"").decode("utf-8", "ignore").lower()

        if not ct or "text/html" in ct or "xhtml" in ct:
            log.debug("[ALLOW-resp] HTML [%s] -> %s", ct or "no-ct", _short(url))
            return response

        log.warning("[BLOCK-resp] non-HTML [%s] -> %s", ct, url)
        raise IgnoreRequest(f"Non-HTML content-type: {ct}")


class NexoraSpiderMiddleware:
    """Spider middleware — handles spider output and exceptions."""

    @classmethod
    def from_crawler(cls, crawler):
        s = cls()
        crawler.signals.connect(s.spider_opened, signal=signals.spider_opened)
        return s

    def process_spider_input(self, response):
        """Scrapy 2.16+ — no spider argument."""
        return None

    async def process_spider_output(self, response, result):
        """Scrapy 2.16+ async output processing.

        Must be named process_spider_output (not process_spider_output_async).
        Scrapy detects the async def and calls it asynchronously.
        """
        async for x in result:
            yield x

    def process_spider_exception(self, response, exception):
        """Scrapy spider exception handler — Scrapy 2.16+ no spider argument."""
        log.error("[spider-exception] %s — %s", response.url, exception)
        return None

    def spider_opened(self, spider):
        log.info("Spider opened: %s", spider.name)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _short(url: str, n: int = 80) -> str:
    """Truncate a URL for readable log lines."""
    return url if len(url) <= n else url[:n] + "..."
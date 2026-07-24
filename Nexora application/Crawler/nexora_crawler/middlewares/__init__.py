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
    r"/vote",
    r"/hide",
    r"/submit",
    r"\.pdf$",
    r"\.zip$",
    r"\.exe$",
    r"\.dmg$",
    r"\.(jpg|jpeg|png|gif|webp|svg|ico)$",
    r"\.(mp4|mp3|avi|mov|wmv)$",
    r"\.(css|js|woff|woff2|ttf)$",
]
_BLOCKED_RE = re.compile("|".join(BLOCKED_PATH_PATTERNS), re.IGNORECASE)

# Query-string action parameters that produce non-content pages (history,
# edit, mobile variants, etc.). Checked alongside path patterns so action
# links like /vote?ID=... or ?action=history are blocked at request time.
_BLOCKED_QUERY_RE = re.compile(
    r"(?:^|&)(?:action|mobileaction)=(?:history|edit|raw|diff|undelete|protect|move|delete|purge|watch|unwatch|rollback|mark|semiprotect)(?:&|$)",
    re.IGNORECASE,
)

# State-changing path segments that should never be crawled, regardless of
# query string. HN-style sites put the action in the path (/vote?id=...)
# rather than the query, so a segment-level check catches what regex
# path-pattern misses.
BLOCKED_PATH_SEGMENTS = {
    "vote", "hide", "login", "logout", "submit", "flag",
    "favorite", "reply", "register", "signup", "account",
}

# Crawl-infrastructure files that are intentionally non-HTML: robots.txt
# (text/plain, consumed by RobotsTxtMiddleware) and sitemap XML variants
# (sitemap.xml / sitemap_index.xml / sitemap-1.xml[.gz], consumed by the
# sitemap detector/parser). These must bypass the content-type block or
# robots rules are silently never applied.
_INFRA_PATH_RE = re.compile(r"/(robots\.txt|sitemap[^/]*\.xml(\.gz)?)$", re.IGNORECASE)


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

        parsed = urlparse(request.url)
        path = parsed.path
        query = parsed.query

        if _BLOCKED_RE.search(path):
            log.debug("[BLOCK-req] path pattern match -> %s", _short(request.url))
            raise IgnoreRequest(f"Blocked URL pattern: {request.url}")

        # Path-segment check for state-changing actions (e.g. HN /vote?id=...)
        path_segments = [seg for seg in path.strip("/").split("/") if seg]
        if any(seg.lower() in BLOCKED_PATH_SEGMENTS for seg in path_segments):
            log.debug("[BLOCK-req] path segment match -> %s", _short(request.url))
            raise IgnoreRequest(f"Blocked state-changing path segment: {request.url}")

        if query and _BLOCKED_QUERY_RE.search(query):
            log.debug("[BLOCK-req] query pattern match -> %s", _short(request.url))
            raise IgnoreRequest(f"Blocked URL query: {request.url}")

        log.debug("[ALLOW-req] %s", _short(request.url))
        return None

    async def process_response(self, request, response):
        """Scrapy 2.16+ async signature — no spider argument."""
        url = request.url

        # sitemap XML must reach parse_sitemap_index (text/xml / application/xml)
        if request.meta.get("from_sitemap"):
            log.debug("[ALLOW-resp] sitemap pass-through -> %s", _short(url))
            return response

        # robots.txt / sitemap XML are crawl infrastructure — let them through
        # regardless of content-type (RobotsTxtMiddleware needs the body).
        if _INFRA_PATH_RE.search(urlparse(url).path):
            log.debug("[ALLOW-resp] infra file -> %s", _short(url))
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
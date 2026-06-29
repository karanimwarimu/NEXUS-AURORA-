"""
ExponentialBackoffMiddleware — Retries failed requests with exponential delay.

Scrapy's built-in retry uses a fixed delay between retries. This middleware
replaces that with exponential backoff: 1s → 2s → 4s → 8s for each retry.

Also handles 429 (Too Many Requests) by respecting Retry-After headers.

Registered at priority: 700 (runs after all other middlewares).
"""
import logging
import time
from urllib.parse import urlparse

from scrapy import signals
from scrapy.exceptions import IgnoreRequest

logger = logging.getLogger(__name__)

# Default retry delays in seconds (exponential backoff)
# 1st retry: 1s, 2nd: 2s, 3rd: 4s, 4th: 8s, 5th: 16s
RETRY_DELAYS = [1, 2, 4, 8, 16]

# HTTP codes that trigger retry with backoff
RETRYABLE_CODES = {429, 503, 502, 504, 408, 500}

# Maximum Retry-After header value to respect (seconds)
MAX_RETRY_AFTER = 120


class ExponentialBackoffMiddleware:
    """Retries failed requests with exponential backoff delay."""

    def __init__(self, crawler):
        self.crawler = crawler

    @classmethod
    def from_crawler(cls, crawler):
        mw = cls(crawler)
        crawler.signals.connect(mw.spider_opened, signal=signals.spider_opened)
        return mw

    def spider_opened(self, spider):
        logger.info("[ExponentialBackoff] Middleware initialized")

    async def process_response(self, request, response):
        """Check if response should be retried with backoff."""
        if response.status in RETRYABLE_CODES:
            retries = request.meta.get("retry_times", 0)
            max_retries = self.crawler.settings.getint("RETRY_TIMES", 3)

            if retries < max_retries:
                delay = self._get_delay(retries, response)
                request.meta["retry_times"] = retries + 1
                request.meta["_retry_delay"] = delay

                logger.info(
                    "[ExponentialBackoff] Retry %d/%d for %s (status=%d, delay=%ds)",
                    retries + 1, max_retries,
                    request.url, response.status, delay,
                )

                # Schedule the retry by returning a copy of the request
                return request.copy()

        return response

    async def process_exception(self, request, exception):
        """Handle connection errors with backoff."""
        retries = request.meta.get("retry_times", 0)
        max_retries = self.crawler.settings.getint("RETRY_TIMES", 3)

        if retries < max_retries:
            delay = RETRY_DELAYS[min(retries, len(RETRY_DELAYS) - 1)]
            request.meta["retry_times"] = retries + 1
            request.meta["_retry_delay"] = delay

            logger.info(
                "[ExponentialBackoff] Retry %d/%d for %s (error=%s, delay=%ds)",
                retries + 1, max_retries,
                request.url, type(exception).__name__, delay,
            )

            return request.copy()

        # Max retries exceeded — let Scrapy handle the failure
        return None

    def _get_delay(self, retry_count: int, response) -> float:
        """Calculate delay for this retry attempt.

        Uses Retry-After header if present and reasonable,
        otherwise uses exponential backoff.
        """
        # Check Retry-After header (common on 429 responses)
        retry_after = response.headers.get(b"Retry-After")
        if retry_after is not None:
            try:
                delay = float(retry_after.decode("utf-8", "ignore"))
                if 0 < delay <= MAX_RETRY_AFTER:
                    return delay
            except (ValueError, UnicodeDecodeError):
                pass

        # Default exponential backoff
        return RETRY_DELAYS[min(retry_count, len(RETRY_DELAYS) - 1)]
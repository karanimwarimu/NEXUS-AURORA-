"""PlaywrightCleanupMiddleware - Prevents memory leaks from dangling pages.

Handles cleanup in BOTH process_response (success) and process_exception (failure)
paths to ensure no Playwright page references leak on errors.
"""
import logging

logger = logging.getLogger(__name__)


class PlaywrightCleanupMiddleware:
    """Close Playwright pages after response processing or on exception.

    Registered at priority 550 (after ScrapyPlaywrightDownloadHandler at 543).
    """

    def __init__(self, crawler):
        self.crawler = crawler

    @classmethod
    def from_crawler(cls, crawler):
        return cls(crawler)

    async def _close_page(self, request):
        """Helper: close the Playwright page if present, with error handling."""
        page = request.meta.get("playwright_page")
        if page:
            try:
                await page.close()
                logger.debug("[PlaywrightCleanup] Closed page for %s", request.url)
            except Exception as exc:
                logger.warning("[PlaywrightCleanup] Page close failed for %s: %s",
                               request.url, exc)

    async def process_response(self, request, response):

        """Close Playwright page after successful response."""
        await self._close_page(request)
        return response

    async def process_exception(self, request, exception):

        """Close Playwright page when an exception occurs during download.

        Without this handler, pages leak on timeouts, connection errors,
        and redirect loops — causing unbounded memory growth.
        """
        await self._close_page(request)
        logger.warning("[PlaywrightCleanup] Cleaned up page after exception for %s: %s",
                       request.url, exception)
        # Return None to let Scrapy's default exception handling continue
        return None
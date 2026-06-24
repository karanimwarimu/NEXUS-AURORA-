"""PlaywrightCleanupMiddleware - Prevents memory leaks from dangling pages."""
import logging

logger = logging.getLogger(__name__)


class PlaywrightCleanupMiddleware:
    """Close Playwright pages after response processing."""
    
    def __init__(self, crawler):
        self.crawler = crawler
    
    @classmethod
    def from_crawler(cls, crawler):
        return cls(crawler)
    
    async def process_response(self, request, response, spider):
        page = request.meta.get("playwright_page")
        if page:
            try:
                await page.close()
                logger.debug("[PlaywrightCleanup] Closed page for %s", request.url)
            except Exception as exc:
                logger.warning("[PlaywrightCleanup] Failed: %s", exc)
        return response
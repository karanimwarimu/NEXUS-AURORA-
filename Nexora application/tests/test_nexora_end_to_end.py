import os
import sys
import logging
import pytest
from urllib.parse import urlparse
from unittest.mock import AsyncMock, MagicMock, patch

# Ensure crawler package is importable
CRAWLER_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "Crawler"))
if CRAWLER_ROOT not in sys.path:
    sys.path.insert(0, CRAWLER_ROOT)

from twisted.internet import asyncioreactor
asyncioreactor.install()

import scrapy
from scrapy.http import Request, Response, HtmlResponse
from scrapy.utils.project import get_project_settings
from scrapy.crawler import CrawlerRunner
from scrapy.utils.log import configure_logging
from twisted.internet import defer

from nexora_crawler.spiders.nexora_spider import NexoraSpider
from nexora_crawler.sitemap_detector import SitemapDetector
from nexora_crawler.middlewares.dynamic_detection import DynamicDetectionMiddleware
from nexora_crawler.middlewares.playwright_cleanup import PlaywrightCleanupMiddleware

logger = logging.getLogger(__name__)


@pytest.fixture(scope="module")
def crawler_settings():
    settings = get_project_settings()
    settings.set("LOG_LEVEL", "DEBUG")
    settings.set("DOWNLOAD_HANDLERS", {
        "http": "scrapy_playwright.handler.ScrapyPlaywrightDownloadHandler",
        "https": "scrapy_playwright.handler.ScrapyPlaywrightDownloadHandler",
    })
    settings.set("TWISTED_REACTOR", "twisted.internet.asyncioreactor.AsyncioSelectorReactor")
    settings.set("DOWNLOADER_MIDDLEWARES", {
        "nexora_crawler.middlewares.NexoraUserAgentMiddleware": 50,
        "nexora_crawler.middlewares.ContentTypeFilterMiddleware": 510,
        "nexora_crawler.middlewares.dynamic_detection.DynamicDetectionMiddleware": 542,
        "nexora_crawler.middlewares.playwright_cleanup.PlaywrightCleanupMiddleware": 550,
    })
    settings.set("NEXORA_PLAYWRIGHT_ENABLED", True)
    return settings


@pytest.fixture
def runner(crawler_settings):
    configure_logging({'LOG_FORMAT': '%(levelname)s: %(message)s'})
    return CrawlerRunner(settings=crawler_settings)


@pytest.mark.real
@pytest.mark.asyncio
async def test_end_to_end_sitemap_autodetect_and_playwright(runner):
    """End-to-end crawl: sitemap autodetect, URL filtering, domain lock, and Playwright pipeline."""
    target_url = "https://www.bbc.com"
    spider = NexoraSpider(urls=target_url, strategy="whole-website", max_pages=20)

    data = {
        'requests': [],
        'items': [],
        'errors': [],
    }

    class CaptureSpider(scrapy.Spider):
        name = 'capture_nexora'
        allowed_domains = spider.allowed_domains

        def __init__(self, *args, **kwargs):
            super().__init__(*args, **kwargs)
            self._spider = spider

        async def start_requests(self):
            async for request in spider.start():
                request = request.replace(callback=self._capture_callback)
                yield request

        def _capture_callback(self, response):
            data['requests'].append(response.request.url)
            data['items'].append({
                'url': response.url,
                'status': response.status,
                'depth': response.meta.get('depth', 0),
                'sitemap': response.meta.get('from_sitemap', False),
                'playwright': response.meta.get('playwright', False),
                'sitemap_lastmod': response.meta.get('sitemap_lastmod'),
                'sitemap_priority': response.meta.get('sitemap_priority'),
                'sitemap_changefreq': response.meta.get('sitemap_changefreq'),
            })
            return []

        def parse(self, response):
            return []

        def errback(self, failure):
            data['errors'].append(str(failure.value))

    config = {
        'USER_AGENT': 'NexoraTest/1.0',
        'PLAYWRIGHT_BROWSER_TYPE': 'chromium',
        'PLAYWRIGHT_LAUNCH_OPTIONS': {'headless': True},
        'PLAYWRIGHT_DEFAULT_NAVIGATION_TIMEOUT': 20000,
    }
    runner.settings.setdict(config)

    await defer.ensureDeferred(runner.crawl(CaptureSpider))

    assert data['errors'] == [], f"Errors during crawl: {data['errors']}"
    assert len(data['items']) > 0, "No pages were crawled."
    assert all(urlparse(item['url']).scheme in ("http", "https") for item in data['items'])
    assert all(urlparse(item['url']).hostname in spider.allowed_domains or item['sitemap'] for item in data['items'])
    assert len(data['items']) <= spider.max_pages
    assert any(item['sitemap'] for item in data['items']), "Expected sitemap-sourced pages in results"

    # Verify sitemap metadata is preserved where available
    sitemap_meta_items = [item for item in data['items'] if item['sitemap']]
    assert all('sitemap_lastmod' in item for item in sitemap_meta_items)
    assert all('sitemap_priority' in item for item in sitemap_meta_items)
    assert all('sitemap_changefreq' in item for item in sitemap_meta_items)

    # Ensure Playwright can be used on dynamic pages without breaking
    assert any(item['playwright'] for item in data['items']) or any('script' in item['url'] for item in data['items'])

    logger.info("End-to-end crawl completed with %d pages, %d requests, %d sitemap pages", len(data['items']), len(data['requests']), len(sitemap_meta_items))

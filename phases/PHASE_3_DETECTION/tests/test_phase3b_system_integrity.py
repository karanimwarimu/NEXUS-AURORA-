"""
Phase 3b v0.2 System Integrity Tests

These tests validate the Phase 3b backbone on real websites and verify
core sitemap + dynamic routing behavior for actual production-like pages.

Run live-network tests with:
    pytest tests/test_phase3b_system_integrity.py -m real -v

This file is intentionally focused on actual website validation,
complementing existing unit and benchmark suites.
"""

import os
import sys
from unittest.mock import MagicMock

import httpx
import pytest
from scrapy.http import Request

# Ensure Crawler/ is importable
CRAWLER_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "Crawler"))
if CRAWLER_ROOT not in sys.path:
    sys.path.insert(0, CRAWLER_ROOT)

from nexora_crawler.middlewares.dynamic_detection import DynamicDetectionMiddleware
from nexora_crawler.middlewares.playwright_resource_blocker import PlaywrightResourceBlocker
from nexora_crawler.sitemap_detector import SitemapDetector


def create_middleware(tmp_path):
    crawler = MagicMock()
    settings = MagicMock()
    settings.getbool.side_effect = lambda key, default=False: {
        "NEXORA_PLAYWRIGHT_ENABLED": True,
        "NEXORA_STEALTH_ENABLED": True,
    }.get(key, default)
    settings.get.side_effect = lambda key, default=None: str(tmp_path / "site_profiles.db") if key == "NEXORA_SITE_PROFILE_DB" else default
    crawler.settings = settings
    return DynamicDetectionMiddleware(crawler)


@pytest.mark.real
@pytest.mark.asyncio
async def test_real_bbc_sitemap_discovery_and_fetch():
    """Verify that the system discovers and parses a real sitemap from BBC."""
    async with SitemapDetector() as detector:
        sitemaps = await detector.discover("https://www.bbc.com")
        assert sitemaps, "BBC must expose at least one sitemap URL"

        leaf_urls = await detector.fetch_urls(sitemaps[0])
        assert leaf_urls, f"BBC sitemap must yield page URLs: {sitemaps[0]}"
        assert all(url.startswith("http") for url in leaf_urls[:5])


@pytest.mark.real
@pytest.mark.asyncio
async def test_real_static_site_remains_http(tmp_path):
    """Example.com and Books to Scrape should be classified as static HTTP pages."""
    mw = create_middleware(tmp_path)

    for url in ["https://example.com", "https://books.toscrape.com"]:
        request = Request(url)
        result = await mw.process_request(request, None)
        assert result is None, f"{url} should remain on HTTP and not require Playwright"


@pytest.mark.real
@pytest.mark.asyncio
async def test_real_bot_sannysoft_triggers_playwright(tmp_path):
    """A JS-heavy fingerprint page should route to Playwright."""
    mw = create_middleware(tmp_path)
    request = Request("https://bot.sannysoft.com")

    result = await mw.process_request(request, None)
    assert result is not None, "bot.sannysoft.com should trigger Playwright routing"
    assert result.meta.get("playwright") is True
    assert result.meta.get("playwright_include_page") is True
    assert isinstance(result.meta.get("playwright_page_methods"), list)


@pytest.mark.asyncio
async def test_playwright_resource_blocker_attaches_page_methods():
    """Verify the PlaywrightResourceBlocker injects a blocking init script."""
    crawler = MagicMock()
    settings = MagicMock()
    settings.getbool.return_value = True
    crawler.settings = settings

    middleware = PlaywrightResourceBlocker(crawler)
    request = Request("https://example.com")
    request.meta["playwright"] = True
    request.meta["playwright_page_methods"] = []

    await middleware.process_request(request, None)

    page_methods = request.meta.get("playwright_page_methods")
    assert isinstance(page_methods, list)
    assert page_methods, "PlaywrightResourceBlocker must add at least one PageMethod"
    assert getattr(page_methods[0], "method", None) == "add_init_script"


@pytest.mark.real
@pytest.mark.asyncio
async def test_real_http_probe_client_success(tmp_path):
    """Verify the real HTTP probe path works for an actual page."""
    mw = create_middleware(tmp_path)
    request = Request("https://httpbin.org/html")

    result = await mw.process_request(request, None)
    assert result is None, "httpbin.org/html should be classified as a static HTML page"


@pytest.mark.real
@pytest.mark.asyncio
async def test_real_dynamic_detection_handle_network_errors(tmp_path):
    """Ensure the real network path handles connection failures gracefully."""
    mw = create_middleware(tmp_path)
    mw._create_http_client = lambda: httpx.AsyncClient(timeout=httpx.Timeout(0.5, connect=0.25))

    request = Request("https://localhost/does-not-exist")
    result = await mw.process_request(request, None)
    assert result is not None, "Probe failures should fallback to Playwright rather than crash"
    assert result.meta.get("playwright") is True

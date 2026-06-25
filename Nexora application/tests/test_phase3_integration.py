"""
Phase 3.2 — Integration Tests (Tier 3)
============================================
Tests the full HTTP→Playwright pipeline using mocked responses.
Validates selective routing — the core value proposition.

Run: pytest tests/test_phase3_integration.py -v --tb=short
"""

import os
import sys
import tempfile

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "Crawler")))

import pytest
from scrapy.http import Request
from unittest.mock import AsyncMock, MagicMock, patch

from nexora_crawler.middlewares.dynamic_detection import DynamicDetectionMiddleware


# ============================================================================
# I1: Static page → HTTP handler (no browser launched)
# ============================================================================

class TestI1_StaticPageHttpOnly:

    @pytest.fixture
    def mw(self):
        """Create middleware with temp DB, mocked HTTP client, empty cache."""
        crawler = MagicMock()
        crawler.settings = MagicMock()
        crawler.settings.getbool.side_effect = lambda k, d=False: {
            "NEXORA_PLAYWRIGHT_ENABLED": True,
            "NEXORA_STEALTH_ENABLED": True,
        }.get(k, d)
        with tempfile.TemporaryDirectory() as tmpdir:
            crawler.settings.get.return_value = os.path.join(tmpdir, "p.db")
            m = DynamicDetectionMiddleware(crawler)
            m._client = AsyncMock()
            m._profile_cache = {}
            m._profile_cache_timestamps = {}
            yield m

    @pytest.mark.asyncio
    async def test_i1_static_article_returns_none(self, mw):
        """Static article with substantial text → HTTP (result is None)."""
        html = (
            "<html><body>"
            "<h1>Article Title</h1>"
            "<p>" + "This is a paragraph with lots of meaningful content. " * 20 + "</p>"
            "<p>" + "Another paragraph with even more content for testing purposes. " * 20 + "</p>"
            "<p>" + "And yet another paragraph to ensure the page is recognized as static. " * 20 + "</p>"
            "</body></html>"
        )
        mw._client.get.return_value = MagicMock(
            status_code=200,
            text=html,
            url="https://example.com/article"
        )

        request = Request("https://example.com/article")
        result = await mw.process_request(request, None)

        # Static pages should return None (no Playwright routing)
        assert result is None, (
            "Static article with substantial text must NOT route to Playwright. "
            "This is the core value proposition of selective rendering."
        )

    @pytest.mark.asyncio
    async def test_i1_static_contact_page_returns_none(self, mw):
        """Small legitimate static contact page → HTTP (result is None)."""
        html = (
            "<html><body>"
            "<h1>Contact Us</h1>"
            "<p>Email: info@example.com<br>Phone: +1-555-0123</p>"
            "<p>Address: 123 Main Street, City, Country</p>"
            "</body></html>"
        )
        mw._client.get.return_value = MagicMock(
            status_code=200,
            text=html,
            url="https://example.com/contact"
        )

        request = Request("https://example.com/contact")
        result = await mw.process_request(request, None)

        # Small static pages WITHOUT scripts should stay on HTTP
        assert result is None, (
            "Small static page with no scripts must NOT route to Playwright. "
            "This was a known false positive before the fix."
        )

    @pytest.mark.asyncio
    async def test_i1_error_page_returns_none(self, mw):
        """Error page (404, 500) with static content → HTTP."""
        html = (
            "<html><body>"
            "<h1>404 Not Found</h1>"
            "<p>The requested page could not be found.</p>"
            "</body></html>"
        )
        mw._client.get.return_value = MagicMock(
            status_code=404,
            text=html,
            url="https://example.com/missing"
        )

        request = Request("https://example.com/missing")
        result = await mw.process_request(request, None)

        assert result is None, "404 error page should not trigger Playwright"

    @pytest.mark.asyncio
    async def test_i1_no_empty_body_no_framework(self, mw):
        """Empty body with no framework markers and low script ratio → HTTP."""
        # A truly empty minimal page — no scripts, no framework, no body text
        html = "<html><head><title>Minimal</title></head><body></body></html>"
        mw._client.get.return_value = MagicMock(
            status_code=200,
            text=html,
            url="https://example.com/minimal"
        )

        request = Request("https://example.com/minimal")
        result = await mw.process_request(request, None)

        # Body is empty, but no scripts and no framework → should be static
        assert result is None, (
            "Minimal page with empty body but no scripts/frameworks "
            "should NOT route to Playwright"
        )


# ============================================================================
# I2: JS-heavy page → Playwright renders content
# ============================================================================

class TestI2_JsHeavyPagesTriggerPlaywright:

    @pytest.fixture
    def mw(self):
        """Create middleware with temp DB, mocked HTTP client, empty cache."""
        crawler = MagicMock()
        crawler.settings = MagicMock()
        crawler.settings.getbool.side_effect = lambda k, d=False: {
            "NEXORA_PLAYWRIGHT_ENABLED": True,
            "NEXORA_STEALTH_ENABLED": True,
        }.get(k, d)
        with tempfile.TemporaryDirectory() as tmpdir:
            crawler.settings.get.return_value = os.path.join(tmpdir, "p.db")
            m = DynamicDetectionMiddleware(crawler)
            m._client = AsyncMock()
            m._profile_cache = {}
            m._profile_cache_timestamps = {}
            yield m

    @pytest.mark.asyncio
    async def test_i2_nextjs_triggers_playwright(self, mw):
        """Next.js page → Playwright with correct meta."""
        html = (
            '<html><head>'
            '<meta name="generator" content="Next.js 14.2.0"/>'
            '</head><body><div id="__next"></div>'
            '<script src="/_next/static/chunks/main.js"></script>'
            '</body></html>'
        )
        mw._client.get.return_value = MagicMock(
            status_code=200,
            text=html,
            url="https://nextjs-site.com"
        )

        request = Request("https://nextjs-site.com")
        result = await mw.process_request(request, None)

        assert result is not None, "Next.js page must route to Playwright"
        assert result.meta.get("playwright") is True
        assert result.meta.get("playwright_include_page") is True
        assert result.meta.get("playwright_context") == "default"
        assert len(result.meta.get("playwright_page_methods", [])) > 0

    @pytest.mark.asyncio
    async def test_i2_spa_shell_triggers_playwright(self, mw):
        """SPA shell (empty root div, no content) → Playwright."""
        html = '<html><body><div id="root"></div></body></html>'
        mw._client.get.return_value = MagicMock(
            status_code=200,
            text=html,
            url="https://spa-site.com"
        )

        request = Request("https://spa-site.com")
        result = await mw.process_request(request, None)

        assert result is not None, "SPA shell must route to Playwright"
        assert result.meta.get("playwright") is True

    @pytest.mark.asyncio
    async def test_i2_cloudflare_challenge_triggers_playwright(self, mw):
        """Cloudflare challenge (403 + cf pattern) → Playwright."""
        html = (
            "<html><div class='cf-browser-verification'>"
            "<h1>Checking your browser</h1>"
            "<noscript>Please enable JavaScript</noscript>"
            "</div></html>"
        )
        mw._client.get.return_value = MagicMock(
            status_code=403,
            text=html,
            url="https://protected-site.com"
        )

        request = Request("https://protected-site.com")
        result = await mw.process_request(request, None)

        assert result is not None, "Cloudflare challenge must route to Playwright"
        assert result.meta.get("playwright") is True

    @pytest.mark.asyncio
    async def test_i2_rate_limit_with_captcha_triggers_playwright(self, mw):
        """429 rate limit with captcha → Playwright."""
        html = "<html><div class='px-captcha'>Verify you are human</div></html>"
        mw._client.get.return_value = MagicMock(
            status_code=429,
            text=html,
            url="https://rate-limited-site.com"
        )

        request = Request("https://rate-limited-site.com")
        result = await mw.process_request(request, None)

        assert result is not None, "Rate limit with captcha must route to Playwright"

    @pytest.mark.asyncio
    async def test_i2_probe_failure_fallback(self, mw):
        """HTTP probe failure → Playwright fallback (safe default)."""
        mw._client.get.side_effect = ConnectionError("DNS resolution failed")

        request = Request("https://unreachable-site.com")
        result = await mw.process_request(request, None)

        assert result is not None, "Probe failure should fall back to Playwright"
        assert result.meta.get("playwright") is True

    @pytest.mark.asyncio
    async def test_i2_profile_cache_second_request(self, mw):
        """After first probe, second request uses cache (no HTTP call)."""
        html = (
            '<html><head><meta name="generator" content="Next.js"/></head>'
            '<body><div id="__next"></div></body></html>'
        )
        mw._client.get.return_value = MagicMock(
            status_code=200,
            text=html,
        )

        # First request — probes and caches
        r1 = Request("https://cached-site.com/page1")
        result1 = await mw.process_request(r1, None)
        assert result1 is not None
        assert mw._client.get.called, "First request should probe"

        mw._client.get.reset_mock()

        # Second request — uses cache, no HTTP call
        r2 = Request("https://cached-site.com/page2")
        result2 = await mw.process_request(r2, None)
        assert result2 is not None

        # This is critical: the second request must NOT call _client.get
        assert not mw._client.get.called, (
            "Second request to same domain must use cached profile, "
            "not make another HTTP probe"
        )

    @pytest.mark.asyncio
    async def test_i2_high_script_ratio_triggers_playwright(self, mw):
        """High script-to-tag ratio → Playwright."""
        html = (
            "<html><head>"
            + "".join(['<script src="chunk{}.js"></script>'.format(i) for i in range(15)])
            + "</head><body><div id='app'>Loading...</div></body></html>"
        )
        mw._client.get.return_value = MagicMock(
            status_code=200,
            text=html,
        )

        request = Request("https://heavy-scripts.com")
        result = await mw.process_request(request, None)

        assert result is not None, "High script ratio page must route to Playwright"
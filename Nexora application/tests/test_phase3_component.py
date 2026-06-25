"""
Phase 3.2 — Component Tests (Tier 2)
========================================
Tests middleware behavior inside a real Scrapy engine without live network.
Verifies settings registration, meta injection, and Phase 2.6 regression.

Run: pytest tests/test_phase3_component.py -v --tb=short
"""

import os
import sys
import tempfile

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "Crawler")))

import pytest
from scrapy.http import Request, Response
from unittest.mock import AsyncMock, MagicMock, patch

from nexora_crawler.middlewares.dynamic_detection import DynamicDetectionMiddleware
from nexora_crawler.middlewares.playwright_cleanup import PlaywrightCleanupMiddleware
from nexora_crawler.settings import DOWNLOADER_MIDDLEWARES


# ============================================================================
# C1: Middleware loads in Scrapy engine (registration verification)
# ============================================================================

class TestC1_MiddlewareRegistration:

    def test_c1_middleware_registered(self):
        """Verify ALL Phase 3 middlewares are registered in settings.py."""
        registered = list(DOWNLOADER_MIDDLEWARES.keys())
        dd_registered = any("DynamicDetection" in k for k in registered)
        pw_registered = any("ScrapyPlaywrightDownloadHandler" in k for k in registered)
        cl_registered = any("PlaywrightCleanup" in k for k in registered)

        assert dd_registered, "DynamicDetectionMiddleware NOT registered in DOWNLOADER_MIDDLEWARES"
        assert pw_registered, "ScrapyPlaywrightDownloadHandler NOT registered in DOWNLOADER_MIDDLEWARES"
        assert cl_registered, "PlaywrightCleanupMiddleware NOT registered in DOWNLOADER_MIDDLEWARES"

    def test_c1_priority_order(self):
        """Verify priority order: DD < 543 <= PW < CL."""
        priorities = {}
        for k, v in DOWNLOADER_MIDDLEWARES.items():
            if "DynamicDetection" in k:
                priorities["dd"] = v
            if "ScrapyPlaywrightDownloadHandler" in k:
                priorities["pw"] = v
            if "PlaywrightCleanup" in k:
                priorities["cl"] = v

        assert priorities.get("dd", 999) < 543, (
            f"DynamicDetection priority {priorities.get('dd')} must be < 543"
        )
        assert priorities.get("pw", 0) >= 543, (
            f"Playwright handler priority {priorities.get('pw')} must be >= 543"
        )
        assert priorities.get("cl", 0) > 543, (
            f"Cleanup priority {priorities.get('cl')} must be > 543"
        )

    def test_c1_dynamic_detection_init(self):
        """Verify DynamicDetectionMiddleware initializes without errors."""
        crawler = MagicMock()
        crawler.settings = MagicMock()
        crawler.settings.getbool.side_effect = lambda k, d=False: True
        with tempfile.TemporaryDirectory() as tmpdir:
            crawler.settings.get.return_value = os.path.join(tmpdir, "profiles.db")
            mw = DynamicDetectionMiddleware(crawler)
            assert mw.playwright_enabled is True
            assert mw.stealth_enabled is True
            assert mw._profile_cache == {}
            assert mw._profile_cache_timestamps == {}

    def test_c1_cleanup_init(self):
        """Verify PlaywrightCleanupMiddleware initializes without errors."""
        crawler = MagicMock()
        mw = PlaywrightCleanupMiddleware(crawler)
        assert mw.crawler is crawler


# ============================================================================
# C2: Meta injection format verification
# ============================================================================

class TestC2_MetaInjection:

    @pytest.mark.asyncio
    async def test_c2_playwright_meta_structure(self):
        """Verify process_request injects ALL required Playwright meta fields."""
        crawler = MagicMock()
        crawler.settings = MagicMock()
        crawler.settings.getbool.side_effect = lambda k, d=False: {
            "NEXORA_PLAYWRIGHT_ENABLED": True,
            "NEXORA_STEALTH_ENABLED": True,
        }.get(k, d)
        with tempfile.TemporaryDirectory() as tmpdir:
            crawler.settings.get.return_value = os.path.join(tmpdir, "p.db")
            mw = DynamicDetectionMiddleware(crawler)
            mw._client = AsyncMock()
            mw._client.get.return_value = MagicMock(
                status_code=200,
                text='<html><head><meta name="generator" content="Next.js"/></head><body><div id="__next"></div></body></html>'
            )

            request = Request("https://example.com")
            result = await mw.process_request(request, None)

            assert result is not None, "JS page should route to Playwright"
            meta = result.meta

            # Required fields per Scrapy-Playwright spec
            assert meta.get("playwright") is True, "playwright=True required"
            assert meta.get("playwright_include_page") is True, "playwright_include_page=True required"
            assert meta.get("playwright_context") == "default", "playwright_context='default' required"
            assert "playwright_page_methods" in meta, "playwright_page_methods required"
            assert len(meta["playwright_page_methods"]) > 0, "At least one PageMethod required"

            # Verify first PageMethod is stealth init script (when enabled)
            first_method = meta["playwright_page_methods"][0]
            assert first_method.method == "add_init_script", (
                "First PageMethod should be add_init_script for stealth"
            )

    @pytest.mark.asyncio
    async def test_c2_stealth_disabled(self):
        """Verify when stealth is off, no init_script is added."""
        crawler = MagicMock()
        crawler.settings = MagicMock()
        crawler.settings.getbool.side_effect = lambda k, d=False: {
            "NEXORA_PLAYWRIGHT_ENABLED": True,
            "NEXORA_STEALTH_ENABLED": False,  # Stealth OFF
        }.get(k, d)
        with tempfile.TemporaryDirectory() as tmpdir:
            crawler.settings.get.return_value = os.path.join(tmpdir, "p.db")
            mw = DynamicDetectionMiddleware(crawler)
            mw._client = AsyncMock()
            mw._client.get.return_value = MagicMock(
                status_code=200,
                text='<html><head><meta name="generator" content="Next.js"/></head><body></body></html>'
            )

            request = Request("https://example.com")
            result = await mw.process_request(request, None)

            assert result is not None
            methods = result.meta.get("playwright_page_methods", [])
            stealth_methods = [m for m in methods if m.method == "add_init_script"]
            assert len(stealth_methods) == 0, "No stealth script when disabled"

    @pytest.mark.asyncio
    async def test_c2_cleanup_on_success(self):
        """Verify PlaywrightCleanupMiddleware closes page after response."""
        cl = PlaywrightCleanupMiddleware(MagicMock())
        page = AsyncMock()
        page.close = AsyncMock()

        request = Request("https://example.com")
        request.meta["playwright_page"] = page
        response = Response("https://example.com", status=200)

        result = await cl.process_response(request, response, None)

        assert page.close.called, "page.close() should be called after successful response"
        assert result is response, "process_response should return the response unchanged"

    @pytest.mark.asyncio
    async def test_c2_cleanup_on_exception(self):
        """Verify PlaywrightCleanupMiddleware closes page on exception."""
        cl = PlaywrightCleanupMiddleware(MagicMock())
        page = AsyncMock()
        page.close = AsyncMock()

        request = Request("https://example.com")
        request.meta["playwright_page"] = page

        result = await cl.process_exception(request, TimeoutError(), None)

        assert page.close.called, "page.close() should be called on exception"
        assert result is None, "process_exception should return None to continue Scrapy error handling"


# ============================================================================
# C5: Phase 2.6 Regression — core decision logic unchanged by Phase 3
# ============================================================================

class TestC5_Phase26Regression:

    def test_c5_html_request_detection(self):
        """Phase 2.6: _is_html_request must reject non-HTML extensions."""
        crawler = MagicMock()
        crawler.settings = MagicMock()
        crawler.settings.getbool.return_value = True
        with tempfile.TemporaryDirectory() as tmpdir:
            crawler.settings.get.return_value = os.path.join(tmpdir, "p.db")
            mw = DynamicDetectionMiddleware(crawler)

            assert mw._is_html_request(Request("https://ex.com/page.html")) is True
            assert mw._is_html_request(Request("https://ex.com/")) is True
            assert mw._is_html_request(Request("https://ex.com/page")) is True
            assert mw._is_html_request(Request("https://ex.com/image.jpg")) is False
            assert mw._is_html_request(Request("https://ex.com/style.css")) is False
            assert mw._is_html_request(Request("https://ex.com/script.js")) is False
            assert mw._is_html_request(Request("https://ex.com/doc.pdf")) is False

    def test_c5_text_density(self):
        """Phase 2.6: Text density calculation must be correct."""
        crawler = MagicMock()
        crawler.settings = MagicMock()
        crawler.settings.getbool.return_value = True
        with tempfile.TemporaryDirectory() as tmpdir:
            crawler.settings.get.return_value = os.path.join(tmpdir, "p.db")
            mw = DynamicDetectionMiddleware(crawler)

            # High density page (article-like)
            html_high = "<html><body>" + "<p>" + "Hello World " * 100 + "</p>" + "</body></html>"
            assert mw._calculate_text_density(html_high) > 0.5

            # Low density page (SPA shell)
            html_low = "<html><body><div id='root'><div class='container'><nav></nav></div></div></body></html>"
            assert mw._calculate_text_density(html_low) < 0.1

            # Empty
            assert mw._calculate_text_density("") == 0.0

    def test_c5_framework_detection(self):
        """Phase 2.6: Framework detection must identify known frameworks."""
        crawler = MagicMock()
        crawler.settings = MagicMock()
        crawler.settings.getbool.return_value = True
        with tempfile.TemporaryDirectory() as tmpdir:
            crawler.settings.get.return_value = os.path.join(tmpdir, "p.db")
            mw = DynamicDetectionMiddleware(crawler)

            cases = [
                ('<meta name="generator" content="Next.js 14"/>', "next.js"),
                ('<div data-reactroot="">', "react"),
                ('<div data-v-1234abcd>', "vue"),
                ('<html ng-app="myApp">', "angular"),
                ('<div class="svelte-1a2b3c4">', "svelte"),
                ('<meta name="generator" content="Gatsby 5"/>', "gatsby"),
                ('<meta name="generator" content="Nuxt 3"/>', "nuxt"),
                ('<html><body><h1>Plain</h1></body></html>', None),
            ]
            for html, expected in cases:
                result = mw._detect_framework(html)
                assert result == expected, f"Expected {expected}, got {result}"

    def test_c5_anti_bot_detection(self):
        """Phase 2.6: Anti-bot detection must match specific patterns only."""
        crawler = MagicMock()
        crawler.settings = MagicMock()
        crawler.settings.getbool.return_value = True
        with tempfile.TemporaryDirectory() as tmpdir:
            crawler.settings.get.return_value = os.path.join(tmpdir, "p.db")
            mw = DynamicDetectionMiddleware(crawler)

            # True positives (correct status + pattern)
            assert mw._detects_anti_bot("<html>cf-browser-verification</html>", 403) is True
            assert mw._detects_anti_bot("<html>turnstile</html>", 403) is True
            assert mw._detects_anti_bot("<html>px-captcha</html>", 429) is True
            assert mw._detects_anti_bot("<html>recaptcha</html>", 403) is True
            assert mw._detects_anti_bot("<html>hcaptcha</html>", 503) is True

            # False positives (correct status but wrong pattern)
            assert mw._detects_anti_bot("<html>Cloudflare CDN</html>", 403) is False
            assert mw._detects_anti_bot("<html>Cloudflare hosted</html>", 403) is False

            # False negatives (pattern present but wrong status)
            assert mw._detects_anti_bot("<html>cf-browser-verification</html>", 200) is False

    def test_c5_script_tag_ratio(self):
        """Phase 2.6: Script tag ratio calculation."""
        crawler = MagicMock()
        crawler.settings = MagicMock()
        crawler.settings.getbool.return_value = True
        with tempfile.TemporaryDirectory() as tmpdir:
            crawler.settings.get.return_value = os.path.join(tmpdir, "p.db")
            mw = DynamicDetectionMiddleware(crawler)

            # No scripts
            assert mw._script_tag_ratio("<html><body><h1>Hi</h1></body></html>") == 0.0

            # Heavy scripts
            heavy = "<html>" + "<script></script>" * 10 + "<body></body></html>"
            assert mw._script_tag_ratio(heavy) > 0.3

            # Empty
            assert mw._script_tag_ratio("") == 0.0
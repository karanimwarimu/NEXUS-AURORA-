"""test_phase3_playwright.py - Comprehensive Phase 3 Test Suite"""

import os
import sys
import tempfile

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from scrapy.http import Request
from nexora_crawler.middlewares.dynamic_detection import DynamicDetectionMiddleware


# ============================================================================
# FIXTURES
# ============================================================================

@pytest.fixture
def middleware():
    """Create isolated middleware with temp DB and mocked HTTP client."""
    crawler = MagicMock()
    crawler.settings = MagicMock()
    crawler.settings.getbool.side_effect = lambda k, default=False: {
        "NEXORA_PLAYWRIGHT_ENABLED": True,
        "NEXORA_STEALTH_ENABLED": True,
    }.get(k, default)
    
    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = os.path.join(tmpdir, "test_profiles.db")
        crawler.settings.get.return_value = db_path
        mw = DynamicDetectionMiddleware(crawler)
        mw._client = AsyncMock()
        mw._profile_cache = {}  # Ensure no stale cache
        yield mw


# ============================================================================
# TESTS FROM SPEC (Section 4.2)
# ============================================================================

class TestDynamicDetection:
    
    @pytest.mark.asyncio
    async def test_static_page_no_js(self, middleware):
        """P3-T01: Static site with substantial content → HTTP handler."""
        html = (
            "<html><body>"
            "<h1>Welcome to Example Corp</h1>"
            "<p>We provide enterprise software solutions for businesses of all sizes. "
            "Our platform handles millions of requests daily with 99.9% uptime. "
            "Contact us today for a free consultation and demo of our flagship product.</p>"
            "</body></html>"
        )
        with patch.object(middleware._client, 'get', new_callable=AsyncMock) as mock_get:
            mock_get.return_value.status_code = 200
            mock_get.return_value.text = html
            request = Request("https://example.com/about")
            result = await middleware.process_request(request, None)
            assert result is None, "Static page should NOT route to Playwright"
    
    @pytest.mark.asyncio
    async def test_react_app_needs_playwright(self, middleware):
        """P3-T02: Next.js app → Playwright renders DOM."""
        html = (
            '<html><head><meta name="generator" content="Next.js 14.2.0"/></head>'
            '<body><div id="__next"></div><script src="/_next/static/chunks/main.js"></script></body>'
            '</html>'
        )
        with patch.object(middleware._client, 'get', new_callable=AsyncMock) as mock_get:
            mock_get.return_value.status_code = 200
            mock_get.return_value.text = html
            request = Request("https://react-app.com")
            result = await middleware.process_request(request, None)
            assert result is not None, "React app SHOULD route to Playwright"
            assert result.meta.get("playwright") is True
    
    @pytest.mark.asyncio
    async def test_cloudflare_block(self, middleware):
        """P3-T03: Cloudflare challenge → Playwright + stealth bypass."""
        html = (
            "<html><div class='cf-browser-verification cf-im-under-attack'>"
            "<noscript>Please enable JavaScript</noscript>"
            "<h1>Checking your browser before accessing example.com</h1>"
            "</div></html>"
        )
        with patch.object(middleware._client, 'get', new_callable=AsyncMock) as mock_get:
            mock_get.return_value.status_code = 403
            mock_get.return_value.text = html
            request = Request("https://protected-site.com")
            result = await middleware.process_request(request, None)
            assert result is not None, "Cloudflare block SHOULD route to Playwright"
            assert result.meta.get("playwright") is True
    
    def test_framework_detection(self, middleware):
        """Framework regex detection accuracy."""
        test_cases = [
            ('<meta name="generator" content="Next.js 14"/>', "next.js"),
            ('<meta name="generator" content="Next.js 15.0.3"/>', "next.js"),
            ('<div data-reactroot="">', "react"),
            ('<div data-reactid="1">', "react"),
            ('<div data-v-1234abcd>', "vue"),
            ('<div data-v-abcdef12 class="app">', "vue"),
            ('<html ng-app="myApp">', "angular"),
            ('<div _nghost-c0>Content</div>', "angular"),
            ('<div class="svelte-1a2b3c4">Hello</div>', "svelte"),
            ('<div __svelte="123">', "svelte"),
            ('<script>window.__VUE__=true</script>', "vue"),
        ]
        for html, expected in test_cases:
            detected = middleware._detect_framework(html)
            assert detected == expected, f"Expected {expected}, got {detected} for: {html[:50]}..."
        
        # Negative cases
        negative_cases = [
            '<html><body><h1>Plain HTML</h1></body></html>',
            '<div class="bootstrap-container">',
            '<script src="jquery.min.js"></script>',
        ]
        for html in negative_cases:
            detected = middleware._detect_framework(html)
            assert detected is None, f"Should not detect framework in: {html[:50]}..."


# ============================================================================
# ADDITIONAL EDGE CASE TESTS
# ============================================================================

class TestProbeEdgeCases:
    
    @pytest.mark.asyncio
    async def test_empty_spa_shell(self, middleware):
        """Empty body with just root div → Playwright."""
        html = '<html><body><div id="root"></div></body></html>'
        with patch.object(middleware._client, 'get', new_callable=AsyncMock) as mock_get:
            mock_get.return_value.status_code = 200
            mock_get.return_value.text = html
            request = Request("https://spa-app.com")
            result = await middleware.process_request(request, None)
            assert result is not None
            assert result.meta.get("playwright") is True
    
    @pytest.mark.asyncio
    async def test_small_but_legitimate_static_page(self, middleware):
        """Small static page (< 200 chars) without JS frameworks → Static."""
        html = (
            "<html><body>"
            "<h1>Contact</h1><p>Email: info@example.com<br>Phone: 555-0123</p>"
            "</body></html>"
        )  # ~95 chars body content, no scripts, no framework
        with patch.object(middleware._client, 'get', new_callable=AsyncMock) as mock_get:
            mock_get.return_value.status_code = 200
            mock_get.return_value.text = html
            request = Request("https://example.com/contact")
            result = await middleware.process_request(request, None)
            # This WILL fail with current 200-char threshold — documenting the behavior
            assert result is None, "Small static page should stay on HTTP (may need threshold tuning)"
    
    @pytest.mark.asyncio
    async def test_high_script_ratio(self, middleware):
        """Heavy script tags → Playwright."""
        html = (
            "<html><head>"
            + "".join([f'<script src="chunk{i}.js"></script>' for i in range(15)])
            + "</head><body><div id='app'></div></body></html>"
        )  # 15 script tags out of ~17 total = 0.88 ratio
        with patch.object(middleware._client, 'get', new_callable=AsyncMock) as mock_get:
            mock_get.return_value.status_code = 200
            mock_get.return_value.text = html
            request = Request("https://heavy-js.com")
            result = await middleware.process_request(request, None)
            assert result is not None
            assert result.meta.get("playwright") is True
    
    @pytest.mark.asyncio
    async def test_anti_bot_429(self, middleware):
        """Rate limit with bot indicators → Playwright."""
        html = "<html><div class='px-captcha'>Verify you are human</div></html>"
        with patch.object(middleware._client, 'get', new_callable=AsyncMock) as mock_get:
            mock_get.return_value.status_code = 429
            mock_get.return_value.text = html
            request = Request("https://perimeterx-protected.com")
            result = await middleware.process_request(request, None)
            assert result is not None
            assert result.meta.get("playwright") is True
    
    @pytest.mark.asyncio
    async def test_user_override_playwright_true(self, middleware):
        """P3-T05: Explicit meta override → always Playwright."""
        request = Request("https://example.com")
        request.meta["playwright"] = True
        result = await middleware.process_request(request, None)
        assert result is not None
        assert result.meta.get("playwright") is True
    
    @pytest.mark.asyncio
    async def test_user_override_playwright_false(self, middleware):
        """P3-T06: Explicit meta override → always HTTP."""
        html = '<html><head><meta name="generator" content="Next.js"/></head></html>'
        with patch.object(middleware._client, 'get', new_callable=AsyncMock) as mock_get:
            mock_get.return_value.status_code = 200
            mock_get.return_value.text = html
            request = Request("https://example.com")
            request.meta["playwright"] = False
            result = await middleware.process_request(request, None)
            assert result is None, "Override=False should skip Playwright even for JS frameworks"
    
    @pytest.mark.asyncio
    async def test_non_html_request_skipped(self, middleware):
        """Images, CSS, etc. should never trigger Playwright."""
        for ext in ['.jpg', '.png', '.css', '.js', '.pdf']:
            request = Request(f"https://example.com/asset{ext}")
            result = await middleware.process_request(request, None)
            assert result is None, f"{ext} should not trigger Playwright"
    
    @pytest.mark.asyncio
    async def test_profile_caching(self, middleware):
        """P3-T04: Second request uses cached profile, skips probe."""
        html = '<html><head><meta name="generator" content="Next.js"/></head></html>'
        
        with patch.object(middleware._client, 'get', new_callable=AsyncMock) as mock_get:
            mock_get.return_value.status_code = 200
            mock_get.return_value.text = html
            
            # First request — should probe
            request1 = Request("https://cached-site.com/page1")
            result1 = await middleware.process_request(request1, None)
            assert result1 is not None
            assert mock_get.called, "First request should trigger probe"
            
            # Reset mock to track second call
            mock_get.reset_mock()
            
            # Second request — should use cache
            request2 = Request("https://cached-site.com/page2")
            result2 = await middleware.process_request(request2, None)
            assert result2 is not None
            assert not mock_get.called, "Second request should use cached profile, not probe"


# ============================================================================
# STEALTH & PLAYWRIGHT META TESTS
# ============================================================================

class TestStealthAndMeta:
    
    def test_stealth_script_content(self, middleware):
        """Verify stealth script patches navigator.webdriver."""
        script = middleware._build_stealth_script()
        assert "webdriver" in script
        assert "navigator" in script
        assert "chrome" in script
        assert "plugins" in script
    
    @pytest.mark.asyncio
    async def test_playwright_meta_structure(self, middleware):
        """Verify Playwright meta has required fields."""
        html = '<html><head><meta name="generator" content="Next.js"/></head></html>'
        with patch.object(middleware._client, 'get', new_callable=AsyncMock) as mock_get:
            mock_get.return_value.status_code = 200
            mock_get.return_value.text = html
            request = Request("https://example.com")
            result = await middleware.process_request(request, None)
            
            assert result.meta.get("playwright") is True
            assert result.meta.get("playwright_include_page") is True
            assert result.meta.get("playwright_context") == "default"
            assert "playwright_page_methods" in result.meta
            assert len(result.meta["playwright_page_methods"]) > 0


# ============================================================================
# TEXT DENSITY TESTS
# ============================================================================

class TestTextDensity:
    
    def test_high_text_density(self, middleware):
        """Article with lots of text → high density."""
        html = "<html><body>" + "<p>" + "Word " * 500 + "</p>" + "</body></html>"
        density = middleware._calculate_text_density(html)
        assert density > 0.5, f"Expected high density, got {density}"
    
    def test_low_text_density_spa(self, middleware):
        """SPA with mostly markup → low density."""
        html = (
            "<html><body>"
            + '<div class="container"><div class="row"><div class="col">'
            + '<div id="app"></div>'
            + "</div></div></div>"
            + "</body></html>"
        )
        density = middleware._calculate_text_density(html)
        assert density < 0.05, f"Expected low density for SPA, got {density}"
    
    def test_empty_html(self, middleware):
        """Empty HTML → zero density."""
        density = middleware._calculate_text_density("")
        assert density == 0.0


# ============================================================================
# SCRIPT RATIO TESTS
# ============================================================================

class TestScriptRatio:
    
    def test_no_scripts(self, middleware):
        html = "<html><body><h1>Hello</h1></body></html>"
        ratio = middleware._script_tag_ratio(html)
        assert ratio == 0.0
    
    def test_heavy_scripts(self, middleware):
        html = "<html>" + "<script></script>" * 10 + "<body></body></html>"
        ratio = middleware._script_tag_ratio(html)
        assert ratio > 0.3, f"Expected high ratio, got {ratio}"
    
    def test_balanced_page(self, middleware):
        html = "<html><head><script></script></head><body><h1>Hi</h1><p>Text</p></body></html>"
        ratio = middleware._script_tag_ratio(html)
        assert 0.0 <= ratio <= 0.3, f"Expected moderate ratio, got {ratio}"
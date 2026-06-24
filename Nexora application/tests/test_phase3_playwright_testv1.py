"""test_phase3_playwright.py"""
import os
import sys
import tempfile
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from scrapy.http import Request
from nexora_crawler.middlewares.dynamic_detection import DynamicDetectionMiddleware




class TestDynamicDetection:
    @pytest.fixture
    def middleware(self):
        crawler = MagicMock()
        crawler.settings = MagicMock()
        crawler.settings.getbool.side_effect = lambda k, default=False: {
            "NEXORA_PLAYWRIGHT_ENABLED": True,
            "NEXORA_STEALTH_ENABLED": True,
        }.get(k, default)
        crawler.settings.get.return_value = "./data/test_profiles.db"
        
        # ...
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = os.path.join(tmpdir, "test_profiles.db")
            crawler.settings.get.return_value = db_path
            mw = DynamicDetectionMiddleware(crawler)
            mw._client = AsyncMock()
            yield mw
        
        mw = DynamicDetectionMiddleware(crawler)
        # Initialize the client that spider_opened() normally creates
        import httpx
        mw._client = httpx.AsyncClient()
        return mw
    
   
    
    @pytest.mark.asyncio
    async def test_react_app_needs_playwright(self, middleware):
        html = '<html><head><meta name="generator" content="Next.js"/></head><body><div id="__next"></div></body></html>'
        with patch.object(middleware._client, 'get', new_callable=AsyncMock) as mock_get:
            mock_get.return_value.status_code = 200
            mock_get.return_value.text = html
            request = Request("https://react-app.com")
            result = await middleware.process_request(request, None)
            assert result is not None
            assert result.meta.get("playwright") is True
    
    @pytest.mark.asyncio
    async def test_cloudflare_block(self, middleware):
        html = "<html><div class='cf-browser-verification'>Checking...</div></html>"
        with patch.object(middleware._client, 'get', new_callable=AsyncMock) as mock_get:
            mock_get.return_value.status_code = 403
            mock_get.return_value.text = html
            request = Request("https://protected-site.com")
            result = await middleware.process_request(request, None)
            assert result is not None
            assert result.meta.get("playwright") is True
    
    def test_framework_detection(self, middleware):
        test_cases = [
            ('<meta name="generator" content="Next.js 14"/>', "next.js"),
            ('<div data-reactroot="">', "react"),
            ('<div data-v-1234abcd>', "vue"),
            ('<html ng-app="myApp">', "angular"),
        ]
        for html, expected in test_cases:
            detected = middleware._detect_framework(html)
            assert detected == expected
            
    @pytest.mark.asyncio
    async def test_static_page_no_js(self, middleware):
        html = "<html><body><h1>Hello</h1><p>Content here.</p></body></html>"
        with patch.object(middleware._client, 'get', new_callable=AsyncMock) as mock_get:
            mock_get.return_value.status_code = 200
            mock_get.return_value.text = html
            request = Request("https://example.com/page")
            
            # Debug: check what probe returns
            needs_js = await middleware._probe_page("https://example.com/page", None)
            print(f"DEBUG: _probe_page returned {needs_js}")
            
            result = await middleware.process_request(request, None)
            assert result is None
            


      
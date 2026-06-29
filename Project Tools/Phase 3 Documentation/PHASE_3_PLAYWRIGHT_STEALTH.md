# NEXORA PHASE 3 IMPLEMENTATION FILE
# Selective Playwright Integration & Stealth Anti-Bot Evasion
# Version: 1.0.0 | Date: 2026-06-24
# Priority: P0 - BLOCKS ALL SUBSEQUENT PHASES

---

## 1. ARCHITECTURAL OVERVIEW & WORKFLOW

### 1.1 Core Philosophy: Selective Rendering, Not Universal

Firecrawl runs Playwright for every single request - reliable but catastrophically slow and resource-heavy (16+ GB RAM). Nexora takes the opposite approach: HTTP first, Playwright only when necessary. This preserves our ~500 MB RAM footprint while achieving 100% coverage.

### 1.2 Why This Architecture Wins

| Metric | Firecrawl (Always Playwright) | Nexora Phase 3 (Selective) |
|--------|------------------------------|----------------------------|
| Avg. Time per Page | 3-8 seconds | 0.3-1.5 seconds (static) / 3-5s (JS) |
| RAM per Worker | 3-4 GB | 150-500 MB (static) / 1-2 GB (JS) |
| Coverage | 99%+ | 99%+ (with fallback) |
| Cost at Scale | $$$$ (browser infra) | $ (mostly HTTP) |

### 1.3 Detection Logic: When to Use Playwright

A request is routed to Playwright if ANY of these conditions are met:

1. **Empty Body Check**: Static fetch returns `<body></body>` or minimal content (SPA shell)
2. **Text Density Ratio**: `len(visible_text) / len(raw_html) < 0.05` (heavy JS frameworks)
3. **Meta Tag Detection**: `<meta name="generator" content="Next.js">`, `Gatsby`, `Nuxt`
4. **Script Tag Density**: `script_tags / total_tags > 0.3` (client-side rendered)
5. **Anti-Bot Block**: Response contains Cloudflare challenge, CAPTCHA, or 403 with bot headers
6. **User Override**: Request meta explicitly sets `"playwright": True`

---

## 2. TECHNICAL REQUIREMENTS & DEPENDENCIES

### 2.1 New Dependencies

```bash
# Core Playwright integration
pip install scrapy-playwright==0.0.34

# Stealth evasion layer
pip install playwright-stealth==1.0.6

# Browser binaries (one-time, ~150 MB)
playwright install chromium

# Optional: For site profile caching
pip install aiosqlite==0.20.0
```

### 2.2 System Requirements

| Component | Minimum | Recommended |
|-----------|---------|-------------|
| Python | 3.10 | 3.12 |
| RAM (static mode) | 512 MB | 1 GB |
| RAM (with Playwright) | 2 GB | 4 GB |
| Disk (browser cache) | 500 MB | 2 GB |
| OS | Windows 10 / Linux / macOS | Windows 11 / Ubuntu 22.04 |

### 2.3 Environment Variables

```bash
# .env file
NEXORA_PLAYWRIGHT_ENABLED=true
NEXORA_PLAYWRIGHT_HEADLESS=true
NEXORA_PLAYWRIGHT_MAX_PAGES=5
NEXORA_PLAYWRIGHT_TIMEOUT=30000
NEXORA_STEALTH_ENABLED=true
NEXORA_SITE_PROFILE_DB=./data/site_profiles.db
```

---

## 3. STEP-BY-STEP IMPLEMENTATION BLUEPRINT

### Step 1: Install & Configure scrapy-playwright

**File**: `nexora_crawler/settings.py` (additions)

```python
# PHASE 3: PLAYWRIGHT INTEGRATION SETTINGS

# Async reactor required for Playwright
TWISTED_REACTOR = "twisted.internet.asyncioreactor.AsyncioSelectorReactor"

# Download handlers
DOWNLOAD_HANDLERS = {
    "http": "scrapy_playwright.handler.ScrapyPlaywrightDownloadHandler",
    "https": "scrapy_playwright.handler.ScrapyPlaywrightDownloadHandler",
}

PLAYWRIGHT_BROWSER_TYPE = "chromium"
PLAYWRIGHT_LAUNCH_OPTIONS = {
    "headless": True,
    "args": [
        "--disable-blink-features=AutomationControlled",
        "--disable-dev-shm-usage",
        "--no-first-run",
        "--no-default-browser-check",
        "--disable-background-networking",
        "--disable-background-timer-throttling",
        "--disable-renderer-backgrounding",
        "--disable-features=IsolateOrigins,site-per-process",
        "--disable-site-isolation-trials",
    ],
}

PLAYWRIGHT_MAX_PAGES_PER_CONTEXT = 5
PLAYWRIGHT_DEFAULT_NAVIGATION_TIMEOUT = 30000
```

### Step 2: Build the DynamicDetectionMiddleware

**File**: `nexora_crawler/middlewares/dynamic_detection.py` (NEW)

This is the brain of Phase 3. It decides HTTP vs Playwright per-request.

```python
"""
DynamicDetectionMiddleware - Phase 3 Core Component
Decides whether a page needs JavaScript rendering or can be fetched statically.
Implements selective Playwright routing with site profile caching.
"""

import asyncio
import hashlib
import json
import logging
import os
import re
import sqlite3
from typing import Optional
from urllib.parse import urlparse

import httpx
from scrapy import signals
from scrapy.http import Request
from scrapy_playwright.page import PageMethod

logger = logging.getLogger(__name__)

# JS Framework Detection Patterns
JS_FRAMEWORK_PATTERNS = {
    "next.js": re.compile(r'<meta[^>]*name=["\']generator["\'][^>]*content=["\'][^"\']*Next\.js', re.I),
    "nuxt": re.compile(r'<meta[^>]*name=["\']generator["\'][^>]*content=["\'][^"\']*Nuxt', re.I),
    "gatsby": re.compile(r'<meta[^>]*name=["\']generator["\'][^>]*content=["\'][^"\']*Gatsby', re.I),
    "react": re.compile(r'data-reactroot|data-reactid|__NEXT_DATA__|_reactListening', re.I),
    "vue": re.compile(r'data-v-[a-f0-9]+|__VUE__|vue-router', re.I),
    "angular": re.compile(r'ng-version=|ng-app=|_nghost-', re.I),
    "svelte": re.compile(r'svelte-[a-z0-9]+|__svelte', re.I),
}

ANTI_BOT_INDICATORS = [
    re.compile(r'cf-browser-verification|cloudflare', re.I),
    re.compile(r'captcha|recaptcha|hcaptcha', re.I),
    re.compile(r'perimeterx|px-captcha', re.I),
    re.compile(r'datadome|captcha-delivery', re.I),
]


class DynamicDetectionMiddleware:
    """
    Scrapy downloader middleware that intelligently routes requests
    between static HTTP and Playwright JS rendering based on page characteristics.
    Priority: 543 (between retry (550) and default (500))
    """
    
    def __init__(self, crawler):
        self.crawler = crawler
        self.settings = crawler.settings
        self.playwright_enabled = self.settings.getbool("NEXORA_PLAYWRIGHT_ENABLED", True)
        self.stealth_enabled = self.settings.getbool("NEXORA_STEALTH_ENABLED", True)
        self.profile_db_path = self.settings.get("NEXORA_SITE_PROFILE_DB", "./data/site_profiles.db")
        self._profile_cache = {}
        self._client = None
        self._init_profile_db()
    
    @classmethod
    def from_crawler(cls, crawler):
        mw = cls(crawler)
        crawler.signals.connect(mw.spider_opened, signal=signals.spider_opened)
        crawler.signals.connect(mw.spider_closed, signal=signals.spider_closed)
        return mw
    
    def _init_profile_db(self):
        os.makedirs(os.path.dirname(self.profile_db_path) or ".", exist_ok=True)
        conn = sqlite3.connect(self.profile_db_path)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS site_profiles (
                domain TEXT PRIMARY KEY,
                requires_js INTEGER DEFAULT 0,
                framework TEXT,
                last_checked TEXT,
                success_count INTEGER DEFAULT 0,
                fail_count INTEGER DEFAULT 0,
                avg_load_time REAL DEFAULT 0.0
            )
        """)
        conn.commit()
        conn.close()
    
    def spider_opened(self, spider):
        self._client = httpx.AsyncClient(
            timeout=httpx.Timeout(5.0, connect=2.0),
            follow_redirects=True,
            headers={
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
                "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
                "Accept-Language": "en-US,en;q=0.5",
                "Accept-Encoding": "gzip, deflate, br",
                "DNT": "1",
                "Connection": "keep-alive",
            },
            http2=True,
        )
        logger.info("[DynamicDetection] Middleware initialized")
    
    def spider_closed(self, spider):
        if self._client:
            asyncio.create_task(self._client.aclose())
    
    # CORE DECISION ENGINE
    async def process_request(self, request, spider):
        if not self.playwright_enabled:
            return None
        if not self._is_html_request(request):
            return None
        if request.meta.get("playwright") is True:
            return self._apply_playwright_meta(request)
        if request.meta.get("playwright") is False:
            return None
        
        domain = urlparse(request.url).netloc
        profile = self._get_profile(domain)
        if profile and profile["requires_js"]:
            return self._apply_playwright_meta(request)
        if profile and not profile["requires_js"]:
            return None
        
        needs_js = await self._probe_page(request.url, spider)
        self._update_profile(domain, needs_js=needs_js)
        
        if needs_js:
            return self._apply_playwright_meta(request)
        return None
    
    # STATIC PROBE LOGIC
    async def _probe_page(self, url, spider):
        try:
            response = await self._client.get(url, follow_redirects=True)
            html = response.text
            
            if self._detects_anti_bot(html, response.status_code):
                return True
            
            body_match = re.search(r'<body[^>]*>(.*?)</body>', html, re.DOTALL | re.I)
            if body_match:
                body_content = body_match.group(1).strip()
                if len(body_content) < 200:
                    return True
            
            text_density = self._calculate_text_density(html)
            if text_density < 0.05:
                return True
            
            framework = self._detect_framework(html)
            if framework:
                return True
            
            script_ratio = self._script_tag_ratio(html)
            if script_ratio > 0.35:
                return True
            
            return False
        except Exception:
            return True
    
    def _detects_anti_bot(self, html, status_code):
        if status_code in (403, 429, 503):
            for pattern in ANTI_BOT_INDICATORS:
                if pattern.search(html):
                    return True
        return False
    
    def _calculate_text_density(self, html):
        text = re.sub(r'<[^>]+>', ' ', html)
        text = re.sub(r'\s+', ' ', text).strip()
        if not html:
            return 0.0
        return len(text) / len(html)
    
    def _detect_framework(self, html):
        for name, pattern in JS_FRAMEWORK_PATTERNS.items():
            if pattern.search(html):
                return name
        return None
    
    def _script_tag_ratio(self, html):
        total_tags = len(re.findall(r'<[a-zA-Z][^>]*>', html))
        script_tags = len(re.findall(r'<script', html, re.I))
        if total_tags == 0:
            return 0.0
        return script_tags / total_tags
    
    # PLAYWRIGHT META APPLICATION
    def _apply_playwright_meta(self, request):
        page_methods = [
            PageMethod("wait_for_load_state", "networkidle"),
        ]
        
        if self.stealth_enabled:
            stealth_script = self._build_stealth_script()
            page_methods.insert(0, PageMethod("add_init_script", script=stealth_script))
        
        request.meta.update({
            "playwright": True,
            "playwright_include_page": True,
            "playwright_page_methods": page_methods,
            "playwright_context": "default",
        })
        return request
    
    def _build_stealth_script(self):
        return """
        Object.defineProperty(navigator, 'webdriver', {
            get: () => undefined,
            enumerable: true,
            configurable: true
        });
        window.chrome = window.chrome || {};
        window.chrome.runtime = window.chrome.runtime || {};
        Object.defineProperty(navigator, 'plugins', {
            get: () => [
                {name: 'Chrome PDF Plugin', filename: 'internal-pdf-viewer'},
                {name: 'Native Client', filename: 'native_client.nmf'}
            ]
        });
        Object.defineProperty(navigator, 'mimeTypes', {
            get: () => [
                {type: 'application/pdf', suffixes: 'pdf', description: ''},
                {type: 'application/x-google-chrome-pdf', suffixes: 'pdf', description: ''}
            ]
        });
        const originalQuery = window.navigator.permissions.query;
        window.navigator.permissions.query = (parameters) => (
            parameters.name === 'notifications' 
                ? Promise.resolve({state: Notification.permission})
                : originalQuery(parameters)
        );
        const getParameter = WebGLRenderingContext.prototype.getParameter;
        WebGLRenderingContext.prototype.getParameter = function(parameter) {
            if (parameter === 37445) return 'Intel Inc.';
            if (parameter === 37446) return 'Intel Iris Xe Graphics';
            return getParameter(parameter);
        };
        """
    
    # PROFILE CACHE MANAGEMENT
    def _get_profile(self, domain):
        if domain in self._profile_cache:
            return self._profile_cache[domain]
        try:
            conn = sqlite3.connect(self.profile_db_path)
            conn.row_factory = sqlite3.Row
            row = conn.execute(
                "SELECT * FROM site_profiles WHERE domain = ?", (domain,)
            ).fetchone()
            conn.close()
            if row:
                profile = dict(row)
                self._profile_cache[domain] = profile
                return profile
        except Exception:
            pass
        return None
    
    def _update_profile(self, domain, needs_js=False, framework=None):
        from datetime import datetime, timezone
        profile = {
            "domain": domain,
            "requires_js": 1 if needs_js else 0,
            "framework": framework or "",
            "last_checked": datetime.now(timezone.utc).isoformat(),
            "success_count": 1,
            "fail_count": 0,
            "avg_load_time": 0.0,
        }
        self._profile_cache[domain] = profile
        try:
            conn = sqlite3.connect(self.profile_db_path)
            conn.execute("""
                INSERT INTO site_profiles (domain, requires_js, framework, last_checked, success_count, fail_count, avg_load_time)
                VALUES (:domain, :requires_js, :framework, :last_checked, :success_count, :fail_count, :avg_load_time)
                ON CONFLICT(domain) DO UPDATE SET
                    requires_js = excluded.requires_js,
                    framework = excluded.framework,
                    last_checked = excluded.last_checked,
                    success_count = site_profiles.success_count + 1
            """, profile)
            conn.commit()
            conn.close()
        except Exception:
            pass
    
    def _is_html_request(self, request):
        url = request.url.lower()
        non_html = ('.jpg', '.jpeg', '.png', '.gif', '.css', '.js', 
                    '.pdf', '.zip', '.mp4', '.svg', '.ico', '.woff2')
        return not any(url.endswith(ext) for ext in non_html)
```

### Step 3: Add Playwright Cleanup Middleware

**File**: `nexora_crawler/middlewares/playwright_cleanup.py` (NEW)

```python
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
```

### Step 4: Update settings.py Registration

```python
# Add to DOWNLOADER_MIDDLEWARES:
DOWNLOADER_MIDDLEWARES = {
    # ... existing middlewares ...
    'nexora_crawler.middlewares.dynamic_detection.DynamicDetectionMiddleware': 543,
    'nexora_crawler.middlewares.playwright_cleanup.PlaywrightCleanupMiddleware': 900,
}
```

---

## 4. PRODUCTION CODE BLUEPRINT

### 4.1 Updated items.py Fields

```python
class NexoraPageItem(scrapy.Item):
    # Existing fields ...
    
    # Phase 3: Playwright tracking
    playwright_used = scrapy.Field()      # bool
    screenshot_path = scrapy.Field()      # str
    render_time_ms = scrapy.Field()       # float
    
    # Phase 3: Anti-bot metrics
    detection_score = scrapy.Field()      # float 0.0-1.0
    retry_count = scrapy.Field()          # int
```

### 4.2 Integration Test Script

```python
"""test_phase3_playwright.py"""
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
        return DynamicDetectionMiddleware(crawler)
    
    @pytest.mark.asyncio
    async def test_static_page_no_js(self, middleware):
        html = "<html><body><h1>Hello</h1><p>Content here.</p></body></html>"
        with patch.object(middleware._client, 'get', new_callable=AsyncMock) as mock_get:
            mock_get.return_value.status_code = 200
            mock_get.return_value.text = html
            request = Request("https://example.com/page")
            result = await middleware.process_request(request, None)
            assert result is None
    
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
```

---

## 5. WHAT SUCCESS LOOKS LIKE

### 5.1 Test Matrix

| Test ID | Scenario | Expected | Pass Criteria |
|---------|----------|----------|---------------|
| P3-T01 | Static site | HTTP handler, < 1s/page | playwright_used=false |
| P3-T02 | React/Next.js | Playwright renders DOM | playwright_used=true, body has content |
| P3-T03 | Cloudflare | Playwright + stealth bypass | Status 200, no CAPTCHA |
| P3-T04 | Cached profile | Second run skips probe | < 100ms decision time |
| P3-T05 | Override ON | Always Playwright | playwright_used=true |
| P3-T06 | Override OFF | Always HTTP | playwright_used=false |
| P3-T07 | Memory stability | 100 pages, mixed | No growth > 50 MB |
| P3-T08 | Stealth check | bot.sannysoft.com | Passes all detection tests |
| P3-T09 | Anti-bot bypass | DataDome/PerimeterX | Valid HTML, no challenge |
| P3-T10 | Concurrent JS | 5 JS sites simultaneously | All succeed, no timeout |

### 5.2 Performance Benchmarks

| Metric | Target | Acceptable |
|--------|--------|------------|
| Static fetch | 200-500 ms/page | < 1000 ms |
| Playwright fetch | 2000-5000 ms/page | < 8000 ms |
| Decision (cached) | < 50 ms | < 100 ms |
| Decision (probe) | < 500 ms | < 1000 ms |
| Memory (static) | 150-300 MB | < 500 MB |
| Memory (Playwright) | 800-1500 MB | < 2000 MB |

### 5.3 Definition of Done

- [ ] All 10 test cases pass
- [ ] Static pages load in < 1 second average
- [ ] JS pages render correctly with visible content
- [ ] Memory usage stays under 2 GB for 100-page crawl
- [ ] Site profile cache persists across spider restarts
- [ ] No navigator.webdriver=true detectable on bot.sannysoft.com
- [ ] Cloudflare/DataDome challenge pages bypassed successfully
- [ ] Existing Phase 2.6 tests still pass (no regression)

---

## 6. KNOWN LIMITATIONS

| Limitation | Mitigation | Phase |
|------------|-----------|-------|
| Playwright only Chromium | Acceptable - 95% coverage | P3 |
| TLS fingerprinting | Residential proxies (Phase 6) | P6 |
| Behavioral analysis | Random delays in Phase 4 | P4 |
| WebGL advanced | Canvas noise is basic | P6 |

---

## 7. NEXT PHASE GATE

Phase 3 is complete when all tests pass and benchmarks are met.
Phase 4 entry criteria: Phase 3 merged, clean Markdown output pipeline ready.
"""
DynamicDetectionMiddleware - Phase 3 Core Component
Decides whether a page needs JavaScript rendering or can be fetched statically.
Implements selective Playwright routing with site profile caching and TTL invalidation.

Architecture: Static-first with explainable browser fallback.
Every Playwright-routing decision is logged with the specific reason.
"""

import asyncio
import hashlib
import json
import logging
import os
import re
import sqlite3
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional
from urllib.parse import urlparse

import httpx
from scrapy import signals
from scrapy.http import Request
from scrapy_playwright.page import PageMethod

logger = logging.getLogger(__name__)

# JS Framework Detection Patterns
JS_FRAMEWORK_PATTERNS = {
    "next.js": re.compile(r'<meta[^>]*name=["\']generator["\'][^>]*content=["\'][^"\']*Next\.js|__NEXT_DATA__|id=["\']__next["\']|__NEXT_F__|next-future|/_next/', re.I),
    "nuxt": re.compile(r'<meta[^>]*name=["\']generator["\'][^>]*content=["\'][^"\']*Nuxt', re.I),
    "gatsby": re.compile(r'<meta[^>]*name=["\']generator["\'][^>]*content=["\'][^"\']*Gatsby', re.I),
    "react": re.compile(r'data-reactroot|data-reactid|_reactListening', re.I),
    "vue": re.compile(r'data-v-[a-f0-9]+|__VUE__|vue-router', re.I),
    "angular": re.compile(r'ng-version=|ng-app=|_nghost-', re.I),
    "svelte": re.compile(r'svelte-[a-z0-9]+|__svelte', re.I),
}

# Anti-bot challenge detection — specific patterns only, no broad matches
ANTI_BOT_INDICATORS = [
    re.compile(r'cf-browser-verification|cf-challenge|turnstile', re.I),
    re.compile(r'captcha|recaptcha|hcaptcha', re.I),
    re.compile(r'perimeterx|px-captcha', re.I),
    re.compile(r'datadome|captcha-delivery', re.I),
]

# Cache TTL: re-probe a site after this many seconds (default 24 hours)
PROFILE_CACHE_TTL_SECONDS = 86400

# Resolve profile DB relative to this file's location
_PROJECT_ROOT = Path(__file__).resolve().parents[2]


class DynamicDetectionMiddleware:
    """
    Scrapy downloader middleware that intelligently routes requests
    between static HTTP and Playwright JS rendering based on page characteristics.
    Priority: 542 (runs BEFORE ScrapyPlaywrightDownloadHandler at 543)
    """

    def __init__(self, crawler):
        self.crawler = crawler
        self.settings = crawler.settings
        self.playwright_enabled = self.settings.getbool("NEXORA_PLAYWRIGHT_ENABLED", True)
        self.stealth_enabled = self.settings.getbool("NEXORA_STEALTH_ENABLED", True)
        # Resolve DB path relative to project root to avoid CWD issues
        raw_db_path = self.settings.get("NEXORA_SITE_PROFILE_DB", "data/site_profiles.db")
        self.profile_db_path = str(_PROJECT_ROOT / raw_db_path)
        self._profile_cache = {}
        self._profile_cache_timestamps = {}  # domain -> timestamp of last probe
        self._client: Optional[httpx.AsyncClient] = None
        self._init_profile_db()

    @classmethod
    def from_crawler(cls, crawler):
        mw = cls(crawler)
        crawler.signals.connect(mw.spider_opened, signal=signals.spider_opened)
        crawler.signals.connect(mw.spider_closed, signal=signals.spider_closed)
        return mw

    def _init_profile_db(self):
        """Create profile directory and database table if they don't exist."""
        db_dir = os.path.dirname(self.profile_db_path)
        if db_dir:
            os.makedirs(db_dir, exist_ok=True)
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
        logger.info("[DynamicDetection] Profile DB initialized at %s", self.profile_db_path)

    def spider_opened(self, spider):
        self._client = self._create_http_client()
        logger.info("[DynamicDetection] Middleware initialized")

    def _create_http_client(self):
        return httpx.AsyncClient(
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

    def spider_closed(self, spider):
        """Safely close the HTTP client during spider shutdown.

        Uses ensure_future() instead of create_task() because the event
        loop may be in a shutting-down state when spider_closed fires.
        """
        if self._client:
            try:
                loop = asyncio.get_event_loop()
                if loop.is_running() and not loop.is_closed():
                    asyncio.ensure_future(self._client.aclose())
                    logger.debug("[DynamicDetection] HTTP client close scheduled")
            except RuntimeError:
                # No event loop available — synchronous cleanup fallback
                logger.warning("[DynamicDetection] No event loop for client close")

    # CORE DECISION ENGINE
    async def process_request(self, request, spider):
        if not self.playwright_enabled:
            logger.debug("[DD] Playwright disabled — all requests go HTTP")
            return None
        if not self._is_html_request(request):
            logger.debug("[DD] Non-HTML request skipped: %s", request.url)
            return None
        if request.meta.get("playwright") is True:
            logger.debug("[DD] User override: force Playwright for %s", request.url)
            return self._apply_playwright_meta(request)
        if request.meta.get("playwright") is False:
            logger.debug("[DD] User override: force HTTP for %s", request.url)
            return None

        domain = urlparse(request.url).netloc
        profile = self._get_profile(domain)

        # Check cache TTL — re-probe if stale
        if profile and profile["requires_js"]:
            if self._is_cache_fresh(domain):
                logger.debug("[DD] Cached profile: JS required for %s", domain)
                return self._apply_playwright_meta(request)
            else:
                logger.debug("[DD] Cached profile stale — re-probing %s", domain)
                profile = None  # Force re-probe

        if profile and not profile["requires_js"]:
            if self._is_cache_fresh(domain):
                logger.debug("[DD] Cached profile: static OK for %s", domain)
                return None
            else:
                logger.debug("[DD] Cached profile stale — re-probing %s", domain)
                profile = None  # Force re-probe

        needs_js, reason = await self._probe_page(request.url, spider)
        self._update_profile(domain, needs_js=needs_js)
        self._profile_cache_timestamps[domain] = time.time()

        if needs_js:
            logger.info("[DD] Playwright routing: %s — reason: %s", request.url, reason)
            return self._apply_playwright_meta(request)
        logger.debug("[DD] Static OK: %s", request.url)
        return None

    def _is_cache_fresh(self, domain) -> bool:
        """Check if the cached profile is still within TTL."""
        timestamp = self._profile_cache_timestamps.get(domain, 0)
        return (time.time() - timestamp) < PROFILE_CACHE_TTL_SECONDS

    # STATIC PROBE LOGIC
    async def _probe_page(self, url, spider):
        """Probe a page via HTTP and decide if it needs Playwright.

        Returns: (needs_js: bool, reason: str)
        """
        try:
            if self._client is None:
                self._client = self._create_http_client()
            response = await self._client.get(url, follow_redirects=True)
            html = response.text

            # 1. Anti-bot challenge detection
            if self._detects_anti_bot(html, response.status_code):
                return (True, "anti-bot challenge detected")

            # 2. Body content analysis — short body only triggers if also has scripts
            body_match = re.search(r'<body[^>]*>(.*?)</body>', html, re.DOTALL | re.I)
            script_ratio = self._script_tag_ratio(html)

            if body_match:
                body_content = body_match.group(1).strip()
                if len(body_content) < 200 and script_ratio > 0.15:
                    return (True, f"short body ({len(body_content)} chars) + significant JS ratio ({script_ratio:.2f})")

            # 3. Text density — very low means mostly markup (SPA shell)
            text_density = self._calculate_text_density(html)
            if text_density < 0.05:
                return (True, f"very low text density ({text_density:.4f})")

            # 4. JS framework detection
            framework = self._detect_framework(html)
            if framework:
                return (True, f"JS framework detected: {framework}")

            # 5. High script-to-tag ratio
            if script_ratio > 0.35:
                return (True, f"high script ratio ({script_ratio:.2f})")

            return (False, "static page — no JS needed")
        except Exception as exc:
            logger.warning("[DD] Probe failed for %s: %s — falling back to Playwright", url, exc)
            return (True, f"probe error: {exc}")

    def _detects_anti_bot(self, html, status_code):
        """Detect anti-bot challenges by matching specific indicators.
        
        Only matches anti-bot challenge-specific patterns (not broad terms like "cloudflare").
        """
        if status_code in (403, 429, 503):
            for pattern in ANTI_BOT_INDICATORS:
                if pattern.search(html):
                    return True
        return False

    def _calculate_text_density(self, html):
        """Calculate ratio of visible text to markup."""
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
        """Ratio of <script> tags to total HTML tags."""
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
        """Build JavaScript that patches common bot detection properties.
        
        Patches:
        - navigator.webdriver -> undefined
        - window.chrome.runtime -> present
        - navigator.plugins -> realistic plugins
        - navigator.mimeTypes -> realistic MIME types
        - navigator.permissions.query -> safe notifications
        - WebGL vendor/renderer -> spoofed Intel values
        """
        return """
        (() => {
            // Patches navigator.webdriver
            const navigatorProxy = new Proxy(navigator, {
                get: (target, prop) => {
                    if (prop === 'webdriver') return undefined;
                    return target[prop];
                }
            });
            Object.defineProperty(navigator, 'webdriver', {
                get: () => undefined,
                configurable: true
            });
            
            // Creates chrome.runtime if missing
            window.chrome = window.chrome || {};
            window.chrome.runtime = window.chrome.runtime || {};
            window.chrome.loadTimes = () => {};
            
            // Patches navigator.plugins
            Object.defineProperty(navigator, 'plugins', {
                get: () => [
                    {name: 'Chrome PDF Plugin', filename: 'internal-pdf-viewer'},
                    {name: 'Native Client', filename: 'native_client.nmf'}
                ],
                configurable: true
            });
            
            // Patches navigator.mimeTypes
            Object.defineProperty(navigator, 'mimeTypes', {
                get: () => [
                    {type: 'application/pdf', suffixes: 'pdf', description: ''},
                    {type: 'application/x-google-chrome-pdf', suffixes: 'pdf', description: ''}
                ],
                configurable: true
            });
            
            // Safe permissions.query — only handle notifications
            const originalQuery = window.navigator.permissions.query;
            window.navigator.permissions.query = (parameters) => (
                parameters.name === 'notifications'
                    ? Promise.resolve({state: Notification.permission})
                    : originalQuery(parameters)
            );
            
            // Spoofs WebGL vendor to avoid GPU fingerprinting
            const getParameter = WebGLRenderingContext.prototype.getParameter;
            WebGLRenderingContext.prototype.getParameter = function(parameter) {
                if (parameter === 37445) return 'Intel Inc.';
                if (parameter === 37446) return 'Intel Iris Xe Graphics';
                return getParameter(parameter);
            };
        })();
        """

    # PROFILE CACHE MANAGEMENT
    def _get_profile(self, domain):
        """Get site profile from in-memory cache or SQLite database."""
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
        except Exception as exc:
            logger.warning("[DD] DB read failed for %s: %s", domain, exc)
        return None

    def _update_profile(self, domain, needs_js=False, framework=None):
        """Update or insert site profile in SQLite and in-memory cache."""
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
        except Exception as exc:
            logger.warning("[DD] DB write failed for %s: %s", domain, exc)

    def _is_html_request(self, request):
        """Check if a request targets an HTML page (not an asset).
        
        Uses urlparse to extract only the path, ignoring query strings
        and fragments that would break simple .endswith() checks.
        """
        path = urlparse(request.url).path.lower()
        non_html_extensions = ('.jpg', '.jpeg', '.png', '.gif', '.css', '.js',
                               '.pdf', '.zip', '.mp4', '.svg', '.ico', '.woff2')
        return not path.endswith(non_html_extensions)
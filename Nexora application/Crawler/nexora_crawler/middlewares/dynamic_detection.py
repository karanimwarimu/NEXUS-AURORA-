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
            response = await self._client.get(url, follow_redirects=True) # type: ignore
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
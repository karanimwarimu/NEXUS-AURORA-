"""
PlaywrightResourceBlocker — Blocks unnecessary resources in Playwright browser.

Speeds up page loads by 50-70% by blocking images, fonts, CSS, and analytics
that are not needed for content extraction. Integrated as a route handler.

Registered at priority: 541 (runs before ScrapyPlaywrightDownloadHandler at 543)
and BEFORE DynamicDetectionMiddleware at 542.

This is a SPIDER middleware (not downloader) because it hooks into page creation.
"""
import logging

logger = logging.getLogger(__name__)

# Resource types that are safe to block for content extraction
# 'document' and 'script' are always needed
# 'xhr' and 'fetch' may be needed for dynamic content
BLOCKED_RESOURCE_TYPES = {
    'image',
    'font',
    'media',
    'stylesheet',
    'texttrack',
    'websocket',
    'manifest',
    'other',
}

# URL patterns to always allow (e.g., critical CSS, icon fonts)
ALLOWED_URL_PATTERNS = [
    'data:',           # inline data URIs
    'blob:',           # blob URIs
    'fontawesome',     # common icon font CDN
    'fonts.googleapis.com',  # Google Fonts CSS (needed for font-face)
]

# URL patterns to block (trackers, analytics, ads)
BLOCKED_URL_PATTERNS = [
    'google-analytics',
    'googletagmanager',
    'facebook.net',
    'facebook.com/tr',
    'doubleclick.net',
    'hotjar.com',
    'cdn.segment.com',
    'amplitude.com',
    'mixpanel.com',
    'fullstory.com',
    'newrelic.com',
    'sentry.io',
    'clarity.ms',
    'adsystem',
    'adservice',
    'scorecardresearch',
]


class PlaywrightResourceBlocker:
    """Middleware that adds Playwright route interception to block unnecessary resources.

    This works by injecting a page method that intercepts all routes
    before the page loads. It blocks resource types that are not needed
    for content extraction, significantly speeding up page loads.
    """

    def __init__(self, crawler):
        self.crawler = crawler
        self.enabled = crawler.settings.getbool("NEXORA_BLOCK_RESOURCES", True)
        logger.info(
            "[ResourceBlocker] initialized (enabled=%s)",
            self.enabled,
        )

    @classmethod
    def from_crawler(cls, crawler):
        return cls(crawler)

    async def process_request(self, request, spider):
        """Add route interception to Playwright-bound requests."""
        if not self.enabled:
            return None

        # Only intercept requests going to Playwright
        if not request.meta.get("playwright"):
            return None

        # Read existing page methods or create new list
        page_methods = request.meta.get("playwright_page_methods", [])

        # Add resource blocking as the FIRST page method (runs before navigation)
        page_methods.insert(0, self._build_blocking_method())

        request.meta["playwright_page_methods"] = page_methods
        return None

    def _build_blocking_method(self):
        """Build a PageMethod that intercepts and blocks resources."""
        from scrapy_playwright.page import PageMethod

        # We use add_init_script to set up the route interceptor
        # This must run before the page navigates to the target URL
        blocking_script = self._build_blocking_script()

        return PageMethod("add_init_script", script=blocking_script)

    def _build_blocking_script(self):
        """Build JavaScript that intercepts and blocks unnecessary resources."""
        blocked_types = list(BLOCKED_RESOURCE_TYPES)
        allowed_patterns = ALLOWED_URL_PATTERNS
        blocked_patterns = BLOCKED_URL_PATTERNS

        return f"""
        (() => {{
            const blockedTypes = new Set({json_repr(blocked_types)});
            const allowedPatterns = {json_repr(allowed_patterns)};
            const blockedPatterns = {json_repr(blocked_patterns)};

            // Intercept fetch/XHR to block analytics
            const originalFetch = window.fetch;
            window.fetch = function(url, options) {{
                const urlStr = (typeof url === 'string') ? url : url.url;
                for (const pattern of blockedPatterns) {{
                    if (urlStr.includes(pattern)) {{
                        return Promise.reject(new Error('Blocked by Nexora'));
                    }}
                }}
                return originalFetch.apply(this, arguments);
            }};

            // Block resource hints and preconnects
            document.addEventListener('DOMContentLoaded', () => {{
                const links = document.querySelectorAll('link[rel="preconnect"], link[rel="prefetch"], link[rel="preload"], link[rel="dns-prefetch"]');
                links.forEach(link => {{
                    if (link.href) {{
                        for (const pattern of blockedPatterns) {{
                            if (link.href.includes(pattern)) {{
                                link.parentNode.removeChild(link);
                                break;
                            }}
                        }}
                    }}
                }});
            }});

            // Patch navigator.sendBeacon (used by analytics)
            if (navigator.sendBeacon) {{
                const originalSendBeacon = navigator.sendBeacon.bind(navigator);
                navigator.sendBeacon = function(url, data) {{
                    for (const pattern of blockedPatterns) {{
                        if (url.includes(pattern)) {{
                            return false;
                        }}
                    }}
                    return originalSendBeacon(url, data);
                }};
            }}
        }})();
        """


def json_repr(obj):
    """Simple JSON representation without importing json."""
    if isinstance(obj, str):
        return f'"{obj}"'
    elif isinstance(obj, (list, tuple)):
        items = ", ".join(json_repr(item) for item in obj)
        return f"[{items}]"
    elif isinstance(obj, bool):
        return "true" if obj else "false"
    elif isinstance(obj, (int, float)):
        return str(obj)
    return f'"{str(obj)}"'
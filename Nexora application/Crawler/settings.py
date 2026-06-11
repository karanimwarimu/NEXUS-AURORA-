"""
nexora_crawler/settings.py
===========================
Central configuration for the Scrapy crawling engine.

Every value here is documented with WHY it exists, not just what it does.
Phase 3 additions are clearly marked so you know exactly what to uncomment.
"""

# ── Identity ──────────────────────────────────────────────────────────────────
BOT_NAME    = "nexora_crawler"
SPIDER_MODULES      = ["nexora_crawler.spiders"]
NEWSPIDER_MODULE    = "nexora_crawler.spiders"

# ── Politeness — CRITICAL for responsible crawling ───────────────────────────
# Respect robots.txt — never disable this unless you have explicit permission
ROBOTSTXT_OBEY = True

# Minimum delay between requests to the SAME domain (seconds).
# Prevents hammering servers. Scrapy will auto-randomise between
# DOWNLOAD_DELAY and 2x DOWNLOAD_DELAY when RANDOMIZE_DOWNLOAD_DELAY=True.
DOWNLOAD_DELAY = 1.5
RANDOMIZE_DOWNLOAD_DELAY = True

# Max concurrent requests across ALL domains
CONCURRENT_REQUESTS = 8

# Max concurrent requests to a SINGLE domain — keeps us polite per host
CONCURRENT_REQUESTS_PER_DOMAIN = 2

# Request timeout — abort if server doesn't respond within N seconds
DOWNLOAD_TIMEOUT = 20

# ── Crawl depth control ───────────────────────────────────────────────────────
# How many link-hops from seed URLs to follow.
# 0 = seed only, 1 = seed + direct links, 2 = one more hop, etc.
# Keep low during development; raise for production crawls.
DEPTH_LIMIT = 2

# ── Duplicate URL filter ──────────────────────────────────────────────────────
# Scrapy's built-in filter — prevents re-crawling the same URL.
DUPEFILTER_CLASS = "scrapy.dupefilters.RFPDupeFilter"

# ── Middlewares ───────────────────────────────────────────────────────────────
SPIDER_MIDDLEWARES = {
    "nexora_crawler.middlewares.NexoraSpiderMiddleware": 543,
}

DOWNLOADER_MIDDLEWARES = {
    # Disable Scrapy's default User-Agent middleware
    "scrapy.downloadermiddlewares.useragent.UserAgentMiddleware": None,
    # Enable our rotating User-Agent middleware
    "nexora_crawler.middlewares.NexoraUserAgentMiddleware": 500,
    # Phase 3: uncomment when scrapy-playwright is installed
    # "nexora_crawler.middlewares.PlaywrightRoutingMiddleware": 600,
}

# ── Item Pipelines ────────────────────────────────────────────────────────────
# Numbers = execution order (lower runs first)
ITEM_PIPELINES = {
    "nexora_crawler.pipelines.NexoraExtractionPipeline": 100,  # Phase 1 hook
    "nexora_crawler.pipelines.NexoraExportPipeline":     200,  # per-page files
    "nexora_crawler.pipelines.NexoraDatasetPipeline":    300,  # master CSV
}

# ── HTTP Cache (speeds up development re-runs) ────────────────────────────────
# Caches responses to disk so re-running the spider doesn't re-fetch pages.
# Disable in production or when you need fresh data.
HTTPCACHE_ENABLED      = True
HTTPCACHE_EXPIRATION_SECS = 3600        # cache valid for 1 hour
HTTPCACHE_DIR          = "httpcache"
HTTPCACHE_IGNORE_HTTP_CODES = [503, 504, 400, 403, 404, 408]

# ── Request headers ───────────────────────────────────────────────────────────
DEFAULT_REQUEST_HEADERS = {
    "Accept":          "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9",
    "Accept-Encoding": "gzip, deflate, br",
}

# ── Logging ───────────────────────────────────────────────────────────────────
LOG_LEVEL = "INFO"

# ── Feed exports (optional bulk export) ──────────────────────────────────────
# Uncomment to also export all items to a single JSONL file via Scrapy's feed
# FEEDS = {
#     "output/scrapy_feed.jsonl": {"format": "jsonlines", "encoding": "utf8"},
# }

# ── Phase 3 Playwright settings (add when ready) ─────────────────────────────
# DOWNLOAD_HANDLERS = {
#     "http":  "scrapy_playwright.handler.ScrapyPlaywrightDownloadHandler",
#     "https": "scrapy_playwright.handler.ScrapyPlaywrightDownloadHandler",
# }
# TWISTED_REACTOR = "twisted.internet.asyncioreactor.AsyncioSelectorReactor"
# PLAYWRIGHT_BROWSER_TYPE = "chromium"
# PLAYWRIGHT_LAUNCH_OPTIONS = {"headless": True}

"""
nexora_crawler/settings.py
===========================
Central configuration for the Scrapy crawling engine.

Every value here is documented with WHY it exists.
Phase 3 additions are clearly marked — uncomment when ready.
"""

# ── Identity ──────────────────────────────────────────────────────────────────
BOT_NAME         = "nexora_crawler"
SPIDER_MODULES   = ["nexora_crawler.spiders"]
NEWSPIDER_MODULE = "nexora_crawler.spiders"
USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/124.0.0.0 Safari/537.36"
)

# ── Depth control — DEFAULT: single page only ────────────────────────────────
# 0 = fetch the seed URL only (default — safe, predictable)
# 1 = seed + all links on that page
# 2 = one more hop (can produce hundreds of pages on large sites)
# Override per-run: scrapy crawl nexora -a depth=1
# This is the HARD CEILING. Spider argument cannot exceed this value.
DEPTH_LIMIT = 0

# ── Politeness — CRITICAL for responsible crawling ───────────────────────────
ROBOTSTXT_OBEY = True

# Base delay between requests to the same domain (seconds).
# Actual delay is randomised between DOWNLOAD_DELAY and 2× DOWNLOAD_DELAY.
DOWNLOAD_DELAY            = 1.5
RANDOMIZE_DOWNLOAD_DELAY  = True

# Concurrent request caps — keep conservative for single-site use
CONCURRENT_REQUESTS               = 4
CONCURRENT_REQUESTS_PER_DOMAIN    = 1   # one request at a time per domain

# Request timeout
DOWNLOAD_TIMEOUT = 20

# ── AutoThrottle — adapts delay based on server response time ─────────────────
# Automatically slows down if the server is struggling.
# Fixes the static-delay issue flagged in the assessment.
AUTOTHROTTLE_ENABLED            = True
AUTOTHROTTLE_START_DELAY        = 1.0   # initial delay
AUTOTHROTTLE_MAX_DELAY          = 30.0  # never exceed this
AUTOTHROTTLE_TARGET_CONCURRENCY = 1.0   # aim for 1 parallel request per domain
AUTOTHROTTLE_DEBUG              = False  # set True to see delay adjustments in logs

# ── Retry — handles transient failures (503, 429, timeouts) ──────────────────
RETRY_ENABLED    = True
RETRY_TIMES      = 3
RETRY_HTTP_CODES = [500, 502, 503, 504, 408, 429]
# Scrapy default retry uses fixed delay; exponential backoff added in middleware

# ── Duplicate URL filter ──────────────────────────────────────────────────────
DUPEFILTER_CLASS = "scrapy.dupefilters.RFPDupeFilter"

# ── Security ──────────────────────────────────────────────────────────────────
# Disable Telnet console — security risk, not needed for development
TELNETCONSOLE_ENABLED = False

# ── Middlewares ───────────────────────────────────────────────────────────────
# Scrapy 2.16+ uses async middleware signatures by default.
# The spider middleware order is important — lower numbers run first.
SPIDER_MIDDLEWARES = {
    "nexora_crawler.middlewares.NexoraSpiderMiddleware": 543,
}

DOWNLOADER_MIDDLEWARES = {
    # Disable Scrapy's default User-Agent middleware
    "scrapy.downloadermiddlewares.useragent.UserAgentMiddleware": None,
    # Rotating User-Agent
    "nexora_crawler.middlewares.NexoraUserAgentMiddleware": 50,
    # Content-type guard — rejects PDFs, images, XML before they hit the pipeline
    "nexora_crawler.middlewares.ContentTypeFilterMiddleware": 510,
    # Phase 3: uncomment when scrapy-playwright is installed
    # "nexora_crawler.middlewares.PlaywrightRoutingMiddleware": 600,
}

# ── Item Pipelines ────────────────────────────────────────────────────────────
# Order matters: lower numbers run first.
# 100  Extraction  → 150  Styles  → 200  Export  → 300  Dataset
ITEM_PIPELINES = {
    "nexora_crawler.pipelines.NexoraExtractionPipeline": 100,
    "nexora_crawler.pipelines.NexoraStylePipeline":      150,  # style/theme
    "nexora_crawler.pipelines.NexoraExportPipeline":     200,
    "nexora_crawler.pipelines.NexoraDatasetPipeline":    300,
}

# ── HTTP Cache (dev only — speeds up re-runs without re-fetching) ─────────────
# Disable when you need fresh data or in production.
HTTPCACHE_ENABLED           = False
HTTPCACHE_EXPIRATION_SECS   = 3600
HTTPCACHE_DIR               = "httpcache"
HTTPCACHE_IGNORE_HTTP_CODES = [503, 504, 400, 403, 404, 408]

# ── Request headers ───────────────────────────────────────────────────────────
DEFAULT_REQUEST_HEADERS = {
    "Accept":          "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9",
    "Accept-Encoding": "gzip, deflate, br",
}

# ── Logging ───────────────────────────────────────────────────────────────────
LOG_LEVEL = "INFO"

# ── Phase 3 Playwright settings (uncomment when ready) ───────────────────────
# DOWNLOAD_HANDLERS = {
#     "http":  "scrapy_playwright.handler.ScrapyPlaywrightDownloadHandler",
#     "https": "scrapy_playwright.handler.ScrapyPlaywrightDownloadHandler",
# }
# TWISTED_REACTOR = "twisted.internet.asyncioreactor.AsyncioSelectorReactor"
# PLAYWRIGHT_BROWSER_TYPE = "chromium"
# PLAYWRIGHT_LAUNCH_OPTIONS = {"headless": True}

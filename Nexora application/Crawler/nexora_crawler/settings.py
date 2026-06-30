"""
nexora_crawler/settings.py
===========================
Central configuration for the Scrapy crawling engine.

Every value here is documented with WHY it exists.
Phase 3 additions are clearly marked — uncomment when ready.
Phase 4A: Added markdown, multimodal, schema enricher, metadata indexer, parquet pipelines.
"""

from pathlib import Path
from dotenv import load_dotenv

"""
Load environment variables from the .env file located next to this settings file.

File structure:
  Nexora application/
    Crawler/
      nexora_crawler/
        settings.py       ← we are here
        .env              ← env vars are here
Path: __file__ → parents[0]=nexora_crawler → parents[1]=Crawler → parents[2]=Nexora application
Use parents[1] to get the nexora_crawler directory containing .env
"""
env_path = Path(__file__).resolve().parent / ".env"
load_dotenv(env_path)

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
    # Content-type guard — rejects non-HTML responses, blocks URL patterns
    "nexora_crawler.middlewares.ContentTypeFilterMiddleware": 510,
    # Resource blocking — blocks images/fonts/analytics in Playwright pages (before PW handler)
    "nexora_crawler.middlewares.playwright_resource_blocker.PlaywrightResourceBlocker": 541,
    # Dynamic detection — identifies JS-heavy pages BEFORE Playwright handler (priority < 543)
    "nexora_crawler.middlewares.dynamic_detection.DynamicDetectionMiddleware": 542,
    # Playwright cleanup — closes pages to prevent memory leaks
    "nexora_crawler.middlewares.playwright_cleanup.PlaywrightCleanupMiddleware": 550,
    # Exponential backoff — retries with 1s → 2s → 4s → 8s delay for 429/503/408
    # (Import is from the middleware module file, not middlewares/__init__.py)
    "nexora_crawler.middlewares.exponential_backoff.ExponentialBackoffMiddleware": 700,
    # Proxy rotation — TODO Phase 5
    # "nexora_crawler.middlewares.ProxyRotationMiddleware": 800,
}

# ── Item Pipelines ────────────────────────────────────────────────────────────
# Order matters: lower numbers run first.
#
# Complete Phase 1-4A pipeline chain:
#   100  ExtractionPipeline          ← Phase 1-2: structured data extraction
#   110  MarkdownExtractionPipeline  ← Phase 4A: HTML → clean Markdown + multimodal assets
#   150  StylePipeline               ← Phase 2: visual design intelligence
#   160  UnifiedSchemaEnricher       ← Phase 4A: enforce unified schema defaults
#   165  MetadataIndexerPipeline     ← Phase 4A: persist to SQLite MetadataStore
#   250  Phase 4B pipelines          ← future: AI enrichment, chunking, embedding
#   450  ParquetExportPipeline       ← Phase 4A: compressed columnar export
#   500  ExportPipeline              ← Phase 1: per-page JSON + CSV files
#   600  DatasetPipeline             ← Phase 1: master dataset CSV
ITEM_PIPELINES = {
    "nexora_crawler.pipelines.NexoraExtractionPipeline": 100,
    "nexora_crawler.pipelines.markdown_pipeline.MarkdownExtractionPipeline": 110,
    "nexora_crawler.pipelines.NexoraStylePipeline": 150,
    "nexora_crawler.pipelines.schema_enricher.UnifiedSchemaEnricher": 160,
    "nexora_crawler.pipelines.metadata_indexer.MetadataIndexerPipeline": 165,
    # Phase 4B pipelines at 250+
    "nexora_crawler.pipelines.parquet_export.ParquetExportPipeline": 450,
    "nexora_crawler.pipelines.NexoraExportPipeline": 500,
    "nexora_crawler.pipelines.NexoraDatasetPipeline": 600,
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

# ── Phase 3: Playwright — OPT-IN via env var or .env ───────────────────────
# DynamicDetectionMiddleware reads this setting. When False (default), all
# requests go through standard HTTP — no playwright, no probe that tries to
# set playwright_meta on requests.
# Set NEXORA_PLAYWRIGHT_ENABLED=true in .env or environment to enable.
import os
NEXORA_PLAYWRIGHT_ENABLED = os.getenv("NEXORA_PLAYWRIGHT_ENABLED", "false").lower() in ("1", "true", "yes")
NEXORA_STEALTH_ENABLED = os.getenv("NEXORA_STEALTH_ENABLED", "true").lower() in ("1", "true", "yes")

if NEXORA_PLAYWRIGHT_ENABLED:
    # Async reactor required for Playwright
    TWISTED_REACTOR = "twisted.internet.asyncioreactor.AsyncioSelectorReactor"

    # Download handlers — Playwright routes requests through Chromium
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

    # Add Playwright handler middleware to the chain
    DOWNLOADER_MIDDLEWARES.update({
        "scrapy_playwright.handler.ScrapyPlaywrightDownloadHandler": 543,
    })


# ── Phase 4A: Markdown Pipeline Settings ──────────────────────────────────────
NEXORA_MARKDOWN_ENABLED = True
NEXORA_MARKDOWN_INCLUDE_COMMENTS = False
NEXORA_MARKDOWN_INCLUDE_TABLES = True
NEXORA_MARKDOWN_INCLUDE_LINKS = True
NEXORA_MARKDOWN_DEDUPLICATE = True

# ── Phase 4A: Parquet Export Settings ─────────────────────────────────────────
NEXORA_PARQUET_ENABLED = True
NEXORA_PARQUET_COMPRESSION = 'snappy'  # snappy | gzip | brotli | zstd
NEXORA_PARQUET_ROW_GROUP_SIZE = 10000
NEXORA_PARQUET_OUTPUT = './output/parquet'

# ── Phase 4A: Metadata Store Settings ─────────────────────────────────────────
NEXORA_METADATA_DB = './data/nexora_metadata.db'
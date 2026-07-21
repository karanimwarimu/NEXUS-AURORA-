"""
nexora_crawler/settings.py
===========================
Central configuration for the Scrapy crawling engine.

Every value here is documented with WHY it exists.
Phase 3 additions are clearly marked — uncomment when ready.
Phase 4A: Added markdown, multimodal, schema enricher, metadata indexer, parquet pipelines.
"""

import os
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
    # Exponential backoff — retries with 1s → 2s → 4s → 8s delay for 429/503/408
    # (Import is from the middleware module file, not middlewares/__init__.py)
    "nexora_crawler.middlewares.exponential_backoff.ExponentialBackoffMiddleware": 700,
    # Proxy rotation — TODO Phase 5
    # "nexora_crawler.middlewares.ProxyRotationMiddleware": 800,
}

# ── Enrichment mode ───────────────────────────────────────────────────────────
# Controls WHEN AI enrichment (summary/tags/vectors) runs:
#   "eager"     = run inline during the crawl (default — current behavior).
#   "on_demand" = skip enrichment during crawl; run it later via the offline
#                 `enrich` command over already-saved pages.
# Set via env var / .env; defaults to "on_demand" so crawls are fast and
# AI-free — run `python enrich.py` afterward to backfill summary/tags/vectors.
# Set NEXORA_ENRICH_MODE=eager for the old inline-enrichment behavior.
NEXORA_ENRICH_MODE = os.getenv("NEXORA_ENRICH_MODE", "on_demand").lower()

# ── Item Pipelines ────────────────────────────────────────────────────────────
# Order matters: lower numbers run first. 
# when user enters url , where does it first go  ? 
#This is what happens when a user enters a URL in the crawler:
# 1. The URL is sent to the Scrapy engine, which manages the crawling process(see file Crawler/nexora_crawler/spiders/nexora_spider.py).
# 2. The engine sends the URL to the spider(see the file Crawler /  ), which is responsible for extracting data from the web page.
 # The spider processes the URL and yields an item containing the extracted data.
# 3. The item is sent to the item pipelines, which are responsible for processing and storing the extracted data.
# 4. The item pipelines are defined in the settings.py file, and they are executed in the order specified by their priority values. Lower numbers run first.
# 5. Each pipeline can perform different tasks, such as cleaning the data, enriching it with additional information, or storing it in a database or file.
# 6. Once all the pipelines have processed the item, it is considered complete and can be stored or exported as needed.
# 7. where does , deduplication check happen? 
# This is what happens : 

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
# Base chain — always runs during a crawl (extraction → markdown → style →
# schema → metadata/DB save → parquet/exports).
ITEM_PIPELINES = {
    "nexora_crawler.pipelines.NexoraExtractionPipeline": 100,
    "nexora_crawler.pipelines.markdown_pipeline.MarkdownExtractionPipeline": 110,
    "nexora_crawler.pipelines.NexoraStylePipeline": 150,
    "nexora_crawler.pipelines.schema_enricher.UnifiedSchemaEnricher": 160,
    "nexora_crawler.pipelines.metadata_indexer.MetadataIndexerPipeline": 165,
    "nexora_crawler.pipelines.parquet_export.ParquetExportPipeline": 450,
    "nexora_crawler.pipelines.NexoraExportPipeline": 500,
    "nexora_crawler.pipelines.NexoraDatasetPipeline": 600,
}

# Phase 4B enrichment chain (AI summary/tags/vectors → chunking → vector index).
# Only runs inline during the crawl in "eager" mode. In "on_demand" mode it is
# excluded here and invoked later via the offline `enrich` command.
if NEXORA_ENRICH_MODE == "eager":
    ITEM_PIPELINES.update({
        'nexora_crawler.pipelines.ai_enrichment.AIEnrichmentPipeline': 250,            # Phase 4B
        'nexora_crawler.pipelines.chunking_pipeline.StructuralChunkingPipeline': 260,    # Phase 4B
        'nexora_crawler.pipelines.vector_index_pipeline.VectorIndexPipeline': 270,       # Phase 4B
    })

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
NEXORA_PLAYWRIGHT_ENABLED = os.getenv("NEXORA_PLAYWRIGHT_ENABLED", "true").lower() in ("1", "true", "yes")
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

    # Playwright-support middlewares. NOTE: ScrapyPlaywrightDownloadHandler is
    # a DOWNLOAD HANDLER (registered in DOWNLOAD_HANDLERS above) — it must NOT
    # also be listed here as a middleware, or a second handler instance (and
    # browser) gets created.
    DOWNLOADER_MIDDLEWARES.update({
        "nexora_crawler.middlewares.playwright_resource_blocker.PlaywrightResourceBlocker": 541,
        "nexora_crawler.middlewares.dynamic_detection.DynamicDetectionMiddleware": 542,
        "nexora_crawler.middlewares.playwright_cleanup.PlaywrightCleanupMiddleware": 550,
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

# ── Phase 4B: Vector Store Settings ──────────────────────────────────────────
# Local dev uses ChromaDB (no external service). Switch to "pgvector" when a
# Postgres+pgvector database is available (see NEXORA_DATABASE_URL below).
NEXORA_VECTOR_BACKEND = "chroma"   # chroma | pgvector | qdrant | cloudflare_vectorize
NEXORA_VECTOR_INDEX_ENABLED = True

# Data-store paths are anchored to THIS file's directory, not the process CWD.
# Entrypoints run from different directories (scrapy/api.py from
# nexora_crawler/, enrich.py from Crawler/), and CWD-relative paths made them
# silently operate on DIFFERENT databases (bug #15: enrich.py never saw crawl
# data). Relative values (defaults or from env/.env) are resolved against the
# package dir; absolute values pass through unchanged.
_NEXORA_PKG_DIR = Path(__file__).resolve().parent

def _anchored_path(value: str) -> str:
    p = Path(value)
    return str(p if p.is_absolute() else (_NEXORA_PKG_DIR / p).resolve())

NEXORA_CHROMA_PATH = _anchored_path(os.getenv("NEXORA_CHROMA_PATH", "data/chroma"))
# pgvector (production) — only used when NEXORA_VECTOR_BACKEND="pgvector"
NEXORA_DATABASE_URL = "postgresql://postgres:password@localhost:5432/nexora"
NEXORA_METADATA_DB = _anchored_path(os.getenv("NEXORA_METADATA_DB", "data/nexora_metadata.db"))
# vector_store/factory.py reads these via os.getenv (not this module) — export
# the resolved absolute paths so every consumer lands on the same files.
os.environ["NEXORA_CHROMA_PATH"] = NEXORA_CHROMA_PATH
os.environ["NEXORA_METADATA_DB"] = NEXORA_METADATA_DB


# ── Phase 4B: AI Enrichment Settings (Hugging Face via LiteLLM) ───────────────
# Single source of truth for embeddings = UnifiedEmbeddingEngine (LiteLLM).
# Provider is "huggingface" so the SAME LiteLLM abstraction also supports
# ollama / openai / anthropic later — only these settings change.
NEXORA_AI_ENABLED = True
NEXORA_AI_PROVIDER = "huggingface"  # huggingface | ollama | openai | anthropic

# Embedding model — 384-dim, fast/standard sentence-transformers model.
# NOTE: With NEXORA_AI_PROVIDER="huggingface", embeddings are routed to the
# HF router's legacy feature-extraction endpoint (NOT the OpenAI-compatible
# /v1/embeddings, which does not support sentence-transformers models).
# Switching models = change NEXORA_AI_EMBEDDING_MODEL + NEXORA_EMBEDDING_DIM
# (and rebuild the vector index, since the vector dimension changes).
NEXORA_AI_EMBEDDING_MODEL = "sentence-transformers/all-MiniLM-L6-v2"
NEXORA_EMBEDDING_DIM = 384

# Hosted free LLM for summary/tag generation (instruct-tuned, JSON-friendly)
NEXORA_AI_MODEL = "Qwen/Qwen2.5-7B-Instruct"   # or meta-llama/Llama-3.1-8B-Instruct

# Hugging Face serverless inference root (LiteLLM appends /<model_id>)
NEXORA_AI_BASE_URL = "https://router.huggingface.co/v1"
# Reads NEXORA_AI_API_KEY from .env, else falls back to the HF_TOKEN env var.
NEXORA_AI_API_KEY = os.getenv("NEXORA_AI_API_KEY", "") or os.getenv("HF_TOKEN", "")

NEXORA_AI_TIMEOUT = 60
NEXORA_AI_MAX_CONCURRENT = 2
NEXORA_EMBEDDINGS_ENABLED = True

# Circuit breaker: after this many CONSECUTIVE failed AI calls (LLM or
# embedding, tracked per subsystem) all further AI calls are skipped for the
# remainder of the run. Prevents a dead/quota-exhausted provider from turning
# an eager crawl into an hours-long timeout drain (observed 2026-07-20).
# Set to 0 to disable the breaker.
NEXORA_AI_FAILFAST_THRESHOLD = int(os.getenv("NEXORA_AI_FAILFAST_THRESHOLD", "3"))

# Fallback provider for embeddings when the primary hits the circuit breaker.
# Empty values mean "no fallback" — the engine returns None once the primary
# breaker opens. Set both provider and model (and base_url/api_key if needed)
# to restore AI functionality when the primary quota is exhausted.
# Example: NEXORA_AI_FALLBACK_PROVIDER=ollama  NEXORA_AI_FALLBACK_MODEL=nomic-embed-text
NEXORA_AI_FALLBACK_PROVIDER = os.getenv("NEXORA_AI_FALLBACK_PROVIDER", "")
NEXORA_AI_FALLBACK_MODEL = os.getenv("NEXORA_AI_FALLBACK_MODEL", "")
NEXORA_AI_FALLBACK_BASE_URL = os.getenv("NEXORA_AI_FALLBACK_BASE_URL", "")
NEXORA_AI_FALLBACK_API_KEY = os.getenv("NEXORA_AI_FALLBACK_API_KEY", "")

# -- Phase 4B: Chunking Settings ─────────────────────────────────────────────
NEXORA_CHUNK_SIZE = 512 # Target tokens per chunk 
NEXORA_CHUNK_OVERLAP = 128 #overlap tokens btwn chunks



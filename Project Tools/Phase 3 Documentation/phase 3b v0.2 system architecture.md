# Phase 3b v0.2 System Architecture

## Overview
Nexora Phase 3b v0.2 is a selective crawler + extractor system with a static-first fetch mode and conditional Playwright fallback. The system is organized into three main layers:

1. Crawler control and configuration
2. Dynamic request routing and rendering decision logic
3. Extraction / enrichment pipeline and output export

---

## File-Level Flow

```
settings.py
  ├─ DOWNLOADER_MIDDLEWARES
  │   ├─ ContentTypeFilterMiddleware
  │   ├─ PlaywrightResourceBlocker
  │   ├─ DynamicDetectionMiddleware
  │   ├─ ScrapyPlaywrightDownloadHandler
  │   └─ PlaywrightCleanupMiddleware
  ├─ ITEM_PIPELINES
  │   ├─ NexoraExtractionPipeline
  │   ├─ NexoraStylePipeline
  │   ├─ NexoraExportPipeline
  │   └─ NexoraDatasetPipeline
  └─ Playwright feature flags

spiders/nexora_spider.py
  ├─ start()
  │   ├─ explicit sitemap mode
  │   ├─ auto sitemap discovery mode
  │   └─ seed-based crawling mode
  ├─ parse_sitemap()
  └─ parse_page() → yields NexoraPageItem

items.py
  └─ NexoraPageItem schema shared by spider + pipelines

pipelines.py
  ├─ NexoraExtractionPipeline
  │   ├─ Extractor/Beautifulsoup_extractor.py
  │   ├─ Extractor/Trafilatura_extractor.py
  │   ├─ Extractor/parser.py
  │   ├─ Extractor/cleaner.py
  │   └─ Extractor/style_extractor.py
  ├─ NexoraStylePipeline
  ├─ NexoraExportPipeline
  └─ NexoraDatasetPipeline

sitemap_detector.py
  ├─ SitemapDetector.discover()
  └─ SitemapDetector.fetch_urls()

Extractor/sitemap_parser.py
  └─ sync sitemap discovery / parsing helpers
```

---

## Component Responsibilities

- `Crawler/nexora_crawler/settings.py`
  - Defines crawl politeness, request middleware ordering, pipeline order, and Playwright opt-in.

- `Crawler/nexora_crawler/spiders/nexora_spider.py`
  - Resolves user-provided strategy into crawl mode.
  - Dispatches seed URLs or sitemap requests.
  - Parses sitemap indexes and leaf sitemaps.
  - Creates crawl items with sitemap metadata and render tracking.

- `Crawler/nexora_crawler/middlewares/dynamic_detection.py`
  - Probes pages via HTTP first.
  - Detects anti-bot challenges, JS frameworks, SPA shells, bundle patterns, and text density.
  - Maintains site profile cache and TTL.
  - Annotates requests for Playwright when needed.

- `Crawler/nexora_crawler/middlewares/playwright_resource_blocker.py`
  - Adds Playwright route interception for JS-rendered pages.
  - Blocks images, fonts, analytics, stylesheet prefetches, and trackers.

- `Crawler/nexora_crawler/middlewares/playwright_cleanup.py`
  - Ensures pages are closed to prevent browser memory leaks.

- `Crawler/nexora_crawler/pipelines.py`
  - Enriches raw HTML into structured page intelligence.
  - Writes per-page JSON and CSV exports.
  - Appends summary rows into `output/master_dataset.csv`.

- `Extractor/` modules
  - Provide reusable HTML extraction, text cleaning, semantic parsing, and style detection.
  - Are consumed by the extraction pipeline, not directly by Scrapy.

---

## Architecture Notes

- The system is **selective**: static HTTP fetches are preferred, and Playwright is used only for pages that truly need JS rendering.
- Sitemap handling is supported in both `Crawler/nexora_crawler/sitemap_detector.py` (async) and `Extractor/sitemap_parser.py` (sync helper library).
- The PoC / prototype extractor scripts under `Extractor/` are separate from the production Scrapy pipeline and serve as reusable extraction libraries.
- Playwright is enabled by `NEXORA_PLAYWRIGHT_ENABLED=true` and is guarded behind middleware order to ensure the decision logic runs before the Playwright handler.

---

## Testing and Validation Layers

- `tests/test_phase3_playwright.py`
  - Focused unit and integration-style middleware tests.
  - Validates static vs JS routing decisions and stealth meta injection.

- `tests/test_phase3_integration.py`
  - Mocked integration scenarios for the HTTP→Playwright pipeline.

- `tests/test_sitemap_playwright_integration.py`
  - Sitemap parsing and discovery tests, including real-network sitemap validation.

- `tests/test_phase3_efficiency_matrix.py`
  - Real-site benchmarking for actual URL routing behavior.

- `tests/test_nexora_end_to_end.py`
  - Full end-to-end BBC crawl validation.

---

## Gaps and Recommendations

1. Add a dedicated `pytest` real-site integrity suite that exercises the actual live website decision path for the core backbone. This file should complement the existing benchmark scripts.
2. Keep the `playwright_resource_blocker.py` path and middleware behavior covered with unit tests that verify page methods injection.
3. Maintain separate tests for:
   - stable static baseline sites (`example.com`, `books.toscrape.com`)
   - live sitemap discovery (`bbc.com`)
   - JS-heavy or bot-detection pages (`bot.sannysoft.com`)

This architecture document is the Phase 3b v0.2 system blueprint for ongoing development and validation.

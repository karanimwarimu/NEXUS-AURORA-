# Nexora Codebase - End-to-End Architecture Blueprint

> Scope: Phase 4A / v4.1.0 comprehensive architecture report.
> Authoring mode: Senior Principal Systems Architect + Technical Instructor.

---

# PILLAR 1 - COMPREHENSIVE INFRASTRUCTURE MATRIX

## 1.1 Tool Inventory

| Tool / Lib | Explicit Architectural Job | Key Files |
|------------|---------------------------|-----------|
| **Scrapy** | Core crawling engine: scheduling, download, middleware, pipeline dispatch | Crawler/scrapy.cfg; Crawler/nexora_crawler/settings.py; spiders/nexora_spider.py |
| **Playwright** | Headless Chromium rendering for JS/SPA pages (static-first escape hatch) | settings.py (DOWNLOAD_HANDLERS, TWISTED_REACTOR, PLAYWRIGHT_*); middlewares/dynamic_detection.py |
| **httpx** | Async HTTP probing for static-vs-JS decision and sitemap discovery | middlewares/dynamic_detection.py; sitemap_detector.py |
| **BeautifulSoup4 + lxml** | HTML parsing for structural metadata, styles, multimodal, semantic graphs | Extractor/Beautifulsoup_extractor.py; Extractor/style_extractor.py; Extractor/multimodal_extractor.py; Extractor/parser.py |
| **Trafilatura** | Boilerplate removal; Reader Mode text extraction; Markdown source | Extractor/Trafilatura_extractor.py; pipelines/markdown_pipeline.py |
| **FastAPI** | REST API + interactive CLI host | Crawler/nexora_crawler/api.py |
| **Uvicorn** | ASGI runtime for FastAPI | api.py (uvicorn.run(...)) |
| **SQLite** | Relational metadata persistence (pages, crawl_jobs, site_profiles) | storage/local_sqlite.py; data/nexora_metadata.db; data/site_profiles.db |
| **PyArrow / Parquet** | Compressed columnar export for ML/analytics | pipelines/parquet_export.py; output/parquet/ |
| **pandas** | Buffer-to-DataFrame conversion before Parquet write | pipelines/parquet_export.py |
| **SimHash** | Near-duplicate content fingerprinting | Extractor/cleaner.py |
| **FastText** | ISO language detection (offline) | Extractor/cleaner.py; Models/lid.176.ftz |
| **Celery** | (Planned Phase 5) Background worker pool | Phase 7 spec only |
| **Redis** | (Planned Phase 5) Pub/sub for webhook bridge; Celery broker | Phase 7 spec only |
| **OpenTelemetry** | (Planned Phase 7) Distributed tracing | Phase 7 spec only |
| **LiteLLM** | (Planned Phase 7) LLM gateway for schema extraction and PII redaction | Phase 7 spec only |
## 1.2 Architecture Job of Each Tool

- **Scrapy** is the **orchestration substrate**. It owns request scheduling, downloader middleware chain, spider callbacks, and pipeline dispatch. Every concrete piece of the system plugs into Scrapy.
- **Playwright** is the **rendering escape hatch**. It is engaged only after DynamicDetectionMiddleware proves that static HTTP is insufficient. This design saves ~150-300 MB RAM per static page.
- **httpx** is the **probing instrument**. It performs lightweight HEAD/GET probes before Playwright is ever considered. It never downloads full JS bundles; it only inspects enough HTML to run the 8-signal decision tree.
- **BeautifulSoup4 + lxml** is the **parsing workhorse**. It turns raw HTML into structured Python dictionaries for every downstream consumer.
- **Trafilatura** is the **content distillation layer**. It removes nav, footer, ads, and boilerplate to produce LLM-ready Markdown with >50% token reduction.
- **FastAPI** is the **control-plane API**. It accepts crawl requests, manages job state in-process, and (in Phase 7) will host /v1/search, /v1/webhooks, and /v1/jobs.
- **SQLite** is the **source of truth** for metadata. It stores both crawl results (pages table) and operational state (crawl_jobs, site_profiles).
- **PyArrow + Parquet** is the **analytics sink**. It compresses tabular exports to <30% of equivalent JSON size using snappy/zstd/gzip/brotli.
- **SimHash** is the **deduplication sentinel**. It fingerprints clean_text so near-duplicate pages are skipped inside a single crawl.
- **FastText** is the **language classifier**. It runs locally; no API calls, no network dependency.

---

# PILLAR 2 - GLOBAL MACRO DATA-FLOW

A single URL progresses through four conceptual phases.

## Phase A: Ingestion Trigger

### Entry Points
- **FastAPI** (api.py): POST /crawl or interactive CLI prompts.
- **Scrapy CLI**: scrapy crawl nexora -a urls=... -a strategy=...

### ITO Contract
- **Input:** {url, strategy, max_pages}
- **Transformation:** Resolve strategy to {mode, max_depth, auto_sitemap, domain_lock}. Validate URL reachability via httpx.AsyncClient.head. Create job_id using timestamp + object id.
- **Output:** Launch CrawlerProcess inside loop.run_in_executor. Persist job metadata to in-memory _jobs[job_id].

[WHY THIS MATTERS] The run_in_executor boundary is critical. Scrapy is synchronous internally. Running it directly on the FastAPI event loop would block all other requests. Wrapping it in a thread pool keeps the API responsive.

## Phase B: Active Crawling & Fetching

### Entry Point
NexoraSpider.start() resolves the seed URLs and either auto-discovers a sitemap (whole-website strategy) or yields requests directly.

### Middleware Chain Order and Roles

| Priority | Component | Role |
|----------|-----------|------|
| 50 | NexoraUserAgentMiddleware | Rotate UA per request |
| 510 | ContentTypeFilterMiddleware | Reject non-HTML responses and blocked URL patterns |
| 541 | PlaywrightResourceBlocker | Block images/fonts/analytics inside Playwright pages |
| 542 | DynamicDetectionMiddleware | 8-signal static probe before Playwright |
| 543 | ScrapyPlaywrightDownloadHandler | Chromium rendering (only when middleware sets playwright=True) |
| 550 | PlaywrightCleanupMiddleware | Close page/session to prevent memory leak |
| 700 | ExponentialBackoffMiddleware | Retry with 1s/2s/4s/8s delays |

chunk1
chunk2
chunk3
chunk4
chunk5
chunk6
chunk7
chunk8
chunk9
chunk10
### ITO of DynamicDetectionMiddleware (Phase B Core)

- Input: url Request object
- Transformation:
  1. Playwright disabled -> return None (static HTTP).
  2. Check in-memory + SQLite profile cache for domain.
  3. Cache stale or missing -> async httpx probe.
  4. Run 8 signals: anti-bot, short-body+JS, text density, framework, SPA mount, bundle patterns, script ratio, error fallback.
  5. Needs JS detected -> inject playwright flag plus stealth script and networkidle wait.
- Output: Unchanged request (static) or Playwright-enriched request.

Note: Without profile cache, every first-time domain triggers a probe. 24-hour SQLite cache skips probing on repeat crawls. In-memory layer avoids DB round-trips.

## Phase C: The Pipeline Processing Chain

Entry point: item_pipeline dispatch from Scrapy after spider yields NexoraPageItem.

Order (priority 100 -> 600):

| Priority | Pipeline Class | Input State | Output State | Persists |
|----------|---------------|-------------|--------------|----------|
| 100 | NexoraExtractionPipeline | {html, url} | Adds title, description, keywords, meta_tags, headings, images, internal_links, word_count_raw, clean_text, word_count_clean, author, date, language, sitename, tags, fingerprint, language_iso, language_confidence, structured_schema, social_graphs, graph_relations, image_assets | No |
| 110 | MarkdownExtractionPipeline | Same + above | Adds markdown, markdown_word_count, extraction_method, token_reduction_pct, video_assets, total_images, total_videos, has_hero_image | No |
| 150 | NexoraStylePipeline | Same + above | Adds styles = {framework, theme, colors, fonts, layout_type, has_animations, linked_stylesheets} | No |
| 160 | UnifiedSchemaEnricher | Same + above | Ensures crawl_id, timestamp, domain, entities, style_analysis, quality_scores, website_type with guaranteed defaults | No |
| 165 | MetadataIndexerPipeline | Same + above | SQLite INSERT OR REPLACE | Yes - SQLite |
| 250 | (Phase 4B reserved) | -- | -- | -- |
| 450 | ParquetExportPipeline | Same + above | Appends serialized row to PyArrow buffer | Yes - Parquet |
| 500 | NexoraExportPipeline | Same + above | Per-page JSON + CSV files | Yes - Files |
| 600 | NexoraDatasetPipeline | Same + above | Appends summary row to master CSV | Yes - master CSV |

## Phase D: Storage Flushing

Outputs produced by the pipeline chain:

1. Markdown + metadata stay in-memory within the item dict and are passed to every later pipeline.
2. SQLite flush (MetadataIndexerPipeline) is immediate and idempotent per URL.
3. Parquet flush (ParquetExportPipeline) is batched (100 rows) and occurs on spider close or buffer full.
4. JSON/CSV per page is written immediately when the export pipeline runs.
5. Master dataset CSV is append-only and deduped by (url, fingerprint).

### ITO of ParquetExportPipeline

- Input: item: dict containing nested dicts/lists and heavy text fields (html, markdown, clean_text).
- Transformation: Serializes entities, style_analysis, quality_scores, image_assets, video_assets, ai_tags, ai_embedding into *_json string columns. Removes html, markdown, clean_text. Appends to in-memory _buffer.
- Output: _buffer -> pd.DataFrame -> pa.Table -> pq.write_table(..., compression=snappy) -> output/parquet/{spider}_{timestamp}_{counter:04d}.parquet.

### ITO of MetadataStore (SQLite)

- Input: item: dict
- Transformation: Maps dict fields to 27-column pages table schema. JSON-encodes nested fields. Truncates markdown_preview to 500 chars.
- Output: INSERT OR REPLACE INTO pages (...) VALUES (...)

[WHY THIS MATTERS] INSERT OR REPLACE guarantees idempotency: re-crawling the same URL never creates duplicate rows. The markdown_preview truncation keeps the SQLite row compact. The 27-column schema sacrifices some NoSQL flexibility for query speed.

---

# PILLAR 3 - COMPLETE CODEBASE DIRECTORY MAP

## 3.1 Repository Root

| Path | Responsibility | Talks To | Key Drivers |
|------|---------------|----------|-------------|
| REPOSITORY_STRUCTURE.md | Visual tree layout of all files | Everything | Human onboarding |
| README.md | Project vision, phases, strategy overview | Everything | Human onboarding |
| Project Tools/Phase 4 Documentation/ | Phase 4A spec, copy-paste impl guide | Nexora application | Implementation reference |
| Project Tools/Phase 7 Documentation/PHASE_7_PRODUCTION.md | Phase 7 spec | Nexora application | Future roadmap |
| NEXUS AURORA.code-workspace | VS Code workspace settings | IDE | Developer environment |
| Nexora application/ | All runtime source code | -- | -- |

## 3.2 Nexora application/ (Runtime Root)

| Path | Responsibility | Talks To | Key Drivers |
|------|---------------|----------|-------------|
| requirements.txt | Python dependencies | pip install | Deployment |
| main.py | Phase 1 CLI entry point | Extractor/* modules | Human runs: python main.py <url> |
| scrapy.cfg | Scrapy settings module pointer | Scrapy engine | Crawler startup |

## 3.3 Extractor/ (Phase 1-2 Extraction Layer)

| Path | Responsibility | Talks To | Key Drivers |
|------|---------------|----------|-------------|
| Web_fetcher.py | Synchronous HTML fetch via requests | Beautifulsoup_extractor, main.py | standalone fetcher |
| Beautifulsoup_extractor.py | Title, meta tags, headings, images, internal links, raw word count | main.py, pipelines | structural metadata |
| Trafilatura_extractor.py | Clean text, author, date, language, sitename, tags | main.py, pipelines | boilerplate removal |
| style_extractor.py | Colors, fonts, 9 CSS frameworks, theme, layout, animations | NexoraStylePipeline | style analysis |
| multimodal_extractor.py | Images (srcset highest-res, hero detection >=600px), videos (mp4 + YouTube/Vimeo embeds) | MarkdownExtractionPipeline | multimodal assets |
| parser.py | JSON-LD, microdata, RDFa; OpenGraph + Twitter Card graphs; canonical/prev/next relations | NexoraExtractionPipeline | semantic graphs |
| cleaner.py | SimHash fingerprinting; FastText language detection (lid.176.ftz) | NexoraExtractionPipeline | deduplication, language |
| Save_web_exctract.py | JSON + CSV persistence for single-page mode | Extractor/main.py | standalone output |
| main.py | Phase 1 full pipeline orchestrator (fetch -> BS4 -> Trafilatura -> save) | Web_fetcher, Beautifulsoup_extractor, Trafilatura_extractor, Save_web_exctract | Phase 1 CLI |
| extractor_prototype.py | Legacy monolithic prototype (superseded by modular Extractor/*) | None | Dead code candidate |
| sitemap_parser.py | Custom sitemap XML parsing (if present) | SitemapDetector or spider | May be dead code |
| SITEMAP_INTEGRATION_GUIDE.py | Markdown guide for sitemap integration | None | Documentation only |

## 3.4 Crawler/nexora_crawler/ (Phase 2-4A Production Engine)

### 3.4.1 Top-Level Module Files

| Path | Responsibility | Talks To | Key Drivers |
|------|---------------|----------|-------------|
| __init__.py | Package marker | -- | Module resolution |
| settings.py | Centralized Scrapy + pipeline configuration | All middleware, pipelines, spider | Engine behavior |
| items.py | NexoraPageItem definition (~40 fields, 7 categories) | Every pipeline, storage | Data contract |
| pipelines.py | Legacy consolidated pipeline file | -- | Phase 2 artifact |
| pipelines_phase3bfile.py | Phase 3B pipeline file | NexoraExportPipeline, NexoraDatasetPipeline | May be superseded |
| middlewares_oldversion(moved to folder).py | Old middleware definitions | -- | Dead code candidate |
| spider.py | Legacy spider definition | -- | Superseded by spiders/nexora_spider.py |

### 3.4.2 spiders/

| Path | Responsibility | Talks To | Key Drivers |
|------|---------------|----------|-------------|
| nexora_spider.py | Production spider with 4 strategies and safety guards | All middleware, pipelines | Crawl execution |

### 3.4.3 pipelines/

| Path | Responsibility | Talks To | Key Drivers |
|------|---------------|----------|-------------|
| __init__.py | NexoraExtractionPipeline, MarkdownExtractionPipeline, NexoraStylePipeline, UnifiedSchemaEnricher, NexoraExportPipeline, NexoraDatasetPipeline | items.py, Extractor/* | Pipeline chain |
| markdown_pipeline.py | MarkdownExtractionPipeline (priority 110) | MultimodalAssetExtractor | Markdown conversion |
| schema_enricher.py | UnifiedSchemaEnricher (priority 160) | items.py | Schema defaults |
| metadata_indexer.py | MetadataIndexerPipeline (priority 165) | MetadataStore | SQLite persistence |
| parquet_export.py | ParquetExportPipeline (priority 450) | pandas, PyArrow | Parquet output |

### 3.4.4 middlewares/

| Path | Responsibility | Talks To | Key Drivers |
|------|---------------|----------|-------------|
| __init__.py | NexoraUserAgentMiddleware, ContentTypeFilterMiddleware, NexoraSpiderMiddleware | settings.py, DynamicDetectionMiddleware | Request filtering |
| dynamic_detection.py | DynamicDetectionMiddleware (priority 542): 8-signal static-vs-JS decision engine | httpx, SQLite cache, Playwright | Static-first routing |
| exponential_backoff.py | ExponentialBackoffMiddleware (priority 700): retry logic | Settings | Resilience |
| playwright_resource_blocker.py | PlaywrightResourceBlocker (priority 541): block images/fonts/analytics in Playwright | Settings | RAM optimization |
| playwright_cleanup.py | PlaywrightCleanupMiddleware (priority 550): close page/session | Settings | Memory leak prevention |

### 3.4.5 storage/

| Path | Responsibility | Talks To | Key Drivers |
|------|---------------|----------|-------------|
| __init__.py | Package marker | -- | Module resolution |
| base.py | BaseMetadataStore + BaseVectorStore async ABCs | local_sqlite, future vector backends | Abstraction layer |
| models.py | NexoraUnifiedRecord dataclass | items.py, storage backends | Schema contract |
| local_sqlite.py | SQLite-backed pages, crawl_jobs, indexes | pipelines, dynamic_detection | Local persistence |

### 3.4.6 api/

| Path | Responsibility | Talks To | Key Drivers |
|------|---------------|----------|-------------|
| api.py | FastAPI app, lifespan events, interactive CLI, server mode | CrawlerProcess.run_in_executor | Control plane |

### 3.4.7 Other Top-Level Files

| Path | Responsibility | Talks To | Key Drivers |
|------|---------------|----------|-------------|
| scrapy.cfg | Scrapy settings module | Scrapy engine | Crawler startup |
| Models/lid.176.ftz | FastText language detection model (offline) | cleaner.py | Language detection |

## 3.5 tests/

| Path | Responsibility | Talks To | Key Drivers |
|------|---------------|----------|-------------|
| test_phase4a.py | 18 tests covering Phase 4A components | pipelines, storage, extractor | Regression safety |
| _helpers/factories.py | Test factories for NexoraPageItem, Request, Crawler, Spider | test_phase4a.py | Test infrastructure |

---

# PILLAR 4 - STATIC DATA SCHEMAS & ITEM DICTIONARIES

## 4.1 NexoraPageItem Data Contract

NexoraPageItem is a Scrapy Item with approximately 40 fields across 7 categories.

### Category 1: Scrapy-Level (8 fields)
url, status, html, depth, spider_name, crawled_at, playwright_used, screenshot_path

### Category 2: Style (1 field)
styles

### Category 3: Production Contract (7 fields)
fingerprint, language_iso, language_confidence, structured_schema, social_graphs, graph_relations, image_assets

### Category 4: Extraction (19 fields)
title, description, keywords, meta_tags, headings, images, internal_links, word_count_raw, clean_text, word_count_clean, author, date, language, sitename, tags, response_time_ms, markdown, markdown_word_count, extraction_method, token_reduction_pct

### Category 5: Pipeline (7 fields)
sitemap_lastmod, sitemap_priority, sitemap_changefreq, from_sitemap, saved_json, saved_csv, __skip

### Category 6: Phase 4A (11 fields)
video_assets, total_images, total_videos, has_hero_image, crawl_id, timestamp, domain, entities, price_change_delta, style_analysis, quality_scores, website_type

### Category 7: Phase 4B Reserved (5 fields)
ai_summary, ai_tags, ai_embedding, chunk_count, chunk_ids, has_embedding

## 4.2 Schema Enrichment Guarantees

UnifiedSchemaEnricher guarantees these fields exist with predictable defaults:

- **crawl_id**: Taken from spider.name or generated fallback.
- **timestamp**: Auto-generated ISO 8601 UTC string at the time of pipeline execution.
- **domain**: Parsed from the response URL via urlparse.
- **entities**: Default structure containing prices, currency, tickers, products, people, organizations (empty lists by default).
- **style_analysis**: Default structure containing dominant_colors, tech_stack, css_framework, theme, fonts (empty/unknown defaults).
- **quality_scores**: Default structure containing readability, duplication_score, text_density, crawl_quality (0.0 defaults).
- **website_type**: Heuristic classification result: e-commerce, blog, documentation, article, or unknown.

[WHY THIS MATTERS] These guaranteed defaults mean downstream consumers (Parquet export, SQLite storage, JSON API) never encounter KeyError on expected fields. The schema acts as a typed interface between pipeline stages even though Python dicts are dynamically typed.

## 4.3 Why Flattening Nested Data Is Necessary

Nested structures (entities, style_analysis, quality_scores, image_assets, video_assets, ai_tags, ai_embedding) are stored as JSON strings in Parquet and CSV because:

1. Parquet supports nested types, but the current PyArrow schema flattens them for simplicity and portability.
2. CSV has no native nesting; dict/list fields must be serialized to JSON strings for the CSV writer to handle them.
3. SQLite lacks robust nested query performance; storing nested data as JSON strings allows JSON1 extension queries if needed.
4. Future migration to PostgreSQL or API serialization is simpler when nested fields are already JSON-dumped.

The flattening happens in:
- **ParquetExportPipeline**: Serialized in _serialize_nested method before buffer append.
- **NexoraExportPipeline**: Flattened via json.dumps before CSV DictWriter.
- **MetadataStore.insert_page**: JSON-encoded via json.dumps before SQLite INSERT.

---

# PILLAR 5 - DEAD CODE / COLD HOOKS AUDIT

## 5.1 Dead Code Files

| File | Status | Reason |
|------|--------|--------|
| **Extractor/extractor_prototype.py** | DEAD CODE | Legacy monolithic Phase 1 prototype. Superseded by modular Extractor/* files (Web_fetcher.py, Beautifulsoup_extractor.py, Trafilatura_extractor.py, Save_web_exctract.py, main.py). Contains the same functions duplicated across multiple modules with no importers. |
| **Extractor/Save_web_exctract.py** | DEAD CODE | Standalone JSON/CSV saver for Phase 1 single-page mode. Replaced by NexoraExportPipeline (500) and NexoraDatasetPipeline (600) inside the Scrapy pipeline chain. No active imports in Crawler/ code. |
| **Extractor/Web_fetcher.py** | DEAD CODE | Standalone requests-based fetcher for Phase 1. Replaced by Scrapy HttpDownloadMiddleware. Only imported by legacy Extractor/main.py. |
| **Crawler/nexora_crawler/pipelines.py** | LEGACY | Consolidated pipeline file from Phase 2. Production pipelines now live in pipelines/__init__.py and pipelines/{markdown,schema,metadata,parquet}_pipeline.py. This file may still be referenced by old import paths. |
| **Crawler/nexora_crawler/pipelines_phase3bfile.py** | DEAD CODE | Phase 3B pipeline file. Export and dataset logic moved to pipelines/__init__.py. No importers found outside test references. |
| **Crawler/nexora_crawler/middlewares_oldversion(moved to folder).py** | DEAD CODE | Explicitly labeled as old version. Same classes moved to middlewares/__init__.py. |
| **Crawler/nexora_crawler/spider.py** | DEAD CODE | Legacy spider definition. Superseded by spiders/nexora_spider.py. Only referenced in tests/_helpers/factories.py via import string, not executed. |
| **Extractor/sitemap_parser.py** | DEAD CODE (conditional) | Custom sitemap XML parser. Superseded by SitemapDetector (sitemap_detector.py) which handles robots.txt discovery, common paths, and gzipped sitemaps. Only kept if SitemapDetector fails for exotic formats. |
| **Extractor/SITEMAP_INTEGRATION_GUIDE.py** | DOCUMENTATION | Markdown guide written as Python file. Not executed. Contains no importable code. |
| **Project Tools/** | DOCUMENTATION | Phase 4 and Phase 7 specs, review documents. Not executed. |

## 5.2 Cold Hooks (Unused Config / Placeholder References)

| Hook | Location | Observation |
|------|----------|-------------|
| **BaseVectorStore** | storage/base.py | Interface defined with 8 async methods (connect, close, add_chunks, search, search_by_text, delete_chunks, get_collection_stats, count). Phase 7 spec upgrades it to 11 methods (hybrid_search, list_all). Current implementations are missing (pgvector_store.py, chroma_store.py not present). The interface exists but no concrete backend is wired into the active Scrapy lifecycle. |
| **ai_embedding** | items.py | Field reserved for Phase 4B. Present in item schema but never populated by Phase 4A pipelines. Phase 4A pipelines explicitly skip it. |
| **ContentTypeFilterMiddleware** | settings.py -> settings.py | Listed in DOWNLOADER_MIDDLEWARES at 510 with import path ContentTypeFilterMiddleware. The class actually lives in middlewares/__init__.py. The import path in settings.py is registered via rom_crawler factory pattern, so it resolves without error, but the file-as-named does not exist. This is a latent maintenance risk. |
| **Celery / Redis** | Phase 7 spec only | Referenced extensively in PHASE_7_PRODUCTION.md as infrastructure for Celery workers, webhook delivery,JobTypeRegistry, and Redis pub/sub. No active imports, no docker-compose services, no running processes. |
| **OpenTelemetry / Prometheus** | Phase 7 spec only | Trace and metric hooks defined in spec only. No active instrumentation in Phase 4A code. |
| **NexoraUserAgentMiddleware** | middlewares/__init__.py | Functional but uses hardcoded static list of 4 User-Agent strings. Not yet connected to external UA rotation service. |
| **NexoraSpiderMiddleware** | middlewares/__init__.py | Registered in SPIDER_MIDDLEWARES (543) but process_spider_output yields items unchanged. It is a pass-through with no transformation. |

## 5.3 Cold Hooks in Tests

| Hook | Location | Observation |
|------|----------|-------------|
| **make_minimal_item** | tests/_helpers/factories.py | Calls make_full_item which populates all 40+ fields. The minimal factory is not actually minimal. |
| **make_crawler / make_settings** | tests/_helpers/factories.py | MagicMock-based helpers. Test for Phase 4A (test_phase4a.py) imports make_full_item and make_html_response but never uses make_crawler or make_settings. |

## 5.4 Summary

The codebase has clear phase separation but carries ~6 files of dead code from earlier iterations. The dead code does not affect runtime (Scrapy only loads active middlewares and pipelines from settings.py), but it increases maintenance surface and risks confusion.

Recommended action:
1. Remove Extractor/extractor_prototype.py after verifying no external references.
2. Remove Crawler/nexora_crawler/pipelines_phase3bfile.py if tests prove it is unused.
3. Remove Crawler/nexora_crawler/middlewares_oldversion(moved to folder).py (self-documenting).
4. Remove Crawler/nexora_crawler/spider.py after verifying factories.py does not load it dynamically.
5. Move Extractor/SITEMAP_INTEGRATION_GUIDE.py to Project Tools/ or delete it.
6. Confirm whether Extractor/Web_fetcher.py and Save_web_exctract.py are imported by anything outside their own module.

---

# PILOT AND CO-PILOT LEARNING CHALLENGE

## Diagnostic Quiz Questions

1. **Memory Leak Scenario:** DynamicDetectionMiddleware uses an in-memory list called _PROFILES_CACHE alongside a SQLite-backed cache. Spider close_spider flushes the in-memory cache to SQLite. What happens if the spider is killed by a signal or timeout before close_spider fires? Which unsaved profiles are lost, and what is the next symptom a user would observe on the next crawl of those domains?

2. **Concurrency Race Condition:** The ExponentialBackoffMiddleware uses request.meta[retry_count] and request.meta[retry_timestamps] to enforce max-retry caps. Scrapy hands requests to download handlers that may run process_request hooks concurrently. Is retry_count incremented under a lock? If not, what is the exact failure mode when two retry attempts for the same request interleave?

3. **Pipeline Order Dependency:** UnifiedSchemaEnricher runs at priority 160, AFTER NexoraStylePipeline (150) and MarkdownExtractionPipeline (110). It enriches style_analysis and quality_scores by reading from item[styles] and item[clean_text]. If someone accidentally changes NexoraStylePipeline to priority 170 (run AFTER the enricher), what specific KeyError or default-data issue occurs downstream, and why does ParquetExportPipeline silently mask it?

## Hands-On Debugging Blueprint Challenge

### Scenario: The Phantom Duplicate Record

You deploy Nexora to crawl a documentation site with approximately 1,200 pages. After the crawl completes, you query SQLite and discover 47 duplicate rows in the pages table for the same URL.

The duplicate records have:
- Same url value
- Same fingerprint value
- Slightly different crawled_at timestamps (within 30 seconds)
- Different markdown_preview content (1 record has full Markdown, the duplicate has truncated preview only)

### Task

Diagnose the root cause using the architecture you just studied. Your diagnosis must answer:

1. Which specific pipeline or middleware is bypassing the idempotency guarantee?
2. What exact sequence of events must have occurred for the duplicate to be inserted instead of replaced?
3. Why does the duplicate have a truncated markdown_preview while the first record has full content?
4. What is the minimal one-line fix to guarantee this path always resolves to INSERT OR REPLACE semantics?

### Hint

The answer involves the boundary between Scrapy duplicate filter, the spider from_sitemap flag, and the MetadataIndexerPipeline decision logic. Trace the item through phases B and D.

---
*End of Architecture Blueprint Report*

# 🏗️ Nexora Codebase — End-to-End Architecture Blueprint

---

## Pillar 1 — Comprehensive Infrastructure Matrix

| Tool | Architectural Job | Files | Why Selected Over Alternatives |
|------|-------------------|-------|------------------------------|
| **Scrapy** | Orchestration substrate — request scheduling, middleware chain, pipeline dispatch | `Crawler/scrapy.cfg`, `settings.py`, `spiders/nexora_spider.py` | Mature async crawler with robust retry, dupefilter, and extensibility. Beats BeautifulSoup-only (no queueing) or requests-html (deprecated). |
| **Playwright** | Render escape hatch for JS/SPA sites | `settings.py` (lines 162–194), `middlewares/dynamic_detection.py`, `middlewares/playwright_cleanup.py` | Chromium-based; captures dynamic content after hydration. Selenium is heavier, puppeteer is Node-only. |
| **httpx** | Lightweight static probe before Playwright | `middlewares/dynamic_detection.py`, `sitemap_detector.py` | Async-first, no browser overhead for static detection. requests is sync-only (blocks event loop). |
| **BeautifulSoup4 + lxml** | HTML parsing workhorse | `Extractor/Beautifulsoup_extractor.py`, `style_extractor.py`, `multimodal_extractor.py`, `parser.py` | lxml is fast C-parser; BS4 is battle-tested API. lxml alone lacks BS4's CSS selector convenience. |
| **Trafilatura** | Reader-mode text extraction → Markdown | `Extractor/Trafilatura_extractor.py`, `pipelines/markdown_pipeline.py` | Specialized for boilerplate removal; 50%+ token reduction. jusText/sgml are less maintained. |
| **FastAPI** | Control-plane API + interactive CLI wrapper | `api.py`, `pipelines/__init__.py` (sys.path setup) | Pydantic validation built-in, async-native, OpenAPI auto-docs. Flask is sync, Starlette lacks Pydantic. |
| **SQLite** | Relational metadata store | `storage/local_sqlite.py`, `storage/base.py` | Zero-config, ACID, file-based. PostgreSQL would require server setup. Redis is key-value (no joins). |
| **PyArrow/Parquet** | Compressed columnar export | `pipelines/parquet_export.py` | 10–30% of JSON size, predicate pushdown, pandas-native. CSV is larger; HDF5 is NumPy-centric. |
| **SimHash** | Near-duplicate fingerprinting | `Extractor/cleaner.py` | Locality-sensitive hashing; detects similar (not exact) duplicates. Hashlib would only catch exact duplicates. |
| **FastText** | Offline language detection | `Extractor/cleaner.py`, `Models/lid.176.ftz` | Fast local inference; 176-language coverage. langdetect requires network; google-cloud-translate costs. |

---

## Pillar 2 — Global Macro Data-Flow

### Phase A: Ingestion Trigger

```
┌─────────────────────────────────────────────────────────────────────────┐
│ FastAPI Endpoint / CLI                                                  │
│ ┌──────────────────────┴────────────────────────────────────────────────┐
│ │ POST /crawl (async) OR python -m nexora_crawler.api                 │
│ │   - Validates URL via httpx head request                             │
│ │   - Resolves strategy: single-page | linked-pages | whole-website    │
│ │   - Creates job_id = f"job_{timestamp}_{object_id:x}"               │
│ └──────────────────────────────────────────────────────────────────────┘
│                            ↓
│                    CrawlerProcess() (sync engine)
│                    loop.run_in_executor()
│                    ← [WHY THIS MATTERS] Prevents blocking the FastAPI
│                    event loop. Without it, the entire server stalls
│                    during crawl.
└─────────────────────────────────────────────────────────────────────────┘
```

### Phase B: Message Queueing & Task Delegation

> **Not yet implemented** — Currently uses in-memory `_jobs` dict. Phase 5 (Celery + Redis) will replace this.

### Phase C: Active Crawling & Fetching

```
┌─────────────────────────────────────────────────────────────────────────┐
│ Request Flow (Downloader Middlewares)                                   │
│ Priority Order:                                                         │
│   50   NexoraUserAgentMiddleware      → Random UA rotation              │
│  100   ContentTypeFilterMiddleware    → Reject /admin/, /login, .pdf, │
│                                         .css                              │
│  541   PlaywrightResourceBlocker      → Inject route interceptors       │
│  542   DynamicDetectionMiddleware     → probe → decide: HTTP or         │
│                                         Playwright                        │
│  550   PlaywrightCleanupMiddleware    → Close pages on response/        │
│                                         exception                         │
│  700   ExponentialBackoffMiddleware   → Retry 429/503 with 1→2→4→8s     │
│                                         delay                             │
│                                                                         │
│ DynamicDetection Decision Tree:                                         │
│   ┌── Anti-bot indicators? → Playwright                                 │
│   ├── Body <200 chars + script_ratio>15%? → Playwright                  │
│   ├── Text density <5% + body<5000? → Playwright                        │
│   └── JS framework signature? → Playwright (unless Next.js SSR guard    │
│       passes)                                                             │
└─────────────────────────────────────────────────────────────────────────┘
```

### Phase D: Pipeline Processing Chain

```
┌─────────────────────────────────────────────────────────────────────────┐
│                INPUT ITEM (from spider)                                 │
│  {url, status, html, depth, spider_name, crawled_at, playwright_used} │
│                          ↓ priority 100                                 │
│  ┌──────────────────────────────────────────────────────────────────┐   │
│  │ NexoraExtractionPipeline                                         │   │
│  │   - extract_with_bs4() → title, meta, headings, images, links   │   │
│  │   - extract_with_trafilatura() → clean_text, author, date,       │   │
│  │     language                                                        │   │
│  │   - calculate_fingerprint() → SimHash signature                  │   │
│  │   - detect_language_iso() → FastText classification                │   │
│  │   - extract_structured_data() → JSON-LD, Microdata, RDFa          │   │
│  └──────────────────────────────────────────────────────────────────┘   │
│                          ↓ priority 110                                 │
│  ┌──────────────────────────────────────────────────────────────────┐   │
│  │ MarkdownExtractionPipeline                                       │   │
│  │   - trafilatura.extract(output_format="markdown")                │   │
│  │   - MultimodalAssetExtractor.extract() → images, videos,         │   │
│  │     hero check                                                      │   │
│  │   - token_reduction_pct = (1 - clean/raw) * 100                    │   │
│  └──────────────────────────────────────────────────────────────────┘   │
│                          ↓ priority 150                                 │
│  ┌──────────────────────────────────────────────────────────────────┐   │
│  │ NexoraStylePipeline                                              │   │
│  │   - extract_styles() → framework, theme, colors, fonts, layout   │   │
│  └──────────────────────────────────────────────────────────────────┘   │
│                          ↓ priority 160                                 │
│  ┌──────────────────────────────────────────────────────────────────┐   │
│  │ UnifiedSchemaEnricher                                              │   │
│  │   - Sets defaults: entities{}, style_analysis{},                 │   │
│  │     quality_scores{}                                                │   │
│  │   - _classify_website_type() → e-commerce | blog | docs |        │   │
│  │     article | unknown                                               │   │
│  │   - Ensures crawl_id, timestamp, domain                            │   │
│  └──────────────────────────────────────────────────────────────────┘   │
│                          ↓ priority 165                                 │
│  ┌──────────────────────────────────────────────────────────────────┐   │
│  │ MetadataIndexerPipeline                                          │   │
│  │   - MetadataStore.insert_page() → SQLite pages table               │   │
│  │   - 500-char markdown_preview only (full markdown in JSON)         │   │
│  └──────────────────────────────────────────────────────────────────┘   │
│                          ↓ priority 450                                 │
│  ┌──────────────────────────────────────────────────────────────────┐   │
│  │ ParquetExportPipeline                                            │   │
│  │   - Buffer 100 rows → DataFrame → PyArrow Table                  │   │
│  │   - JSON-stringify nested fields (entities, styles, etc.)        │   │
│  │   - REMOVE heavy fields: html, markdown, clean_text              │   │
│  │   - Write: spider_TIMESTAMP_COUNTER.parquet                      │   │
│  └──────────────────────────────────────────────────────────────────┘   │
│                          ↓ priority 500                                 │
│  ┌──────────────────────────────────────────────────────────────────┐   │
│  │ NexoraExportPipeline                                             │   │
│  │   - JSON: domain__path__TIMESTAMP.json                           │   │
│  │   - CSV: same filenames, nested fields JSON-stringified            │   │
│  └──────────────────────────────────────────────────────────────────┘   │
│                          ↓ priority 600                                 │
│  ┌──────────────────────────────────────────────────────────────────┐   │
│  │ NexoraDatasetPipeline                                            │   │
│  │   - Append to master_dataset.csv (only scalar columns)             │   │
│  │   - Deduplication by (url, fingerprint)                          │   │
│  └──────────────────────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────────────────┘
```

### Phase E: Storage Flushing

```
┌─────────────────────────────────────────────────────────────────────────┐
│ Storage Destinations                                                    │
│                                                                         │
│ output/pages/                                                           │
│   ├── example_com__about__20260630T143022.json   ← Full fidelity        │
│   └── example_com__about__20260630T143022.csv   ← Flattened, nested     │
│                                                   JSON-stringified      │
│                                                                         │
│ output/parquet/                                                         │
│   ├── nexora_20260630_190925_0000.parquet      ← 100-row batches,     │
│   └── ...                                        snappy                 │
│                                                                         │
│ data/nexora_metadata.db                                                  │
│   ├── pages table (URL-indexed, searchable)                             │
│   └── crawl_jobs table (job state tracking)                             │
└─────────────────────────────────────────────────────────────────────────┘
```

---

## Pillar 3 — Complete Codebase Directory Map

```
Nexora application/
├── Crawler/
│   ├── scrapy.cfg                              ← Scrapy project entry
│   └── nexora_crawler/
│       ├── settings.py                         ← Central config (211 lines)
│       ├── api.py                              ← FastAPI + CLI runner (445 lines)
│       ├── items.py                            ← NexoraPageItem schema (106 fields)
│       ├── sitemap_detector.py                 ← Async sitemap discovery
│       ├── middlewares/
│       │   ├── __init__.py                     ← UA, content-type, spider middleware
│       │   ├── dynamic_detection.py            ← HTTP vs Playwright decision (598 lines)
│       │   ├── playwright_resource_blocker.py    ← Block images/fonts/analytics (173 lines)
│       │   ├── playwright_cleanup.py             ← Prevent page leaks (52 lines)
│       │   └── exponential_backoff.py            ← Retry with 1→2→4→8s delay (106 lines)
│       └── pipelines/
│           ├── __init__.py                     ← Core pipelines 100/150/500/600
│           ├── parquet_export.py               ← Columnar export (priority 450)
│           ├── metadata_indexer.py             ← SQLite persistence (priority 165)
│           ├── markdown_pipeline.py            ← Markdown + multimodal (priority 110)
│           ├── schema_enricher.py              ← Unified schema defaults (priority 160)
│           └── pipelines_phase3bfile.py        ← Legacy (duplicate of __init__.py)
│       └── storage/
│           ├── __init__.py                     ← Package init
│           ├── base.py                         ← Abstract interfaces (ABC)
│           ├── local_sqlite.py                 ← SQLite implementation
│           └── models.py                       ← NexoraUnifiedRecord dataclass
├── Extractor/
│   ├── main.py                                 ← Phase 1 standalone runner
│   ├── Web_fetcher.py                          ← requests-based fetch
│   ├── Beautifulsoup_extractor.py              ← Structural metadata
│   ├── Trafilatura_extractor.py                ← Clean text extraction
│   ├── multimodal_extractor.py                 ← Image/video asset extraction
│   ├── style_extractor.py                      ← CSS/framework/theme analysis
│   ├── parser.py                               ← JSON-LD, OG, canonical, assets
│   ├── cleaner.py                              ← SimHash + FastText detection
│   ├── Save_web_exctract.py                    ← JSON/CSV file writers
│   ├── sitemap_parser.py                       ← Sitemap XML parsing utilities
│   └── SITEMAP_INTEGRATION_GUIDE.py           ← Documentation
├── Models/
│   └── lid.176.ftz                             ← FastText language model
├── output/
│   ├── pages/                                    ← Per-page JSON + CSV
│   └── parquet/                                  ← Columnar exports
├── tests/                                        ← pytest suite
└── pytest.ini                                    ← Test configuration
```

---

## Pillar 4 — Static Data Schemas & Item Dictionary

### ITO: `NexoraPageItem` (items.py)

```
┌─────────────────────────────────────────────────────────────────────────┐
│ INPUT (Spider yields):                                                  │
│ {url, status, html, depth, spider_name, crawled_at, playwright_used}  │
└─────────────────────────────────────────────────────────────────────────┘
                              ↓ process_item()
┌─────────────────────────────────────────────────────────────────────────┐
│ AFTER UnifiedSchemaEnricher (priority 160):                             │
│ {                                                                       │
│   url, title, domain, timestamp, crawl_id,                              │
│   markdown (trafilatura), clean_text (fallback),                        │
│   entities: {prices:[], currency:"", tickers:[], products:[],         │
│              people:[], org:[]},                                        │
│   style_analysis: {dominant_colors:[], tech_stack:[],                  │
│                    css_framework:"", ...},                              │
│   quality_scores: {readability, duplication_score, text_density,        │
│                    crawl_quality},                                      │
│   image_assets: [{src, alt, width, height, is_hero}, ...],             │
│   video_assets: [{src, type, platform}, ...],                          │
│   website_type: "article | blog | e-commerce | docs | unknown",         │
│   token_reduction_pct: 72.5, markdown_word_count: 2500,             │
│   __skip: False,                                                        │
│ }                                                                       │
└─────────────────────────────────────────────────────────────────────────┘
                              ↓ Parquet export
┌─────────────────────────────────────────────────────────────────────────┐
│ PARQUET ROW (flattened, no heavy text):                                 │
│ {                                                                       │
│   url, title, domain, timestamp, crawl_id,                              │
│   entities_json, style_analysis_json, quality_scores_json,              │
│   image_assets_json, video_assets_json,                                 │
│   total_images, total_videos, has_hero_image,                           │
│   markdown_word_count, token_reduction_pct, website_type,               │
│   html, markdown, clean_text REMOVED,                                   │
│ }                                                                       │
└─────────────────────────────────────────────────────────────────────────┘
```

### Why Flatten for Parquet?

- Columnar formats require flat schemas.
- JSON strings maintain nested structure while allowing queries.
- Heavy text (`html`, `markdown`) removed because:
  - **Parquet** is for analytics — not full-content retrieval.
  - JSON/CSV already store full content.

---


┌──────────────────────────────────────┐
                     │       FastAPI POST /crawl            │
                     │  (Validates URL, Generates job_id)   │
                     └──────────────────┬───────────────────┘
                                        │
                                        │ (asyncio.create_task)
                                        ▼
                     ┌──────────────────────────────────────┐
                     │       loop.run_in_executor()         │
                     │ ──► [Frees FastAPI Event Loop]       │
                     └──────────────────┬───────────────────┘
                                        │
                                        │ (Spawns Thread)
                                        ▼
                     ┌──────────────────────────────────────┐
                     │      CrawlerProcess(settings)        │
                     │  (Reads settings.py configurations)  │
                     └──────────────────┬───────────────────┘
                                        │
                                        │ (Initializes Engine Engine)
                                        ▼
   ┌─────────────────────────────────────────────────────────────────────────┐
   │                       SCRAPY DOWNLOADER MIDDLEWARES                     │
   │  [50: Rotate UA] ──► [100: Filter Content] ──► [542: Dynamic Detection] │
   └────────────────────────────────────┬────────────────────────────────────┘
                                        │
                                        │ (Decide Fetch Strategy)
                                        ▼
                   ┌───────────────────────────────────────┐
                   │    If JS Detected?                    │
                   │    ├── YES ──► Launch Playwright      │
                   │    └── NO  ──► Standard HTTP Fetch    │
                   └────────────────────┬──────────────────┘
                                        │
                                        │ (Yields Raw HTML Data)
                                        ▼
                     ┌──────────────────────────────────────┐
                     │          Spider.parse()              │
                     │   (Yields NexoraPageItem Object)     │
                     └──────────────────┬───────────────────┘
                                        │
                                        │ (Passes to Processing Line)
                                        ▼
   ┌─────────────────────────────────────────────────────────────────────────┐
   │                         SCRAPY ITEM PIPELINES                           │
   │  [100: BS4/Trafilatura Extraction] ──► [110: Clean Markdown Pipeline]   │
   │                                              │                          │
   │  [165: Log SQLite Metadata]        ◄── [160: Unified Schema Enricher]   │
   │                                              │                          │
   │  [450: Compress Columnar Parquet]  ──► [600: Master CSV Append]         │
   └────────────────────────────────────┬────────────────────────────────────┘
                                        │
                                        │ (All Queues Cleared)
                                        ▼
                     ┌──────────────────────────────────────┐
                     │         Job Marked "Completed"       │
                     │  (Status pollable at GET /crawl/)    │



---


## Pillar 5 — Dead Code / Cold Hooks

| File | Status | Reason |
|------|--------|--------|
| `pipelines_phase3bfile.py` | ❌ **Dead Code** | Duplicate of `pipelines/__init__.py` — same pipeline classes. Not imported in `settings.py`. |
| `Extractor/main.py` | ⚠️ **Cold Hook** | Standalone runner exists but `api.py` is primary entry point. Still usable for Phase 1-only extraction. |
| `Extractor/SITEMAP_INTEGRATION_GUIDE.py` | ⚠️ **Cold Hook** | Documentation file, no code executed. |
| `Extractor/extractor_prototype.py` | ⚠️ **Cold Hook** | Prototype file — not imported anywhere. |
| `Extractor/sitemap_parser.py` | ⚠️ **Cold Hook** | Functions overlap with `sitemap_detector.py` but spider uses `sitemap_detector.py`. |

---

# 🎓 Pilot & Co-Pilot Learning Challenges

## Quiz Questions (Hidden Assumptions)

### Q1: Memory Management Leak

The `DynamicDetectionMiddleware` creates an `httpx.AsyncClient` in `spider_opened`. Describe what happens to the client if `_run_crawl` is called inside `loop.run_in_executor()` from FastAPI, and why the `spider_closed` cleanup uses `asyncio.ensure_future()` instead of `asyncio.create_task()`.

### Q2: Async Execution Safety

`MetadataIndexerPipeline.insert_page()` opens a NEW SQLite connection inside `process_item()`. If 100 concurrent pages are processed (due to `CONCURRENT_REQUESTS=4` × async pipeline), how does SQLite handle the concurrent writes, and what is the risk of database locks?

### Q3: Race Condition in Deduplication

In `NexoraDatasetPipeline`, the `_seen_keys` set is populated inside `process_item()`. If the same spider is run concurrently in different threads/processes, what happens to deduplication? Is it per-spider-run or global?

---

## Debugging Blueprint Challenge

**Scenario:** You run a crawl with `strategy=whole-website`. The job reports "completed" but only 3 pages are saved. Checking logs shows:

```
[DD] Static OK: https://example.com/page1
[DD] Static OK: https://example.com/page2
[Parquet] Flush failed: disk I/O error (path not found)
```

**Question:** Diagnose the root cause and propose a fix using insights from this architecture report. Which component is at fault, and what defensive pattern could prevent this class of failures?

# Repository Structure

```text
.
├── .gitignore
├── LICENSE
├── README.md
├── REPOSITORY_STRUCTURE.md
├── Nexora application/
│   ├── requirements.txt
│   ├── phase1+2 setup.md
│   ├── phase2.6 implementation.md
│   ├── PHASE2.6_TESTING_AND_ARCHITECTURE.md
│   ├── V2.6_DELIVERABLES.md
│   ├── test_sitemap.py
│   ├── Crawler/
│   │   ├── __init__.py
│   │   ├── scrapy.cfg
│   │   ├── TODO.md
│   │   ├── TODO_REVIEW_PLAN.md
│   │   ├── phase2_crawler.md
│   │   ├── middlewares_oldversion(moved to folder).py
│   │   └── nexora_crawler/
│   │       ├── .env
│   │       ├── api.py
│   │       ├── items.py                          ← Phase 4A: 19 new fields (markdown, multimodal, unified schema)
│   │       ├── pipelines_phase3bfile.py
│   │       ├── settings.py                       ← Phase 4A: updated pipeline chain (100→600)
│   │       ├── sitemap_detector.py
│   │       ├── spiders/
│   │       │   └── nexora_spider.py
│   │       ├── middlewares/
│   │       │   ├── __init__.py
│   │       │   ├── dynamic_detection.py           ← Phase 3 Core: JS vs Static detection
│   │       │   ├── exponential_backoff.py
│   │       │   ├── playwright_cleanup.py
│   │       │   └── playwright_resource_blocker.py
│   │       ├── pipelines/                         ← Phase 4A: Modular pipeline files
│   │       │   ├── __init__.py                    ← Phase 1-3: Extraction, Style, Export, Dataset pipelines
│   │       │   ├── markdown_pipeline.py           ← Phase 4A: HTML → clean Markdown + multimodal
│   │       │   ├── schema_enricher.py             ← Phase 4A: Unified schema defaults + classification
│   │       │   ├── metadata_indexer.py            ← Phase 4A: SQLite metadata persistence
│   │       │   └── parquet_export.py              ← Phase 4A: Compressed Parquet export
│   │       └── storage/                           ← Phase 4A: Storage abstraction layer
│   │           ├── __init__.py
│   │           ├── base.py                        ← Abstract base classes (MetadataStore, VectorStore)
│   │           ├── local_sqlite.py                ← SQLite MetadataStore implementation
│   │           └── models.py                      ← Unified schema dataclass (NexoraRecord, NexoraChunk)
│   ├── Extractor/
│   │   ├── Beautifulsoup_extractor.py
│   │   ├── Trafilatura_extractor.py
│   │   ├── Web_fetcher.py
│   │   ├── cleaner.py
│   │   ├── extractor_prototype.py
│   │   ├── main.py
│   │   ├── multimodal_extractor.py               ← Phase 4A: Image/video asset extraction
│   │   ├── parser.py
│   │   ├── Save_web_exctract.py
│   │   ├── SITEMAP_INTEGRATION_GUIDE.py
│   │   ├── sitemap_parser.py
│   │   └── style_extractor.py
│   ├── Models/
│   │   └── lid.176.ftz                           ← Language detection model
│   ├── output/
│   │   ├── master_dataset.csv
│   │   ├── release_notes_v3b_v0.4.0.md           ← Phase 3 release notes
│   │   ├── release_notes_v4.1.0.md               ← Phase 4A release notes (NEW)
│   │   ├── pages/                                ← Crawled page exports (CSV+JSON)
│   │   ├── parquet/                              ← Phase 4A: Compressed Parquet exports (NEW)
│   │   └── audit/                                ← Benchmark reports & test results
│   │       ├── phase3_3_test_summary.md
│   │       ├── phase3_50site_benchmark.md
│   │       ├── phase3_50site_benchmark.json
│   │       ├── phase3_50site_benchmarktest2.md
│   │       ├── phase3_benchmark_analysis_and_roadmap.md
│   │       ├── phase3_live_test_results.json
│   │       ├── phase3_unit_audit.json
│   │       ├── phase3_unit_audit.md
│   │       ├── phase3.2_successes_and_focus.md
│   │       ├── phase3.3_fixes.md
│   │       ├── phase3.4_fixes_applied.md
│   │       └── phase4a_test1_report.md           ← Phase 4A test audit report (NEW)
│   └── tests/
│       ├── conftest.py
│       ├── NEXORA_PHASE3_TEST_REPORT(test 1&2).md
│       ├── PHASE3_1_CODEBASE_AUDIT.md
│       ├── PHASE3_2_TEST_PLAN.md
│       ├── phase3.4 test2 fixes.md
│       ├── real_site_benchmark_phase3.py         ← 50-site benchmark runner
│       ├── real_site_test_phase3.py              ← Quick live-site validation
│       ├── test_phase3_component.py
│       ├── test_phase3_integration.py
│       ├── test_phase3_playwright.py
│       ├── test_phase3_playwright_testv1.py
│       ├── test_phase3_unit_and_vulns.py
│       ├── test_phase4a.py                       ← Phase 4A: 18-test suite (NEW)
│       └── _fixtures/
│           └── html/
│               └── article_with_multimodal.html  ← Phase 4A test fixture (NEW)
├── data/
│   ├── test_profiles.db                          ← SQLite site profile cache
│   └── nexora_metadata.db                        ← Phase 4A: SQLite metadata store (auto-created)
├── nexora venv/                                  ← Python virtual environment
└── Project Tools/
    ├── FIRECRAWL_ANALYSIS_AND_ROADMAP 2.6 upwards implementation.pdf
    ├── competitive_analysis_nexora_vs_industry.md
    ├── final project look (target).txt
    ├── nexora_crawler_industrial_readiness_assessment-phase 2 upgrade.md
    ├── nexora_issues_log-phase2.2.md
    ├── phase 1 and 2 full skeleton.md
    ├── phase 3 technical implementation.md
    ├── phase2.6 implementation.docx
    ├── web_scraping_ai_workflow.md
    ├── web_scraping_ai_website_intelligence_chat (1).pdf
    ├── web_scraping_ai_website_intelligence_chat.pdf
    ├── other scarppers acheivements/
    │   ├── firecrawl.md
    │   └── diorwave/
    │       └── diorwave-firecrawl.md
    └── PHASE IMPLEMENTATION DOCUMENTATION/
        ├── PHASE_3_PLAYWRIGHT_STEALTH.md
        ├── phase3b_data_and_llm_storage.md
        ├── PHASE_4_AI_ANALYTICS.md
        ├── PHASE_5_DISTRIBUTED_SCALING.md
        └── PHASE_6_TAURI_DESKTOP.md
```

## Key Components

### Phase 3 — Dynamic Detection Middleware
- **`Crawler/nexora_crawler/middlewares/dynamic_detection.py`** — Core decision engine that routes requests to either static HTTP or Playwright JS rendering. Uses 8 signals: framework markers, script ratio, text density, body length, anti-bot patterns, SPA mount points, bundle patterns, and noscript tags.
- **`Crawler/nexora_crawler/middlewares/exponential_backoff.py`** — Exponential backoff retry middleware for 429/503/408 responses.
- **`Crawler/nexora_crawler/middlewares/playwright_resource_blocker.py`** — Blocks images/fonts/analytics in Playwright pages to reduce bandwidth.
- **`tests/real_site_benchmark_phase3.py`** — 50-site benchmark across 8 categories (static, server, react, vue, angular, svelte, antibot, spa)
- **`tests/real_site_test_phase3.py`** — Quick validation script (4 test groups, ~10 requests)
- **`output/audit/phase3.4_fixes_applied.md`** — Latest round of fixes (SPA mount detection, bundle patterns, anti-bot on 200)
- **`output/audit/phase3_benchmark_analysis_and_roadmap.md`** — Full analysis with current results, failure root causes, strengths, and future roadmap

### Phase 4A — Storage & Multi-Format Ingestion Engine ✅ (v4.1.0)
- **`Crawler/nexora_crawler/pipelines/markdown_pipeline.py`** — Converts raw HTML to clean, LLM-ready Markdown via Trafilatura (priority 110). Also performs multimodal asset extraction (images, videos) inline.
- **`Extractor/multimodal_extractor.py`** — Extracts image/video references from HTML with structured metadata (src, alt, dimensions, hero detection, platform identification for embeds).
- **`Crawler/nexora_crawler/pipelines/schema_enricher.py`** — UnifiedSchemaEnricher (priority 160) that enforces the NexoraRecord schema with defaults for all fields. Classifies website_type (e-commerce, blog, docs, article, unknown).
- **`Crawler/nexora_crawler/pipelines/metadata_indexer.py`** — MetadataIndexerPipeline (priority 165) that persists each item to SQLite MetadataStore.
- **`Crawler/nexora_crawler/pipelines/parquet_export.py`** — ParquetExportPipeline (priority 450) that buffers rows and flushes compressed Apache Parquet files (snappy, zstd, gzip, brotli).
- **`Crawler/nexora_crawler/storage/base.py`** — Abstract base classes for MetadataStore and VectorStore backends.
- **`Crawler/nexora_crawler/storage/models.py`** — Canonical unified schema dataclass (NexoraRecord, NexoraChunk) with typed sub-classes (EntityExtraction, QualityScores, StyleAnalysis).
- **`Crawler/nexora_crawler/storage/local_sqlite.py`** — SQLite-backed MetadataStore with pages table, crawl_jobs table, and indexes on domain, crawl_id, website_type, timestamp, language.
- **`data/nexora_metadata.db`** — Auto-created SQLite database for metadata persistence.
- **`tests/test_phase4a.py`** — 18-test suite covering all 12 Phase 4A test cases (94.4% initial pass rate, 100% after fix).
- **`output/audit/phase4a_test1_report.md`** — Audit report documenting test results and fix plan.

### Phase 4B (Next) — AI Enrichment & RAG Pipeline
- **`Project Tools/PHASE IMPLEMENTATION DOCUMENTATION/phase3b_data_and_llm_storage.md`** — Implementation plan for Phase 4B

### Phase 4+ — Future
- **`PHASE_4_AI_ANALYTICS.md`** — ML-based site classification, smart routing
- **`PHASE_5_DISTRIBUTED_SCALING.md`** — Distributed crawling with shared profile cache
- **`PHASE_6_TAURI_DESKTOP.md`** — Desktop application packaging
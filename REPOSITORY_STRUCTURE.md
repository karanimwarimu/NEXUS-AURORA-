# Repository Structure

> NEXUS AURORA v4.6.0 — reflects the current state including debug campaign fixes (Steps 1–14), provider fallback architecture, action-link crawl hygiene, crawl_id propagation, Playwright resource blocking, and Phase 4C infrastructure hardening.

```text
.
├── .gitignore
├── LICENSE
├── README.md
├── REPOSITORY_STRUCTURE.md
├── release_notes_v4.4.0.md                              ★ v4.4.0 release notes
├── release_notes_v4.5.0.md                              ★ v4.5.0 release notes
├── release_notes_v4.6.0.md                              ★ new: v4.6.0 release notes
├── Nexora application/
│   ├── application documents/
│   │   ├── requirements.txt
│   │   └── release_notes_v4.6.0.md                      ★ v4.6.0 release notes
│   ├── Crawler/
│   │   ├── __init__.py
│   │   ├── scrapy.cfg
│   │   ├── enrich.py                                    ★ offline on-demand enrichment CLI
│   │   ├── nexora_crawler/
│   │   │   ├── .env                                     ← secrets + Phase 4B toggles (synced to settings.py)
│   │   │   ├── api/                                     ← FastAPI package (replaces old api.py)
│   │   │   │   ├── __init__.py                          FastAPI app + CLI entrypoint
│   │   │   │   ├── __main__.py                          `python -m nexora_crawler.api`
│   │   │   │   ├── auth.py                              JWT + workspace isolation
│   │   │   │   ├── database/
│   │   │   │   │   ├── __init__.py
│   │   │   │   │   └── connection.py                    Async DB (aiosqlite / asyncpg)
│   │   │   │   └── routes/
│   │   │   │       ├── __init__.py
│   │   │   │       ├── search.py                        Vector search endpoints
│   │   │   │       ├── webhooks.py                      Webhook CRUD
│   │   │   │       ├── jobs.py                          Generic job submission + status
│   │   │   │       ├── gdpr.py                          GDPR erase
│   │   │   │       ├── extract.py                       Schema-driven extraction
│   │   │   │       └── health.py                        Health checks
│   │   │   ├── jobs/                                     Job type registry
│   │   │   │   ├── __init__.py
│   │   │   │   └── registry.py                          5 built-in types
│   │   │   ├── tasks/                                    Simplified job dispatcher
│   │   │   │   ├── __init__.py
│   │   │   │   └── dispatcher.py                        In-process dispatch (no Celery)
│   │   │   ├── items.py                                 ← Phase 4A/4B item fields (incl. vector_backend)
│   │   │   ├── settings.py                              ← pipeline chain (100→600) + 4B/4C config
│   │   │   ├── sitemap_detector.py
│   │   │   ├── spiders/
│   │   │   │   └── nexora_spider.py
│   │   │   ├── middlewares/
│   │   │   │   ├── __init__.py
│   │   │   │   ├── dynamic_detection.py                 ← Phase 3 Core: JS vs Static detection + PLAYWRIGHT_ABORT_REQUEST callback + stealth script
│   │   │   │   ├── exponential_backoff.py
│   │   │   │   ├── playwright_cleanup.py
│   │   │   │   └── playwright_resource_blocker.py
│   │   │   ├── AI_Utilities/                            ← Phase 4B: embedding engine
│   │   │   │   └── embedding_engine.py                  ★ provider-aware (HF legacy / LiteLLM)
│   │   │   ├── pipelines/                               ← Phase 4A + 4B modular pipelines
│   │   │   │   ├── __init__.py                          ← Phase 1-3: Extraction, Style, Export, Dataset
│   │   │   │   ├── markdown_pipeline.py                 ← Phase 4A (110): HTML → Markdown + multimodal
│   │   │   │   ├── schema_enricher.py                   ← Phase 4A (160): unified schema + website_type
│   │   │   │   ├── metadata_indexer.py                  ← Phase 4A (165): SQLite metadata persistence
│   │   │   │   ├── parquet_export.py                    ← Phase 4A (450): compressed Parquet export
│   │   │   │   ├── ai_enrichment.py                     ← Phase 4B (250): summary + tags + embedding (+ _truncate_text)
│   │   │   │   ├── chunking_pipeline.py                 ← Phase 4B (260): Markdown → NexoraChunk
│   │   │   │   ├── vector_index_pipeline.py             ← Phase 4B (270): chunks → BaseVectorStore
│   │   │   │   ├── test_ai.py                           ← Phase 4B: HF connectivity probe (LiteLLM LLM + direct embedding)
│   │   │   │   ├── test_ai_direct_hf.py                 ← Phase 4B: huggingface_hub InferenceClient probe
│   │   │   │   └── test_vector_store.py                 ← Phase 4B: Chroma store/retrieval verification
│   │   │   └── vector_store/                            ← Phase 4B: storage abstraction
│   │   │       ├── base.py                              ← BaseVectorStore + VectorRecord/SearchQuery/SearchResult
│   │   │       ├── chroma_store.py                      ← ChromaDB backend (local dev)
│   │   │       ├── pgvector_store.py                    ← pgvector backend (Supabase/Postgres)
│   │   │       └── factory.py                           ← build_vector_store() + async singleton
│   │   └── Extractor/
│   │       ├── multimodal_extractor.py                  ← Phase 4A: image/video asset extraction
│   │       └── ... (Beautifulsoup/Trafilatura/parser/etc.)
│   ├── Models/
│   │   └── lid.176.ftz                                  ← Language detection model
│   ├── output/
│   │   ├── master_dataset.csv
│   │   ├── pages/                                       ← per-page CSV+JSON exports
│   │   ├── parquet/                                     ← Phase 4A: Parquet exports
│   │   └── audit/                                       ← benchmark & test reports (45-test Phase 4B suite)
│   │       ├── NEXORA_PHASE4B_TEST_SUMMARY.md           ★ comprehensive test summary
│   │       ├── BUG_enrich_py_missing_helpers.md         ★ known bug documentation
│   │       ├── audit_round3_step3_2.py                  ★ R3 integration tests
│   │       ├── audit_round3_step3_3.py                  ★ R3 regression tests
│   │       ├── R1-Step1.1-*.json/.md                    Round 1 audit artifacts
│   │       ├── R1-Step1.2-*.json/.md                    Round 1 audit artifacts
│   │       ├── R1-Step1.3-*.json/.md                    Round 1 audit artifacts
│   │       ├── R2-Step2.1-*.json/.md                    Round 2 audit artifacts
│   │       ├── R2-Step2.2-*.json/.md                    Round 2 audit artifacts
│   │       ├── R2-Step2.3-*.json/.md                    Round 2 audit artifacts
│   │       ├── R2-Step2.4-*.json/.md                    Round 2 audit artifacts
│   │       ├── R2-Step2.5-*.json/.md                    Round 2 audit artifacts
│   │       ├── R2-Step2.6-*.json/.md                    Round 2 audit artifacts
│   │       ├── R3-Step3.1-*.json/.md                    Round 3 audit artifacts
│   │       ├── R3-Step3.2-*.json/.md                    Round 3 audit artifacts
│   │       └── R3-Step3.3-*.json/.md                    Round 3 audit artifacts
│   ├── tests/
│   │   ├── test_phase4a.py                              ← Phase 4A: 18-test suite
│   │   └── ... (Phase 3 live-site / benchmark scripts)
│   ├── release_notes_v4.1.0.md
│   └── release_notes_v4.4.0.md                          ★ v4.4.0 release notes
├── data/
│   ├── test_profiles.db                                 ← SQLite site profile cache
│   ├── nexora_metadata.db                               ← Phase 4A/4C: SQLite metadata store (9 tables)
│   └── chroma/                                          ← Phase 4B: vector store (auto-created; chroma.sqlite3 + segments)
└── Project Tools/
    ├── switch_model_guide.md                            ← Phase 4B: model/provider/backend switch guide
    ├── competitive_analysis_nexora_vs_industry.md
    ├── Phase 1 Documentation/
    ├── Phase 2 Documentation/
    ├── Phase 3 Documentation/
    ├── Phase 4 Documentation/
    │   └── release_notes_v4.1.0.md                      ← prior release notes
    ├── Phase 5 Documentation/
    ├── Phase 6 Documentation/
    ├── Phase 7 Documentation/
    └── Studytools/
```

## Key Components

### Phase 3 — Dynamic Detection Middleware
- **`Crawler/nexora_crawler/middlewares/dynamic_detection.py`** — Core decision engine routing requests to static HTTP or Playwright JS rendering. Uses 8 signals: framework markers, script ratio, text density, body length, anti-bot patterns, SPA mount points, bundle patterns, and noscript tags. Contains `_abort_blocked_resources()` callback for route-level resource blocking.
- **`Crawler/nexora_crawler/middlewares/exponential_backoff.py`** — Exponential backoff retry for 429/503/408 (with `IgnoreRequest` guard).
- **`Crawler/nexora_crawler/middlewares/playwright_resource_blocker.py`** — Blocks images/fonts/analytics in Playwright pages at the JS level.
- **`tests/real_site_benchmark_phase3.py`** — 50-site benchmark across 8 categories.

### Phase 4A — Storage & Multi-Format Ingestion Engine ✅ (v4.1.0)
- **`Crawler/nexora_crawler/pipelines/markdown_pipeline.py`** — HTML → clean Markdown via Trafilatura (110).
- **`Extractor/multimodal_extractor.py`** — Image/video metadata extraction.
- **`Crawler/nexora_crawler/pipelines/schema_enricher.py`** — UnifiedSchemaEnricher (160).
- **`Crawler/nexora_crawler/pipelines/metadata_indexer.py`** — MetadataIndexerPipeline (165) → SQLite.
- **`Crawler/nexora_crawler/pipelines/parquet_export.py`** — ParquetExportPipeline (450).
- **`Crawler/nexora_crawler/storage/`** — `base.py` interfaces, `models.py` dataclasses, `local_sqlite.py` implementation.
- **`data/nexora_metadata.db`** — Auto-created SQLite metadata store.
- **`tests/test_phase4a.py`** — 18-test suite.

### Phase 4B — AI Enrichment & Vector Indexing ✅ (v4.5.0)
- **`Crawler/nexora_crawler/AI_Utilities/embedding_engine.py`** — `UnifiedEmbeddingEngine`. Provider-aware: `huggingface` → HF router legacy `feature-extraction` endpoint; others → LiteLLM `aembedding`. Circuit breaker prevents timeout drains; fallback engine routes to secondary provider when primary is quota-exhausted.
- **`Crawler/nexora_crawler/pipelines/ai_enrichment.py`** — `AIEnrichmentPipeline` (250): LLM summary + tags. Circuit breaker skips remaining pages after N consecutive failures; fallback provider retries LLM calls when breaker opens. Includes `_truncate_text()` for clean prompt boundaries.
- **`Crawler/nexora_crawler/pipelines/chunking_pipeline.py`** — `StructuralChunkingPipeline` (260): Markdown → `NexoraChunk` (~512 tokens), per-chunk `embed_batch()` embeddings (replaces inherited page-level embedding). `_estimate_tokens()` single source of truth, always `int`.
- **`Crawler/nexora_crawler/pipelines/vector_index_pipeline.py`** — `VectorIndexPipeline` (270): `NexoraChunk` → `VectorRecord` → `BaseVectorStore`.
- **`Crawler/nexora_crawler/vector_store/`** — `base.py` (`BaseVectorStore` contract), `chroma_store.py` (local), `pgvector_store.py` (Supabase/Postgres), `factory.py` (`build_vector_store` with settings-aware `_cfg()` resolver + async singleton `get_vector_store()`).
- **`data/chroma/`** — Auto-created Chroma persistence (verified: 124 records indexed in a live run).
- **`Crawler/nexora_crawler/pipelines/test_ai.py`** / **`test_ai_direct_hf.py`** — connectivity probes.
- **`Crawler/nexora_crawler/pipelines/test_vector_store.py`** — proves embeddings are stored in and retrieveable from Chroma (health, count, sample records, round-trip search).
- **`Project Tools/switch_model_guide.md`** — change model/provider/backend via settings only.

### Phase 4C — API Layer & Multi-Tenancy ✅ (v4.6.0)
- **`Crawler/nexora_crawler/api/__init__.py`** — FastAPI app (v4.5.0), lifespan auto-migration hook, CORS from `NEXORA_CORS_ORIGINS`, `NEXORA_API_WORKERS` wired to uvicorn.
- **`Crawler/nexora_crawler/api/__main__.py`** — `python -m nexora_crawler.api` entrypoint.
- **`Crawler/nexora_crawler/api/auth.py`** — JWT verification with env-gated dev bypass (`NEXORA_AUTH_BYPASS_ENABLED=false`); startup warning on default secret.
- **`Crawler/nexora_crawler/api/database/connection.py`** — Async connection singleton (`aiosqlite` dev / `asyncpg` prod) pointing to unified `NEXORA_METADATA_DB`.
- **`Crawler/nexora_crawler/api/routes/search.py`** — Vector search (`/v1/search/semantic`, `/v1/search/hybrid`, `/v1/search/by-source/{source_type}/{source_id}/similar`).
- **`Crawler/nexora_crawler/api/routes/webhooks.py`** — Webhook CRUD with secret returned once on create.
- **`Crawler/nexora_crawler/api/routes/jobs.py`** — Generic job submission (`POST /v1/jobs`) with status polling (`GET /v1/jobs/{id}`); stub handlers return 501.
- **`Crawler/nexora_crawler/api/routes/gdpr.py`** — GDPR Article 17 right-to-erasure endpoint.
- **`Crawler/nexora_crawler/api/routes/extract.py`** — Schema-driven extraction endpoint.
- **`Crawler/nexora_crawler/api/routes/health.py`** — Liveness (`/health`) and readiness (`/health/detailed`) endpoints.
- **`Crawler/nexora_crawler/jobs/registry.py`** — `JobTypeRegistry` with 5 built-in types (`crawl`, `schema_extract`, `index_search`, `index_add`, `export`).
- **`Crawler/nexora_crawler/tasks/dispatcher.py`** — In-process job dispatcher (no Celery); runs handlers in thread pool via `run_in_executor`.
- **`Crawler/nexora_crawler/storage/local_sqlite.py`** — 9 tables (`pages`, `crawl_jobs` + 6 Phase 4C tables); `workspace_id` backfill; migration-before-DDL ordering.

### On-Demand Enrichment Rework + Debug Campaign (v4.4.0 – v4.5.0)
- **`Crawler/nexora_crawler/settings.py`** — `NEXORA_ENRICH_MODE` flag (`"eager"` | `"on_demand"`). Conditional `ITEM_PIPELINES` (8 pipelines in on_demand, 11 in eager). `_anchored_path()` resolves relative DB/chroma paths against settings file directory. `NEXORA_AI_FAILFAST_THRESHOLD` and `NEXORA_AI_FALLBACK_*` settings for circuit breaker + provider fallback. `PLAYWRIGHT_ABORT_REQUEST` for route-level resource blocking.
- **`Crawler/nexora_crawler/api/__init__.py`** — `enrich_mode` in `CrawlRequest`/`CrawlResponse`, `_normalize_enrich_mode()`, subprocess env forwarding, settings reload in `run_cli_direct()`. Generates `crawl_id = uuid.uuid4().hex` per crawl. Lifespan hook auto-migrates database.
- **`Crawler/nexora_crawler/spiders/nexora_spider.py`** — Accepts `crawl_id` parameter; `CloseSpider` on `max_pages` cap.
- **`Crawler/nexora_crawler/storage/local_sqlite.py`** — `_migrate_schema()` (markdown_preview→markdown), `_limit_clause()` (None-safe LIMIT), `get_unenriched_pages()`, `update_enrichment()`.
- **`Crawler/nexora_crawler/items.py`** — `vector_backend`, `ai_status` fields. Removed non-functional mangled `__skip` field.
- **`Crawler/enrich.py`** — Offline enrichment CLI with `_build_crawler()`, `_collect_targets()`, `_enrich_row()`. Deserializes `ai_tags_json`; write-back preserves existing summary/tags when new values are empty.
- **`Crawler/nexora_crawler/pipelines/__init__.py`** — `NexoraExtractionPipeline` uses `scrapy.exceptions.DropItem` for duplicates (was `__skip` KeyError). Dead `__skip` guards removed.
- **`Crawler/nexora_crawler/pipelines/parquet_export.py`** — Catch-all JSON-stringify for nested fields prevents PyArrow `struct<>` inference from unwritable empty dicts.
- **`Crawler/nexora_crawler/middlewares/__init__.py`** — `_INFRA_PATH_RE` pass-through for `/robots.txt` and `sitemap*.xml`. `_BLOCKED_QUERY_RE` blocks action query params (`vote`, `hide`, `submit`, `action=history`, etc.). `BLOCKED_PATH_SEGMENTS` set for path-segment filtering.
- **`Crawler/nexora_crawler/middlewares/exponential_backoff.py`** — `IgnoreRequest` early-exit in `process_exception`.
- **`Crawler/nexora_crawler/middlewares/playwright_cleanup.py`** — Silenced shutdown noise (`Event loop is closed` / `Task was destroyed`).
- **`Crawler/nexora_crawler/sitemap_detector.py`** — Pre-discovery redirect resolution in `discover()`.
- **`Extractor/multimodal_extractor.py`** — `_descriptor_weight()` and `_safe_dimension()` handle `2x`/`100%`/`auto`/trailing-comma srcsets.
- **`outputs/audit/`** — 45-test verification suite (39 PASS, 5 FAIL, 1 SKIP). See `NEXORA_PHASE4B_TEST_SUMMARY.md` for details.
- **`outputs/qa_run_20260720/`** — Live 10-test QA scorecard + 14-step debug campaign log + open items resolution (crawl_id + resource blocking).

### Phase 4+ — Future
- **`PHASE_4_AI_ANALYTICS.md`** — ML-based site classification, smart routing
- **`PHASE_5_DISTRIBUTED_SCALING.md`** — Distributed crawling with shared profile cache
- **`PHASE_6_TAURI_DESKTOP.md`** — Desktop application packaging
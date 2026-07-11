# Repository Structure

> NEXUS AURORA v4.2.1 — reflects the current state including Phase 4B (AI enrichment, embeddings, chunking, vector indexing).

```text
.
├── .gitignore
├── LICENSE
├── README.md
├── REPOSITORY_STRUCTURE.md
├── Nexora application/
│   ├── application documents/
│   │   └── requirements.txt
│   ├── Crawler/
│   │   ├── __init__.py
│   │   ├── scrapy.cfg
│   │   ├── nexora_crawler/
│   │   │   ├── .env                                  ← secrets + Phase 4B toggles (synced to settings.py)
│   │   │   ├── api.py                                ← FastAPI + interactive CLI
│   │   │   ├── items.py                              ← Phase 4A/4B item fields
│   │   │   ├── settings.py                           ← pipeline chain (100→600) + 4B config
│   │   │   ├── sitemap_detector.py
│   │   │   ├── spiders/
│   │   │   │   └── nexora_spider.py
│   │   │   ├── middlewares/
│   │   │   │   ├── __init__.py
│   │   │   │   ├── dynamic_detection.py             ← Phase 3 Core: JS vs Static detection
│   │   │   │   ├── exponential_backoff.py
│   │   │   │   ├── playwright_cleanup.py
│   │   │   │   └── playwright_resource_blocker.py
│   │   │   ├── AI_Utilities/                         ← Phase 4B: embedding engine
│   │   │   │   └── embedding_engine.py               ★ provider-aware (HF legacy / LiteLLM)
│   │   │   ├── pipelines/                            ← Phase 4A + 4B modular pipelines
│   │   │   │   ├── __init__.py                       ← Phase 1-3: Extraction, Style, Export, Dataset
│   │   │   │   ├── markdown_pipeline.py              ← Phase 4A (110): HTML → Markdown + multimodal
│   │   │   │   ├── schema_enricher.py                ← Phase 4A (160): unified schema + website_type
│   │   │   │   ├── metadata_indexer.py               ← Phase 4A (165): SQLite metadata persistence
│   │   │   │   ├── parquet_export.py                 ← Phase 4A (450): compressed Parquet export
│   │   │   │   ├── ai_enrichment.py                  ← Phase 4B (250): summary + tags + embedding
│   │   │   │   ├── chunking_pipeline.py              ← Phase 4B (260): Markdown → NexoraChunk
│   │   │   │   ├── vector_index_pipeline.py          ← Phase 4B (270): chunks → BaseVectorStore
│   │   │   │   ├── test_ai.py                        ← Phase 4B: HF connectivity probe (LiteLLM LLM + direct embedding)
│   │   │   │   ├── test_ai_direct_hf.py              ← Phase 4B: huggingface_hub InferenceClient probe
│   │   │   │   └── test_vector_store.py              ← Phase 4B: Chroma store/retrieval verification
│   │   │   └── vector_store/                         ← Phase 4B: storage abstraction
│   │   │       ├── base.py                           ← BaseVectorStore + VectorRecord/SearchQuery/SearchResult
│   │   │       ├── chroma_store.py                   ← ChromaDB backend (local dev)
│   │   │       ├── pgvector_store.py                 ← pgvector backend (Supabase/Postgres)
│   │   │       └── factory.py                        ← build_vector_store()
│   │   └── Extractor/
│   │       ├── multimodal_extractor.py               ← Phase 4A: image/video asset extraction
│   │       └── ... (Beautifulsoup/Trafilatura/parser/etc.)
│   ├── Models/
│   │   └── lid.176.ftz                               ← Language detection model
│   ├── output/
│   │   ├── master_dataset.csv
│   │   ├── pages/                                    ← per-page CSV+JSON exports
│   │   ├── parquet/                                  ← Phase 4A: Parquet exports
│   │   └── audit/                                    ← benchmark & test reports
│   └── tests/
│       ├── test_phase4a.py                           ← Phase 4A: 18-test suite
│       └── ... (Phase 3 live-site / benchmark scripts)
├── data/
│   ├── test_profiles.db                              ← SQLite site profile cache
│   ├── nexora_metadata.db                            ← Phase 4A: SQLite metadata store (auto-created)
│   └── chroma/                                       ← Phase 4B: vector store (auto-created; chroma.sqlite3 + segments)
└── Project Tools/
    ├── switch_model_guide.md                         ← Phase 4B: model/provider/backend switch guide
    ├── competitive_analysis_nexora_vs_industry.md
    ├── Phase 1 Documentation/
    ├── Phase 2 Documentation/
    ├── Phase 3 Documentation/
    ├── Phase 4 Documentation/
    │   └── release_notes_v4.1.0.md                   ← prior release notes
    ├── Phase 5 Documentation/
    ├── Phase 6 Documentation/
    ├── Phase 7 Documentation/
    └── Studytools/
```

## Key Components

### Phase 3 — Dynamic Detection Middleware
- **`Crawler/nexora_crawler/middlewares/dynamic_detection.py`** — Core decision engine routing requests to static HTTP or Playwright JS rendering. Uses 8 signals: framework markers, script ratio, text density, body length, anti-bot patterns, SPA mount points, bundle patterns, and noscript tags.
- **`Crawler/nexora_crawler/middlewares/exponential_backoff.py`** — Exponential backoff retry for 429/503/408.
- **`Crawler/nexora_crawler/middlewares/playwright_resource_blocker.py`** — Blocks images/fonts/analytics in Playwright pages.
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

### Phase 4B — AI Enrichment & Vector Indexing ✅ (v4.2.1)
- **`Crawler/nexora_crawler/AI_Utilities/embedding_engine.py`** — `UnifiedEmbeddingEngine`. Provider-aware: `huggingface` → HF router legacy `feature-extraction` endpoint; others → LiteLLM `aembedding`.
- **`Crawler/nexora_crawler/pipelines/ai_enrichment.py`** — `AIEnrichmentPipeline` (250): LLM summary + tags + page-level embedding.
- **`Crawler/nexora_crawler/pipelines/chunking_pipeline.py`** — `StructuralChunkingPipeline` (260): Markdown → `NexoraChunk` (~512 tokens), inherits `ai_summary`/`ai_tags`/`ai_embedding`.
- **`Crawler/nexora_crawler/pipelines/vector_index_pipeline.py`** — `VectorIndexPipeline` (270): `NexoraChunk` → `VectorRecord` → `BaseVectorStore`.
- **`Crawler/nexora_crawler/vector_store/`** — `base.py` (`BaseVectorStore` contract), `chroma_store.py` (local), `pgvector_store.py` (Supabase/Postgres), `factory.py` (`build_vector_store`).
- **`data/chroma/`** — Auto-created Chroma persistence (verified: 124 records indexed in a live run).
- **`Crawler/nexora_crawler/pipelines/test_ai.py`** / **`test_ai_direct_hf.py`** — connectivity probes.
- **`Crawler/nexora_crawler/pipelines/test_vector_store.py`** — proves embeddings are stored in and retrieveable from Chroma (health, count, sample records, round-trip search).
- **`Project Tools/switch_model_guide.md`** — change model/provider/backend via settings only.

### Phase 4+ — Future
- **`PHASE_4_AI_ANALYTICS.md`** — ML-based site classification, smart routing
- **`PHASE_5_DISTRIBUTED_SCALING.md`** — Distributed crawling with shared profile cache
- **`PHASE_6_TAURI_DESKTOP.md`** — Desktop application packaging

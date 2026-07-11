# NEXUS AURORA v4.2.1

> AI-powered website intelligence platform with static-first routing, browser-aware extraction, multi-format storage engine, AI enrichment, and vector indexing for production-grade RAG and web intelligence workflows.

[![Version](https://img.shields.io/badge/version-4.2.1-blue)]()
[![Python](https://img.shields.io/badge/python-3.11+-green)]()
[![License](https://img.shields.io/badge/license-MIT-lightgrey)]()
[![Status](https://img.shields.io/badge/status-phase%204B%20vector%20indexing-brightgreen)]()

---

## Table of Contents

- [Overview](#overview)
- [What's New in v4.2.1](#whats-new-in-v421)
- [Features](#features)
- [Architecture](#architecture)
  - [Complete Pipeline Chain](#complete-pipeline-chain)
  - [Dynamic Detection Engine](#dynamic-detection-engine)
- [Project Structure](#project-structure)
- [Installation](#installation)
- [Usage](#usage)
  - [Phase 1 — Single Page Extraction](#phase-1--single-page-extraction)
  - [Phase 2 — Scrapy Crawler](#phase-2--scrapy-crawler)
  - [Phase 2.6 — Interactive CLI & API](#phase-26--interactive-cli--api)
  - [Phase 3 — Dynamic Detection Middleware](#phase-3--dynamic-detection-middleware)
  - [Phase 4A — Storage & Multi-Format Export](#phase-4a--storage--multi-format-export)
  - [Phase 4B — AI Enrichment & Vector Indexing](#phase-4b--ai-enrichment--vector-indexing)
- [Crawl Strategies](#crawl-strategies)
- [Output Format](#output-format)
- [Configuration](#configuration)
- [Testing & Verification](#testing--verification)
- [Switching Models / Providers / Backends](#switching-models--providers--backends)
- [Development Roadmap](#development-roadmap)
- [Known Limitations](#known-limitations)
- [License](#license)

---

## Overview

**NEXUS AURORA** (codename: **Nexora**) is a Python web intelligence pipeline with an intelligent **static-first routing engine** and a **multi-format storage infrastructure**. It probes each URL via lightweight HTTP, decides if JavaScript rendering is needed using 8 detection signals, routes accordingly — saving 150-300MB RAM per page for static sites — then transforms raw HTML into clean, structured, multi-format outputs for human analysts, ML pipelines, and RAG systems.

On top of the Phase 4A storage engine, **v4.2.1 completes Phase 4B**: per-page AI summarization and tagging, sentence-transformers embeddings via the Hugging Face router, structural chunking, and vector indexing into Chroma (local) or pgvector/Supabase (production) — all behind a provider-agnostic interface so the embedding model, AI provider, and vector backend are **settings-only changes**.

> **Current Phase: 4B (v4.2.1)** — AI enrichment, embeddings, chunking, and vector indexing are implemented and verified end-to-end (124 records indexed in a live Chroma run).

---

## What's New in v4.2.1

| Feature | Description |
|---------|-------------|
| **AIEnrichmentPipeline** | Scrapy pipeline (Priority 250) generating a 2-3 sentence LLM summary + 3-5 topic tags per page, plus a page-level embedding |
| **UnifiedEmbeddingEngine** | Provider-aware embedding generator (`AI_Utilities/embedding_engine.py`). `huggingface` → HF router legacy `feature-extraction` endpoint; other providers (ollama/openai/…) → LiteLLM `aembedding` |
| **StructuralChunkingPipeline** | Scrapy pipeline (Priority 260) splitting Markdown into ~512-token semantic chunks; chunks inherit the page `ai_summary`, `ai_tags`, and `ai_embedding` |
| **VectorIndexPipeline** | Scrapy pipeline (Priority 270) converting `NexoraChunk` → `VectorRecord` and persisting via `BaseVectorStore` |
| **Vector Store Layer** | `BaseVectorStore` contract + `ChromaVectorStore` (local dev) + `PgVectorStore` (Supabase/Postgres), selected by `build_vector_store()` factory |
| **Default embedding model** | `sentence-transformers/all-MiniLM-L6-v2` (384-dim) via the HF router — fast, free, serverless |
| **Verification scripts** | `test_ai.py`, `test_ai_direct_hf.py` (connectivity), `test_vector_store.py` (proves embeddings are stored & retrieveable in Chroma) |
| **Model-switch guide** | `Project Tools/switch_model_guide.md` — change model/provider/backend with zero code changes |
| **Bug fixes** | Added missing `NexoraChunk.source_type`; fixed `ChromaVectorStore.add()` metadata serialization; synced `.env` to `settings.py` |

---

## Features

### Content Extraction
- **Structural metadata** — title, description, keywords, headings, images, internal links
- **Reader-mode text** — clean article body via Trafilatura
- **Semantic data** — JSON-LD, microdata, RDFa, Open Graph, Twitter Cards
- **Rich image assets** — URLs, alt text, dimensions
- **Graph relations** — canonical, prev/next pagination links

### Visual Design Intelligence
- CSS framework detection (Tailwind, Bootstrap, Materialize, Bulma, etc.)
- Dark/light theme inference
- Font and color palette extraction
- Layout type (flex, grid, float, table)
- Animation signals (CSS keyframes, GSAP, Framer Motion class names)

### Phase 3 — Intelligent Routing
- **Static-first design** — Zero Chromium processes for static sites
- **8 detection signals** — Framework patterns, script ratio, text density, body length, anti-bot checks, SPA mount points, bundle hashes, error fallback
- **7 framework detectors** — Next.js, Nuxt, Gatsby, React, Vue, Angular, Svelte
- **Anti-bot detection** — Cloudflare, DataDome, PerimeterX, hCaptcha/reCAPTCHA (including stealth 200 challenges)
- **SPA mount point detection** — Catches framework-agnostic SPA shells
- **24-hour profile cache** — SQLite-backed, TTL-based re-probe

### Phase 4A — Multi-Format Storage Engine
- **Markdown extraction** — HTML → clean Markdown with >50% token reduction
- **Multimodal asset isolation** — Structured metadata for images and videos (no binary download)
- **Unified schema** — Every record has entities, style_analysis, quality_scores with guaranteed defaults
- **Website classification** — Automatic e-commerce, blog, documentation, article, or unknown detection
- **SQLite metadata store** — Fast relational storage indexed by domain, crawl_id, website_type, language
- **Parquet export** — Columnar, compressed storage for ML pipelines (snappy compression, < 30% of equivalent JSON)
- **One crawl → multiple formats** — Markdown + JSON + CSV + Parquet + SQLite from a single pass

### Phase 4B — AI Enrichment & Vector Indexing (NEW)
- **AI summary + tags** — LLM-generated per page (LiteLLM against the HF router)
- **Embeddings** — sentence-transformers vectors via the HF router's legacy `feature-extraction` endpoint (the OpenAI-compatible `/v1/embeddings` does **not** support ST models)
- **Structural chunking** — Markdown split at heading/paragraph boundaries with overlap
- **Vector store** — Chroma (local) or pgvector/Supabase (production), behind one interface
- **Provider-agnostic** — switch embedding model, AI provider, or vector backend via settings only

---

## Architecture

### Complete Pipeline Chain

```
                         ┌─────────────────┐
                         │  Incoming URL    │
                         └────────┬────────┘
                                  │
                                  ▼
               ┌──────────────────────────────────────┐
               │      DYNAMIC DETECTION MIDDLEWARE    │
               │      (Priority 542 — Phase 3)        │
               │      Static HTTP or Playwright?      │
               └──────────────────┬───────────────────┘
                                  │
                                  ▼
               ┌──────────────────────────────────────┐
               │      EXTRACTION PIPELINE (100)       │
               │      BS4 + Trafilatura + Style       │
               └──────────────────┬───────────────────┘
                                  │
                                  ▼
               ┌──────────────────────────────────────┐
               │  ┌──────────────────────────────────┐ │
               │  │ PHASE 4A — STORAGE ENGINE        │ │
               │  │ [110] → MarkdownExtraction       │ │
               │  │ [150] → NexoraStylePipeline      │ │
               │  │ [160] → UnifiedSchemaEnricher    │ │
               │  │ [165] → MetadataIndexerPipeline  │ │
               │  └──────────────────────────────────┘ │
               │  ┌──────────────────────────────────┐ │
               │  │ PHASE 4B — AI ENRICHMENT         │ │
               │  │ [250] → AIEnrichmentPipeline     │ │  summary + tags + embedding
               │  │ [260] → StructuralChunkingPipeline│ │  Markdown → chunks
               │  │ [270] → VectorIndexPipeline       │ │  chunks → vector store
               │  └──────────────────────────────────┘ │
               │  [450] → ParquetExportPipeline       │
               └──────────────────┬───────────────────┘
                                  │
                                  ▼
               ┌──────────────────────────────────────┐
               │      EXPORT LAYER                    │
               │  [500] → JSON + CSV per page         │
               │  [600] → Master dataset CSV          │
               └──────────────────────────────────────┘
                                  │
                                  ▼
            ┌────────────┬────────────┬────────────┬────────────┐
            ▼            ▼            ▼            ▼            ▼
         Markdown    JSON/CSV    Parquet      SQLite      Vector Store
         (LLM)      (Inspect)   (ML/BI)     (Metadata)   (Chroma/pgvector)
```

### 8-Signal Decision Tree

```
HTTP GET → [1]Anti-Bot 403/429/503 → [1b]Anti-Bot 200 → [2]Short Body (<200ch+JS)
→ [3]Low Text Density → [4]Framework Patterns → [5]SPA Mount Points
→ [6]Bundle Hashes → [7]High Script Ratio → [8]Error Fallback → Static Route
```

---

## Dynamic Detection Engine

### Detected Frameworks (7 frameworks, 16+ patterns)

| Framework | Detection Patterns | Example Sites |
|-----------|-------------------|---------------|
| **Next.js** | `__NEXT_DATA__`, `/_next/`, `/_next/static/chunks`, `.next/server` | react.dev, vercel.com, supabase.com |
| **Nuxt** | `<meta generator="Nuxt">`, `data-v-xxxxxxxx`, `__VUE__` | vuejs.org, nuxt.com, gitlab.com |
| **Gatsby** | `<meta generator="Gatsby">`, `gatsby-focus-wrapper` | — |
| **React** | `data-reactroot`, `__reactFiber`, `/static/js/main.xxx.js` | Generic React SPAs |
| **Vue** | `__VUE__`, `vue-router`, `__vue_app__`, `/assets/index.xxx.js` | behance.net, laravel.com |
| **Angular** | `ng-version=`, `<app-root>`, `__ngContext__`, `/runtime.xxx.js`, `zone.js` | angular.io, rxjs.dev |
| **Svelte** | `svelte-xxxxxx`, `__svelte`, `/assets/index.xxx.js` | svelte.dev, kit.svelte.dev |

### Anti-Bot Protection Detected
- **Cloudflare** — `cf-browser-verification`, `turnstile`, `challenge-platform`, `/cdn-cgi/challenge`
- **DataDome** — `datadome`, `captcha-delivery`
- **PerimeterX** — `perimeterx`, `px-captcha`
- **CAPTCHA** — recaptcha, hCaptcha
- **Generic** — "Just a moment..." page titles

### Stealth Capabilities
- `navigator.webdriver` → `undefined`
- `navigator.plugins` → realistic Chrome plugin list
- `navigator.mimeTypes` → realistic MIME types
- WebGL vendor spoofing → Intel Iris Xe Graphics
- Safe `permissions.query` API handling

---

## Project Structure

```
NEXUS AURORA/
├── README.md
├── REPOSITORY_STRUCTURE.md
├── Nexora application/                     ← Main application source
│   ├── application documents/
│   │   └── requirements.txt
│   ├── Crawler/                            Scrapy project with Phases 1-4B
│   │   └── nexora_crawler/
│   │       ├── AI_Utilities/
│   │       │   └── embedding_engine.py          ★ Phase 4B: provider-aware embeddings
│   │       ├── middlewares/
│   │       │   ├── dynamic_detection.py          ★ Phase 3 core engine
│   │       │   ├── exponential_backoff.py
│   │       │   ├── playwright_cleanup.py
│   │       │   └── playwright_resource_blocker.py
│   │       ├── pipelines/                        ★ Phase 4A + 4B modular pipelines
│   │       │   ├── __init__.py                   Phase 1-3 pipelines
│   │       │   ├── markdown_pipeline.py          ★ Phase 4A
│   │       │   ├── schema_enricher.py            ★ Phase 4A
│   │       │   ├── metadata_indexer.py           ★ Phase 4A
│   │       │   ├── parquet_export.py             ★ Phase 4A
│   │       │   ├── ai_enrichment.py              ★ Phase 4B: summary + tags + embedding
│   │       │   ├── chunking_pipeline.py          ★ Phase 4B: Markdown → chunks
│   │       │   ├── vector_index_pipeline.py      ★ Phase 4B: chunks → vector store
│   │       │   ├── test_ai.py                    ★ Phase 4B: HF connectivity probe
│   │       │   ├── test_ai_direct_hf.py          ★ Phase 4B: huggingface_hub probe
│   │       │   └── test_vector_store.py          ★ Phase 4B: Chroma store/retrieval check
│   │       ├── vector_store/                     ★ Phase 4B storage abstraction
│   │       │   ├── base.py                       BaseVectorStore + VectorRecord/SearchQuery
│   │       │   ├── chroma_store.py               ChromaDB backend (local dev)
│   │       │   ├── pgvector_store.py             pgvector backend (Supabase/Postgres)
│   │       │   └── factory.py                   build_vector_store()
│   │       ├── storage/                          ★ Phase 4A storage layer
│   │       │   ├── base.py                       Abstract interfaces
│   │       │   ├── models.py                     Unified schema dataclass
│   │       │   └── local_sqlite.py               SQLite implementation
│   │       ├── spiders/
│   │       │   └── nexora_spider.py
│   │       ├── api.py                 FastAPI + interactive CLI
│   │       ├── items.py               Updated with Phase 4A/4B fields
│   │       ├── settings.py            Updated with Phase 4A/4B priorities
│   │       └── sitemap_detector.py
│   ├── Extractor/
│   │   ├── multimodal_extractor.py                ★ Phase 4A
│   │   └── ...
│   ├── Models/
│   │   └── lid.176.ftz
│   ├── output/
│   │   ├── audit/                                 Test reports & benchmarks
│   │   ├── parquet/                               ★ Phase 4A Parquet exports
│   │   ├── pages/
│   │   └── master_dataset.csv
│   ├── tests/
│   │   ├── test_phase4a.py                        ★ 18-test Phase 4A suite
│   │   └── ...
│   └── release_notes_v4.1.0.md
├── data/
│   ├── test_profiles.db
│   ├── nexora_metadata.db                         ★ Phase 4A auto-created DB
│   └── chroma/                                     ★ Phase 4B vector store (auto-created)
└── Project Tools/
    └── switch_model_guide.md                      ★ Phase 4B: model/provider/backend switching
```

For full details, see [REPOSITORY_STRUCTURE.md](REPOSITORY_STRUCTURE.md).

---

## Installation

### Prerequisites
- Python 3.11 or later
- pip

### Install Dependencies
```powershell
cd "Nexora application\application documents"
pip install -r requirements.txt
```

### Phase 4B Dependencies
```powershell
pip install litellm chromadb requests
# (optional, for the OpenAI/ollama provider paths) pip install sentence-transformers
```

### Install Playwright (for JS rendering)
```powershell
pip install scrapy-playwright playwright
playwright install chromium
set NEXORA_PLAYWRIGHT_ENABLED=1
```

### Optional: Language Detection Model
Download the FastText model to `Nexora application/Models/lid.176.ftz`. Language detection falls back gracefully if absent.

---

## Usage

### Phase 1 — Single Page Extraction
```powershell
cd "Nexora application/Extractor"
python main.py https://example.com
```

### Phase 2 — Scrapy Crawler
```powershell
cd "Nexora application/Crawler"

# Single page
scrapy crawl nexora -a urls="https://example.com"

# Linked pages (depth 1)
scrapy crawl nexora -a urls="https://example.com" -a strategy="linked-pages"

# Whole website (sitemap auto-discovery)
scrapy crawl nexora -a urls="https://example.com" -a strategy="whole-website"
```

### Phase 2.6 — Interactive CLI & API
```powershell
# Interactive CLI
cd "Nexora application/Crawler"
python -m nexora_crawler.api

# FastAPI REST server
python -m nexora_crawler.api --server
# API docs: http://localhost:8000/docs
```

### Phase 3 — Dynamic Detection Middleware
The middleware runs automatically when using the Scrapy crawler with `NEXORA_PLAYWRIGHT_ENABLED=1`:
```powershell
set NEXORA_PLAYWRIGHT_ENABLED=1
set NEXORA_STEALTH_ENABLED=1
scrapy crawl nexora -a urls="https://example.com"
```

### Phase 4A — Storage & Multi-Format Export
Phase 4A pipelines run automatically as part of the Scrapy pipeline chain. No additional commands needed. Outputs are generated in:

| Format | Location | Description |
|--------|----------|-------------|
| Markdown | `item["markdown"]` | In-memory; also in JSON/CSV exports |
| SQLite | `data/nexora_metadata.db` | Relational metadata store |
| Parquet | `output/parquet/` | Compressed columnar files |
| JSON/CSV | `output/pages/` | Per-page exports (existing) |

### Phase 4B — AI Enrichment & Vector Indexing
Phase 4B pipelines also run automatically in the chain. They require a Hugging Face token in `.env` (`NEXORA_AI_API_KEY`). A crawl that reaches the vector stage writes one `VectorRecord` per chunk into the configured backend (Chroma by default, at `data/chroma`).

Verify the AI + vector stack before/after a crawl:
```powershell
cd "Nexora application/Crawler"

# 1) Connectivity: LLM via LiteLLM + embedding via HF legacy endpoint
python -m nexora_crawler.pipelines.test_ai

# 2) Prove embeddings are STORED in and RETRIEVEABLE from Chroma
python -m nexora_crawler.pipelines.test_vector_store
```

`test_vector_store.py` prints the store health, record count, sample records (with vector dim), and a round-trip search whose top hit is the query chunk at `score≈1.0`.

---

## Crawl Strategies

| Strategy | Depth | Description |
|----------|-------|-------------|
| `single-page` | 0 | Process only the seed URL |
| `linked-pages` | 1 | Seed URL + all direct links |
| `whole-website` | 3 | Auto-detect sitemap; fallback to depth-3 crawl |
| `everything` | 5 | Deep domain crawl (locked to seed domain) |

All strategies respect `max_pages` safety cap (default: 1000, max: 50000).

---

## Output Format

```
output/
├── pages/
│   ├── example.com__about__20250624T143022.json
│   ├── example.com__about__20250624T143022.csv
├── parquet/                               ← Phase 4A
│   └── nexora_20260630_190925_0000.parquet
data/
├── nexora_metadata.db                     ← Phase 4A
└── chroma/                                ← Phase 4B vector store (auto-created)
    ├── chroma.sqlite3
    └── <uuid>/                            ← collection segments
```

### Phase 4B Fields (Added to Item)

| Field | Type | Description |
|-------|------|-------------|
| `ai_summary` | str | 2-3 sentence LLM summary of the page |
| `ai_tags` | list[str] | 3-5 generated topic tags |
| `ai_embedding` | list[float] | Page-level embedding (384-dim MiniLM) |
| `chunk_count` | int | Number of chunks produced |
| `chunk_ids` | list[str] | Chunk UUIDs |
| `chunks` | list[NexoraChunk] | In-memory chunks consumed by VectorIndexPipeline |
| `has_embedding` | bool | True once indexed |

---

## Configuration

Key settings in `Crawler/nexora_crawler/settings.py` (also overridable in `.env`):

| Setting | Default | Purpose |
|---------|---------|---------|
| `NEXORA_PLAYWRIGHT_ENABLED` | `True` | Enable Playwright for JS pages |
| `NEXORA_STEALTH_ENABLED` | `True` | Apply bot-detection evasion |
| `NEXORA_MARKDOWN_ENABLED` | `True` | Enable HTML → Markdown conversion |
| `NEXORA_PARQUET_ENABLED` | `True` | Enable compressed Parquet export |
| `NEXORA_METADATA_DB` | `./data/nexora_metadata.db` | SQLite metadata database path |
| `ROBOTSTXT_OBEY` | `True` | Respect robots.txt |
| `DOWNLOAD_DELAY` | `1.5` | Base delay between requests (seconds) |
| `AUTOTHROTTLE_ENABLED` | `True` | Adapt delay to server response time |
| `NEXORA_AI_ENABLED` | `True` | Enable Phase 4B AI enrichment |
| `NEXORA_AI_PROVIDER` | `huggingface` | `huggingface` / `ollama` / `openai` / `anthropic` |
| `NEXORA_AI_MODEL` | `Qwen/Qwen2.5-7B-Instruct` | LLM for summary/tags |
| `NEXORA_AI_EMBEDDING_MODEL` | `sentence-transformers/all-MiniLM-L6-v2` | Embedding model |
| `NEXORA_EMBEDDING_DIM` | `384` | Must match the embedding model |
| `NEXORA_VECTOR_BACKEND` | `chroma` | `chroma` (local) / `pgvector` (Supabase) |
| `NEXORA_VECTOR_INDEX_ENABLED` | `True` | Index chunks into the vector store |
| `NEXORA_CHROMA_PATH` | `./data/chroma` | Chroma persistence path |
| `NEXORA_CHUNK_SIZE` | `512` | Target tokens per chunk |
| `NEXORA_CHUNK_OVERLAP` | `128` | Overlap tokens between chunks |

---

## Testing & Verification

```powershell
cd "Nexora application"

# Phase 3 — Live-site validation
python tests/real_site_test_phase3.py

# Phase 4A — Storage engine (18 tests)
python -m pytest tests/test_phase4a.py -v

# Phase 4B — HF connectivity (LLM via LiteLLM + embedding via legacy endpoint)
python -m nexora_crawler.pipelines.test_ai

# Phase 4B — Chroma storage & retrieval round-trip
python -m nexora_crawler.pipelines.test_vector_store
```

---

## Switching Models / Providers / Backends

All three are **settings-only changes** — no code changes required. See [`Project Tools/switch_model_guide.md`](Project%20Tools/switch_model_guide.md) for the full matrix.

- **Embedding model (same HF family):** update `NEXORA_AI_EMBEDDING_MODEL` + `NEXORA_EMBEDDING_DIM`. If the dimension changes, wipe `data/chroma` (the HNSW index bakes in the dim).
- **AI provider:** update `NEXORA_AI_PROVIDER` / `NEXORA_AI_MODEL` / `NEXORA_AI_BASE_URL` / `NEXORA_AI_API_KEY`. Non-`huggingface` providers use LiteLLM's OpenAI-compatible API.
- **Vector backend → pgvector/Supabase:** set `NEXORA_VECTOR_BACKEND=pgvector` and put `NEXORA_DATABASE_URL` + `NEXORA_EMBEDDING_DIM` in `.env` (the factory reads these from the environment). Use the Supabase **direct** connection string (port 5432), not the 6543 pooler.

---

## Development Roadmap

| Phase | Status | Scope |
|-------|--------|-------|
| **1** | ✅ Complete | Single-page extraction CLI |
| **2 / 2.5** | ✅ Complete | Multi-page Scrapy crawler + style extraction |
| **2.6** | ✅ Complete | FastAPI REST API + interactive CLI + sitemap discovery |
| **3** | ✅ Complete (3.4) | DynamicDetectionMiddleware with 8-signal engine, 85-90% accuracy |
| **4A** | ✅ Complete (v4.1.0) | Storage & Multi-Format Ingestion Engine |
| **4B** | ✅ Complete (v4.2.1) | AI enrichment, embeddings, chunking, vector indexing |
| **5** | 📋 Planned | Distributed crawling, shared profile cache |
| **6** | 📋 Planned | Tauri desktop application |
| **7** | 📋 Planned | Hybrid search, list_all for migration tooling |

---

## Known Limitations (v4.2.1)

- **Page-level embeddings:** The embedding is generated once per page (on the whole Markdown) and **inherited by all chunks**. Retrieval therefore behaves at page granularity until per-chunk embeddings are implemented.
- **HF router rate limits:** The free HF router can return 429/503; the pipeline degrades gracefully (skips embedding, logs a warning) so the crawl continues.
- **Chroma dimension lock:** Switching embedding models with a different dimension requires wiping `data/chroma` before re-crawling.
- **Network-dependent** — ~12% of sites may timeout; these correctly fallback to Playwright but add latency.
- **Angular production builds** — `ng-version=` attribute is removed; detection relies on bundle patterns.
- **No auth** — FastAPI endpoints are open; job store is in-memory only.
- **Parquet requires pandas+pyarrow** — must be installed separately.

---

## License

MIT License — see [LICENSE](LICENSE) for details.

---

<p align="center">
  <strong>NEXUS AURORA v4.2.1</strong> — Intelligent website intelligence for ML, RAG, and competitive analysis.
</p>

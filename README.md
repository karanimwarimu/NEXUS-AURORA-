# NEXUS AURORA v4.5.0

> AI-powered website intelligence platform with static-first routing, browser-aware extraction, multi-format storage engine, on-demand AI enrichment (default), eager inline enrichment (fallback), and vector indexing for production-grade RAG and web intelligence workflows.

[![Version](https://img.shields.io/badge/version-4.5.0-blue)]()
[![Python](https://img.shields.io/badge/python-3.11+-green)]()
[![License](https://img.shields.io/badge/license-MIT-lightgrey)]()
[![Status](https://img.shields.io/badge/status-phase%204C%20hardened-brightgreen)]()

---

## Table of Contents

- [Overview](#overview)
- [What's New in v4.5.0](#whats-new-in-v450)
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

On top of the Phase 4A storage engine, **v4.3.0 completes Phase 4B verification**: per-page AI summarization and tagging, sentence-transformers embeddings via the Hugging Face router, structural chunking, and vector indexing into Chroma (local) or pgvector/Supabase (production) — all behind a provider-agnostic interface. **Crawl and enrichment are now decoupled:** by default (`on_demand` mode), crawls are fast with no AI calls. AI enrichment runs later via the offline `enrich.py` command or inline via `eager` mode.

> **Current Phase: 4C (v4.6.0)** — Phase 4C infrastructure integrated, hardened, and verified. All S1/S2 defects from independent gap analysis resolved. Database migration safety, transaction durability, tenant isolation, vector store initialization, job semantics, and dependency declarations complete.

---

## What's New in v4.6.0

| Feature | Description |
|---------|-------------|
| **Phase 4C infrastructure hardened** | Database migration order fixed (workspace_id backfill runs before DDL); lifespan auto-migration hook added; all async route writes now durable with explicit `await db.commit()`. |
| **Tenant isolation enforced** | JWT validation now evaluated before `X-Workspace-Id` dev bypass; bypass gated behind `NEXORA_AUTH_BYPASS_ENABLED=false` by default; startup warning on default `JWT_SECRET`. |
| **Job execution semantics fixed** | Stub handlers now return `HTTP 501 Not Implemented`; added `GET /v1/jobs/{job_id}` status endpoint; async tasks tracked to prevent GC. |
| **Dead settings wired** | `NEXORA_CORS_ORIGINS` parsed from env and passed to CORS middleware; `NEXORA_API_WORKERS` forwarded to `uvicorn.run()`; version strings aligned to `4.5.0`. |
| **Dependencies declared** | Added fastapi, uvicorn, pydantic, PyJWT, aiosqlite, asyncpg, bcrypt, slowapi, python-multipart to `requirements.txt`; pinned `scrapy-playwright>=0.0.48`. |

### v4.5.0 (Previous Release)

| Feature | Description |
|---------|-------------|
| **crawl_id propagation fixed** | `api.py` now generates a UUID per crawl and passes it to the spider. Every row in the SQLite `pages` table now has a non-empty `crawl_id`, enabling multi-crawl traceability and `--crawl-id` filtering in `enrich.py`. Verified on books.toscrape.com, quotes.toscrape.com/js/, and react-shopping-cart. |
| **PLAYWRIGHT_BLOCKED_RESOURCE_TYPES wired** | `dynamic_detection.py` now registers a Playwright route-level abort callback (`PLAYWRIGHT_ABORT_REQUEST`) that blocks `image`, `font`, `media`, and `ping` requests before they reach the network. Uses the correct scrapy-playwright mechanism (`PLAYWRIGHT_ABORT_REQUEST`, not `playwright_page_methods` which fires too late). Verified: 17/17 image requests aborted on react-shopping-cart, 26/26 on Wikipedia, 1/1 font on quotes.toscrape.com/js/. |

### v4.4.0 (Previous Release)

| Feature | Description |
|---------|-------------|
| **14-step debug campaign** | Live 10-test QA run (2026-07-20) exposed 6 runtime bugs + 1 split-brain path bug. All fixed and verified. |
| **`__skip` crash fixed** | Duplicate pages now cleanly drop via `scrapy.exceptions.DropItem` instead of crashing with `KeyError`. |
| **MarkdownPipeline srcset crash fixed** | `_descriptor_weight()` and `_safe_dimension()` handle `2x`/`100%`/`auto`/trailing-comma srcsets. |
| **robots.txt enforcement fixed** | `ContentTypeFilterMiddleware` now lets `/robots.txt` and `sitemap*.xml` through before content-type blocking. |
| **Parquet empty-struct fix** | Catch-all JSON-stringify prevents PyArrow `struct<>` inference from unwritable empty dicts. |
| **Eager-mode circuit breaker** | After 3 consecutive AI failures, all further calls are skipped for the run. |
| **Provider fallback architecture** | New `NEXORA_AI_FALLBACK_*` settings. When primary breaker opens, calls route to a secondary provider. |
| **Split-brain DB path fix** | Paths resolved against settings file directory, not CWD. |
| **Action-link crawl hygiene** | `/vote`, `/hide`, `/submit` path patterns + `action=`/`mobileaction=` query param blocking. |
| **Test 02 fixture refreshed** | Dead fixture replaced with live `react-shopping-cart-67954.firebaseapp.com` (200). |

### v4.3.0 (Previous Release)

| Feature | Description |
|---------|-------------|
| **On-Demand Enrichment** | `NEXORA_ENRICH_MODE` flag (`"eager"` \| `"on_demand"`). Default: `"on_demand"` — fast crawls with no AI calls. Enrich later via `enrich.py`. |
| **Offline `enrich.py` command** | Reuses existing Phase 4B pipelines over saved pages. Supports `--url`, `--domain`, `--crawl-id`, `--limit`. |
| **Full markdown storage** | `markdown` column stores full cleaned text (no 500-char truncation). Schema migration preserves existing data. |
| **Multi-entrypoint wiring** | FastAPI, interactive CLI, direct CLI all support `enrich_mode` selection. Settings reloaded in-process for direct CLI. |
| **Phase 4B test verification** | 45 tests across 3 rounds. Unit, integration, and regression coverage for all pipelines. |

### v4.2.1 (Previous Release)

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

### Phase 4C — API Layer & Multi-Tenancy
- **FastAPI REST server** — `python -m nexora_crawler.api --server` with 21 routes (legacy + Phase 4C)
- **JWT authentication** — `X-Workspace-Id` dev bypass gated by `NEXORA_AUTH_BYPASS_ENABLED=false` by default
- **Vector search** — `/v1/search/semantic`, `/v1/search/hybrid`, `/v1/search/by-source/{source_type}/{source_id}/similar`
- **Webhooks** — CRUD endpoints with secret management at `/v1/webhooks`
- **Generic job submission** — `/v1/jobs` with status polling at `/v1/jobs/{id}`
- **GDPR compliance** — `DELETE /v1/gdpr/erase` (Article 17 right to erasure)
- **Schema-driven extraction** — `POST /v1/extract/schema` for Firecrawl-style structured extraction
- **Health checks** — `/health` and `/health/detailed`
- **Workspace isolation** — `workspace_id` column on all tables; 429 existing rows backfilled to `'default'`
- **6 new tables** — `webhooks`, `webhook_deliveries`, `workspace_quotas`, `usage_records`, `audit_logs`, `extraction_schemas`
- **Async DB layer** — `aiosqlite` (dev) / `asyncpg` (prod) with unified `NEXORA_METADATA_DB` path
- **CORS middleware** — Origins configurable via `NEXORA_CORS_ORIGINS`

### Phase 4B — AI Enrichment & Vector Indexing
- **On-demand enrichment** — Crawl is decoupled from AI. Default `on_demand` mode saves cleaned markdown only. Run `enrich.py` later to generate summaries, tags, and vectors.
- **AI summary + tags** — LLM-generated per page (LiteLLM against the HF router)
- **Embeddings** — sentence-transformers vectors via the HF router's legacy `feature-extraction` endpoint (the OpenAI-compatible `/v1/embeddings` does **not** support ST models)
- **Structural chunking** — Markdown split at heading/paragraph boundaries with overlap (~512 tokens)
- **Per-chunk embeddings** — Each chunk gets its own embedding via `embed_batch()` (replaces inherited page-level embedding)
- **Circuit breaker** — After N consecutive AI failures, calls are skipped for the rest of the run to prevent timeout drains
- **Provider fallback** — Optional secondary provider (e.g. local Ollama) takes over when primary quota is exhausted
- **Vector store** — Chroma (local) or pgvector/Supabase (production), behind one interface
- **Provider-agnostic** — switch embedding model, AI provider, or vector backend via settings only
- **Tested end-to-end** — 45-test verification suite (39 PASS) + 14-step debug campaign (Steps 1–14 complete)

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

### Phase 4C — API Surface

```
                          ┌─────────────────┐
                          │  FastAPI Server │
                          └────────┬────────┘
                                   │
          ┌────────────┬────────────┼────────────┬────────────┐
          ▼            ▼            ▼            ▼            ▼
       /health    /v1/search    /v1/webhooks   /v1/jobs   /v1/gdpr
       /strategies  /semantic   /{id}          /types     /erase
                    /hybrid      POST/GET/DELETE  POST     /extract
                    /by-source   ...                      /schema
                    /similar
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
│   │   ├── requirements.txt
│   │   └── release_notes_v4.6.0.md         ★ Phase 4C remediation
│   ├── Crawler/                            Scrapy project with Phases 1-4C
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
│   │       │   └── factory.py                   build_vector_store() + async singleton
│   │       ├── storage/                          ★ Phase 4A storage layer
│   │       │   ├── base.py                       Abstract interfaces
│   │       │   ├── models.py                     Unified schema dataclass
│   │       │   └── local_sqlite.py               SQLite implementation + Phase 4C tables
│   │       ├── spiders/
│   │       │   └── nexora_spider.py
│   │       ├── api/                              ★ Phase 4C: FastAPI package
│   │       │   ├── __init__.py                   FastAPI app + CLI entrypoint
│   │       │   ├── __main__.py                   `python -m nexora_crawler.api`
│   │       │   ├── auth.py                       JWT + workspace isolation
│   │       │   ├── database/
│   │       │   │   ├── __init__.py
│   │       │   │   └── connection.py             Async DB (aiosqlite / asyncpg)
│   │       │   └── routes/
│   │       │       ├── __init__.py
│   │       │       ├── search.py                 Vector search endpoints
│   │       │       ├── webhooks.py               Webhook CRUD
│   │       │       ├── jobs.py                   Generic job submission + status
│   │       │       ├── gdpr.py                   GDPR erase
│   │       │       ├── extract.py                Schema-driven extraction
│   │       │       └── health.py                 Health checks
│   │       ├── jobs/                             ★ Phase 4C: job registry
│   │       │   ├── __init__.py
│   │       │   └── registry.py                   5 built-in job types
│   │       ├── tasks/                            ★ Phase 4C: simplified dispatcher
│   │       │   ├── __init__.py
│   │       │   └── dispatcher.py                 In-process job dispatch (no Celery)
│   │       ├── items.py               Updated with Phase 4A/4B fields
│   │       ├── settings.py            Updated with Phase 4A/4B/4C priorities
│   │       └── sitemap_detector.py
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

#### On-Demand Mode (Default)
Crawls are fast — no AI calls. Just fetch, clean, and save:
```powershell
cd "Nexora application/Crawler"
scrapy crawl nexora -a urls="https://example.com"
```

Later, enrich saved pages offline:
```powershell
cd "Nexora application/Crawler"
python enrich.py                      # enrich all unenriched pages
python enrich.py --domain example.com
python enrich.py --limit 50
```

#### Eager Mode (Inline Enrichment)
For immediate AI enrichment during the crawl:
```powershell
# Via env var
set NEXORA_ENRICH_MODE=eager
scrapy crawl nexora -a urls="https://example.com"

# Via direct CLI
python -m nexora_crawler.api --url https://example.com --enrich-mode eager

# Via FastAPI
curl -X POST http://localhost:8000/crawl \
  -H 'Content-Type: application/json' \
  -d '{"url": "https://example.com", "strategy": "single-page", "enrich_mode": "eager"}'
```

#### Verify the AI + Vector Stack
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
| `NEXORA_ENRICH_MODE` | `on_demand` | `"on_demand"` (fast, no AI) \| `"eager"` (inline enrichment) |
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
| `NEXORA_AI_FAILFAST_THRESHOLD` | `3` | Consecutive AI failures before breaker opens (0 = disabled) |
| `NEXORA_AI_FALLBACK_PROVIDER` | `""` | Secondary provider when primary breaker opens (empty = no fallback) |
| `NEXORA_AI_FALLBACK_MODEL` | `""` | Secondary provider model |
| `NEXORA_AI_FALLBACK_BASE_URL` | `""` | Secondary provider base URL (empty = no fallback) |
| `NEXORA_AI_FALLBACK_API_KEY` | `""` | Secondary provider API key |
| `NEXORA_AI_FALLBACK_API_KEY` | `""` | Secondary provider API key |

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

# Phase 4B — Comprehensive verification (45-test suite)
python -m pytest outputs/audit/audit_round3_step3_2.py -v
python -m pytest outputs/audit/audit_round3_step3_3.py -v
```

Full test results: `outputs/audit/NEXORA_PHASE4B_TEST_SUMMARY.md`

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
| **4B** | ✅ Complete + Tested (v4.5.0) | AI enrichment, embeddings, chunking, vector indexing. 14-step debug campaign (Steps 1–14) fixed all P0/P1 runtime bugs. Provider fallback added. Open items (crawl_id + resource blocking) resolved and verified. |
| **4C** | ✅ Complete + Hardened (v4.6.0) | API layer, JWT auth, workspace isolation, webhooks, jobs, GDPR, schema extraction. All S1/S2 defects from independent gap analysis resolved. |
| **5** | 📋 Planned | Distributed crawling, shared profile cache |
| **6** | 📋 Planned | Tauri desktop application |
| **7** | 📋 Planned | Hybrid search, list_all for migration tooling |

---

## Known Limitations (v4.6.0)

- **Phase 4C test suite** — No `test_phase4c*.py` exists yet. Minimum useful set: migration against populated DB, write-then-read per route, unauthenticated 401, job submission asserting real work.
- **Job handler implementations** — All 5 registered job types return 501. Real `handler_cls` implementations pending.
- **Full re-validation matrix not yet re-run** — Tests 06/07/08 need full-scale re-runs with working AI provider + Playwright active (deferred per operator).
- **Chunk size overshoot** — avg ≈ 680 tokens/chunk vs 512 target (overlap-driven; tracked as nice-to-have).

### Resolved in v4.6.0

- ~~Database migration crash on pre-existing DBs~~ — `_migrate_schema()` hoisted before DDL; lifespan auto-migration hook added.
- ~~All Phase 4C writes rolled back silently~~ — Explicit `await db.commit()` added to all mutating async routes.
- ~~Tenant isolation bypass via unauthenticated X-Workspace-Id~~ — JWT-first auth; dev bypass gated behind `NEXORA_AUTH_BYPASS_ENABLED=false`.
- ~~Vector store HTTP 500 on search/GDPR routes~~ — All routes use `await get_vector_store()` async singleton.
- ~~Subprocess spawns referenced deleted api.py~~ — Both paths now spawn `python -m nexora_crawler.api`.
- ~~Job stubs returned fake "completed" status~~ — Stubs return HTTP 501; `GET /v1/jobs/{id}` added; async tasks tracked.
- ~~Dead settings (CORS origins, API workers, version strings)~~ — Wired to env/config.

### Resolved in v4.5.0

- ~~`crawl_id` not populated~~ — `api.py` now generates a UUID per crawl and passes it to the spider; every SQLite row has a non-empty `crawl_id`.
- ~~`PLAYWRIGHT_BLOCKED_RESOURCE_TYPES` not wired~~ — Route-level abort callback blocks image/font/media/ping requests before they reach the network.

### Resolved in v4.4.0

- ~~Page-level embeddings inherited by chunks~~ — Per-chunk embeddings via `embed_batch()` in `StructuralChunkingPipeline`.
- ~~`__skip` KeyError on duplicates~~ — `DropItem` used instead; 124 items lost in QA run → 0.
- ~~MarkdownPipeline srcset `2x` crash~~ — `_descriptor_weight()` + `_safe_dimension()` handle all srcset/dimension edge cases.
- ~~robots.txt silently blocked~~ — `_INFRA_PATH_RE` pass-through; robots rules now enforced.
- ~~Parquet empty-struct export failure~~ — Catch-all JSON-stringify prevents unwritable `struct<>` inference.
- ~~Eager-mode pipeline-drain hang~~ — Circuit breaker opens after 3 consecutive AI failures.
- ~~Split-brain metadata DB~~ — `_anchored_path()` resolves relative paths against settings file directory.
- ~~`enrich.py` missing helpers~~ — `_build_crawler()`, `_collect_targets()`, `_enrich_row()` implemented.
- ~~`enrich.py --limit` None crash~~ — `_limit_clause()` omits LIMIT when `None`; filter + cap compose correctly.
- ~~`_enrich_row` reads `ai_tags` vs DB column `ai_tags_json`~~ — Deserializes from DB column; write-back preserves existing data.
- ~~`token_count` float from `//4.5`~~ — `_estimate_tokens()` always returns `int`.
- ~~`build_vector_store()` fallback defaults diverge~~ — `_cfg()` resolver chains env → settings → default.
- ~~Provider fallback architecture~~ — Circuit breaker routes to secondary provider when primary is exhausted.
- ~~Action-link crawl hygiene~~ — Path patterns + query param blocking for state-changing endpoints.
- ~~Test 02 fixture refreshed~~ — Dead Firebase URL replaced with live deployment.
- ~~Playwright wiring (4 sub-defects)~~ — Handler deduplication, text-density fix, txt/xml exclusion, dupefilter bypass for PW retry.
- ~~Anti-bot stealth leak~~ — Prototype-level `webdriver` patch + full `window.chrome` object.
- ~~ExponentialBackoff retries IgnoreRequest~~ — `IgnoreRequest` early-exit in `process_exception`.
- ~~Playwright shutdown noise~~ — Silenced `Event loop is closed` / `Task was destroyed` messages.
- ~~No early exit on max-pages cap~~ — `CloseSpider` raises immediately when cap is hit.
- ~~Playwright timeout too short~~ — `PLAYWRIGHT_DEFAULT_NAVIGATION_TIMEOUT` 30s → 60s.
- ~~Sitemap discovery misses redirected paths~~ — Pre-discovery redirect resolution in `SitemapDetector.discover()`.
- ~~BLOCKED_PATH_PATTERNS incomplete~~ — Added `BLOCKED_PATH_SEGMENTS` set for path-segment filtering.

---

## License

MIT License — see [LICENSE](LICENSE) for details.

---

<p align="center">
  <strong>NEXUS AURORA v4.6.0</strong> — Intelligent website intelligence for ML, RAG, and competitive analysis.
</p>

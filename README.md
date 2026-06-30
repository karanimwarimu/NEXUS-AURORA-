# NEXUS AURORA v4.1.0

> AI-powered website intelligence platform with static-first routing, browser-aware extraction, multi-format storage engine, and hardened crawl safety for production-grade web intelligence workflows.

[![Version](https://img.shields.io/badge/version-4.1.0-blue)]()
[![Python](https://img.shields.io/badge/python-3.11+-green)]()
[![License](https://img.shields.io/badge/license-MIT-lightgrey)]()
[![Status](https://img.shields.io/badge/status-phase%204A%20storage-brightgreen)]()

---

## Table of Contents

- [Overview](#overview)
- [What's New in v4.1.0](#whats-new-in-v410)
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
  - [Benchmark Suite](#benchmark-suite)
- [Crawl Strategies](#crawl-strategies)
- [Output Format](#output-format)
- [Configuration](#configuration)
- [Testing](#testing)
- [Development Roadmap](#development-roadmap)
- [Known Limitations](#known-limitations)
- [License](#license)

---

## Overview

**NEXUS AURORA** (codename: **Nexora**) is a Python web intelligence pipeline with an intelligent **static-first routing engine** and a **multi-format storage infrastructure**. It probes each URL via lightweight HTTP, decides if JavaScript rendering is needed using 8 detection signals, routes accordingly — saving 150-300MB RAM per page for static sites — then transforms raw HTML into clean, structured, multi-format outputs for human analysts, ML pipelines, and RAG systems.

> **Current Phase: 4A (v4.1.0)** — Storage & Multi-Format Ingestion Engine with Markdown extraction, multimodal asset isolation, unified schema enforcement, SQLite metadata indexing, and compressed Parquet export.

---

## What's New in v4.1.0

| Feature | Description |
|---------|-------------|
| **MarkdownExtractionPipeline** | Scrapy pipeline (Priority 110) converting raw HTML to clean, LLM-ready Markdown via Trafilatura with >50% token reduction |
| **MultimodalAssetExtractor** | Isolates images and videos from HTML with structured metadata (src, alt, dimensions, hero detection, embed platform) |
| **UnifiedSchemaEnricher** | Scrapy pipeline (Priority 160) enforcing the NexoraRecord schema with defaults, website_type classification (e-commerce, blog, docs, article, unknown) |
| **MetadataIndexerPipeline** | Scrapy pipeline (Priority 165) persisting items to SQLite MetadataStore |
| **ParquetExportPipeline** | Scrapy pipeline (Priority 450) buffering and flushing compressed Apache Parquet files (snappy/gzip/zstd/brotli) |
| **SQLite MetadataStore** | Relational storage with `pages` and `crawl_jobs` tables, indexed by domain, crawl_id, website_type, timestamp, language |
| **Unified Schema Dataclass** | `NexoraRecord` — canonical data shape with typed sub-classes (EntityExtraction, QualityScores, StyleAnalysis) |
| **Phase 4A Test Suite** | 18 automated tests covering all 12 specification test cases (100% pass rate) |
| **One Crawl → Multiple Formats** | Raw HTML → Markdown + JSON/CSV + Parquet + SQLite from a single crawl job |

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

### Phase 4A — Multi-Format Storage Engine (NEW)
- **Markdown extraction** — HTML → clean Markdown with >50% token reduction
- **Multimodal asset isolation** — Structured metadata for images and videos (no binary download)
- **Unified schema** — Every record has entities, style_analysis, quality_scores with guaranteed defaults
- **Website classification** — Automatic e-commerce, blog, documentation, article, or unknown detection
- **SQLite metadata store** — Fast relational storage indexed by domain, crawl_id, website_type, language
- **Parquet export** — Columnar, compressed storage for ML pipelines (snappy compression, < 30% of equivalent JSON)
- **One crawl → multiple formats** — Markdown + JSON + CSV + Parquet + SQLite from a single pass

### Benchmarking
- **50-site benchmark** across 8 categories with confusion matrix
- **Per-category accuracy metrics**
- **18-test Phase 4A suite** covering all storage components

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
               │  │                                  │ │
               │  │ [110] → MarkdownExtraction       │ │
               │  │       + MultimodalAssetExtractor │ │
               │  │ [150] → NexoraStylePipeline      │ │
               │  │ [160] → UnifiedSchemaEnricher    │ │
               │  │ [165] → MetadataIndexerPipeline  │ │
               │  │ [250] → Phase 4B pipelines       │ │
               │  │ [450] → ParquetExportPipeline    │ │
               │  └──────────────────────────────────┘ │
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
            ┌────────────┬────────────┬────────────┐
            ▼            ▼            ▼            ▼
         Markdown    JSON/CSV    Parquet      SQLite
         (LLM)      (Inspect)   (ML/BI)     (Metadata)
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
│   ├── requirements.txt
│   ├── Crawler/                            Scrapy project with Phases 1-4A
│   │   └── nexora_crawler/
│   │       ├── middlewares/
│   │       │   ├── dynamic_detection.py          ★ Phase 3 core engine
│   │       │   ├── exponential_backoff.py
│   │       │   └── playwright_cleanup.py
│   │       ├── pipelines/                        ★ Phase 4A modular pipelines
│   │       │   ├── __init__.py                   Phase 1-3 pipelines
│   │       │   ├── markdown_pipeline.py          ★ Phase 4A
│   │       │   ├── schema_enricher.py            ★ Phase 4A
│   │       │   ├── metadata_indexer.py           ★ Phase 4A
│   │       │   └── parquet_export.py             ★ Phase 4A
│   │       ├── storage/                          ★ Phase 4A storage layer
│   │       │   ├── base.py                       Abstract interfaces
│   │       │   ├── models.py                     Unified schema dataclass
│   │       │   └── local_sqlite.py               SQLite implementation
│   │       ├── spiders/
│   │       │   └── nexora_spider.py
│   │       ├── api.py                 FastAPI + interactive CLI
│   │       ├── items.py               Updated with Phase 4A fields
│   │       ├── settings.py            Updated with Phase 4A priorities
│   │       └── sitemap_detector.py
│   ├── Extractor/
│   │   ├── multimodal_extractor.py                ★ Phase 4A
│   │   └── ...
│   ├── Models/
│   │   └── lid.176.ftz
│   ├── output/
│   │   ├── audit/                                 Test reports & benchmarks
│   │   │   ├── phase3_*.md
│   │   │   └── phase4a_test1_report.md            ★ Phase 4A
│   │   ├── parquet/                               ★ Phase 4A Parquet exports
│   │   ├── pages/
│   │   └── master_dataset.csv
│   ├── tests/
│   │   ├── test_phase4a.py                        ★ 18-test Phase 4A suite
│   │   ├── test_phase3_*.py
│   │   └── ...
│   └── release_notes_v4.1.0.md
├── data/
│   ├── test_profiles.db
│   └── nexora_metadata.db                         ★ Phase 4A auto-created DB
└── Project Tools/
```

For full details, see [REPOSITORY_STRUCTURE.md](REPOSITORY_STRUCTURE.md).

---

## Installation

### Prerequisites
- Python 3.11 or later
- pip

### Install Dependencies
```powershell
cd "Nexora application"
pip install -r requirements.txt
```

### Install Playwright (for JS rendering)
```powershell
pip install scrapy-playwright playwright
playwright install chromium
set NEXORA_PLAYWRIGHT_ENABLED=1
```

### Install Phase 4A Dependencies
```powershell
pip install pandas pyarrow
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

To verify the Phase 4A pipeline is working:
```powershell
cd "Nexora application/tests"
python -m pytest test_phase4a.py -v
```

### Benchmark Suite
```powershell
# Quick validation (4 tests, ~10 sites)
cd "Nexora application"
python tests/real_site_test_phase3.py

# Full 50-site benchmark (~4 minutes, rate-limited)
python tests/real_site_benchmark_phase3.py

# Phase 4A storage engine tests (18 tests)
python -m pytest tests/test_phase4a.py -v
```

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
├── parquet/                               ← NEW Phase 4A
│   └── nexora_20260630_190925_0000.parquet
data/
└── nexora_metadata.db                     ← NEW Phase 4A
```

### Phase 4A Fields (Added to Existing)

| Field | Type | Description |
|-------|------|-------------|
| `markdown` | str | Clean Markdown content (Trafilatura) |
| `extraction_method` | str | trafilatura / fallback / error |
| `token_reduction_pct` | float | % of tokens reduced vs raw HTML |
| `image_assets` | list[dict] | Structured image metadata (src, alt, dimensions, hero) |
| `video_assets` | list[dict] | Structured video metadata (src, poster, platform) |
| `crawl_id` | str | UUID of crawl job |
| `entities` | dict | Prices, currency, tickers, products, people |
| `style_analysis` | dict | Colors, tech_stack, framework, theme, fonts |
| `quality_scores` | dict | Readability, duplication, text_density, crawl_quality |
| `website_type` | str | e-commerce, blog, docs, article, unknown |

---

## Configuration

Key settings in `Crawler/nexora_crawler/settings.py`:

| Setting | Default | Purpose |
|---------|---------|---------|
| `NEXORA_PLAYWRIGHT_ENABLED` | `True` | Enable Playwright for JS pages |
| `NEXORA_STEALTH_ENABLED` | `True` | Apply bot-detection evasion |
| `NEXORA_MARKDOWN_ENABLED` | `True` | Enable HTML → Markdown conversion |
| `NEXORA_PARQUET_ENABLED` | `True` | Enable compressed Parquet export |
| `NEXORA_PARQUET_COMPRESSION` | `snappy` | Parquet compression: snappy/gzip/zstd/brotli |
| `NEXORA_PARQUET_ROW_GROUP_SIZE` | `10000` | Rows per Parquet row group |
| `NEXORA_PARQUET_OUTPUT` | `./output/parquet` | Parquet output directory |
| `NEXORA_METADATA_DB` | `./data/nexora_metadata.db` | SQLite metadata database path |
| `ROBOTSTXT_OBEY` | `True` | Respect robots.txt |
| `DOWNLOAD_DELAY` | `1.5` | Base delay between requests (seconds) |
| `AUTOTHROTTLE_ENABLED` | `True` | Adapt delay to server response time |

---

## Testing

```powershell
cd "Nexora application"

# Phase 3 — Live-site validation
python tests/real_site_test_phase3.py

# Phase 3 — 50-site benchmark (~4 min)
python tests/real_site_benchmark_phase3.py

# Phase 3 — Unit + integration
pytest tests/test_phase3_component.py -v
pytest tests/test_phase3_integration.py -v

# Phase 4A — Storage engine (18 tests)
python -m pytest tests/test_phase4a.py -v

# Phase 4A — Filter by test case
python -m pytest tests/test_phase4a.py -v -k "P4A-T01 or P4A-T10"
```

---

## Development Roadmap

| Phase | Status | Scope |
|-------|--------|-------|
| **1** | ✅ Complete | Single-page extraction CLI |
| **2 / 2.5** | ✅ Complete | Multi-page Scrapy crawler + style extraction |
| **2.6** | ✅ Complete | FastAPI REST API + interactive CLI + sitemap discovery |
| **3** | ✅ Complete (3.4) | DynamicDetectionMiddleware with 8-signal engine, 85-90% accuracy |
| **4A** | ✅ Complete (v4.1.0) | Storage & Multi-Format Ingestion Engine (Markdown, multimodal, unified schema, SQLite, Parquet) |
| **4B** | 🔜 Next | AI enrichment, LLM summarization, embeddings, RAG chunking |
| **5** | 📋 Planned | Distributed crawling, shared profile cache |
| **6** | 📋 Planned | Tauri desktop application |

---

## Known Limitations (v4.1.0)

- **Network-dependent** — ~12% of sites may timeout; these correctly fallback to Playwright but add latency
- **Angular production builds** — `ng-version=` attribute is removed; detection relies on bundle patterns
- **No auth** — FastAPI endpoints are open; job store is in-memory only
- **Some heavy SPAs** — TikTok relies on script ratio (>0.35) rather than framework markers
- **Phase 4B not yet implemented** — AI enrichment, embeddings, and RAG chunking are placeholders only
- **Parquet requires pandas+pyarrow** — must be installed separately

---

## License

MIT License — see [LICENSE](LICENSE) for details.

---

<p align="center">
  <strong>NEXUS AURORA v4.1.0</strong> — Intelligent website intelligence for ML, RAG, and competitive analysis.
</p>
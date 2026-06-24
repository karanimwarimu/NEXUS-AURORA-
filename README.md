# NEXUS AURORA v2.6

> AI-powered website intelligence platform that crawls, analyzes, and extracts structured knowledge, technologies, styles, and datasets from websites — built for machine learning, RAG, and competitive intelligence.

[![Version](https://img.shields.io/badge/version-2.6-blue)]()
[![Python](https://img.shields.io/badge/python-3.11+-green)]()
[![License](https://img.shields.io/badge/license-MIT-lightgrey)]()

---

## Table of Contents

- [Overview](#overview)
- [What's New in v2.6](#whats-new-in-v26)
- [Features](#features)
- [Architecture](#architecture)
- [Project Structure](#project-structure)
- [Installation](#installation)
- [Usage](#usage)
  - [Phase 1 — Single Page Extraction](#phase-1--single-page-extraction)
  - [Phase 2 — Scrapy Crawler](#phase-2--scrapy-crawler)
  - [Phase 2.6 — Interactive CLI](#phase-26--interactive-cli)
  - [Phase 2.6 — FastAPI REST API](#phase-26--fastapi-rest-api)
  - [Phase 5 — Streamlit Dashboard](#phase-5--streamlit-dashboard)
- [Crawl Strategies](#crawl-strategies)
- [Output Format](#output-format)
- [Data Schema](#data-schema)
- [Configuration](#configuration)
- [Development Roadmap](#development-roadmap)
- [Known Limitations](#known-limitations)
- [License](#license)

---

## Overview

**NEXUS AURORA** (internal codename: **Nexora**) is a Python web intelligence pipeline. It fetches web pages, extracts clean article text and structural metadata, enriches pages with semantic data (Schema.org, Open Graph, Twitter Cards), detects visual design signals (CSS frameworks, themes, fonts, colors), deduplicates content via SimHash fingerprints, and exports everything as JSON/CSV datasets.

There is **no React/Vue frontend yet** — v2.6 exposes the crawler through a **Scrapy CLI**, an **interactive terminal CLI**, a **FastAPI REST API**, and a **Streamlit dashboard**. Storage is **file-based** (no database).

---

## What's New in v2.6

| Feature | Description |
|---------|-------------|
| **FastAPI REST API** | Start crawls via HTTP, poll job status, list strategies |
| **Interactive CLI** | Terminal prompts for URL, strategy, and page cap |
| **Streamlit dashboard** | Web UI for starting crawls and viewing results |
| **Crawl strategies** | User-friendly presets: single-page, linked-pages, whole-website, everything |
| **Sitemap auto-discovery** | Async `SitemapDetector` finds sitemaps via robots.txt and common paths |
| **Style intelligence** | CSS framework, dark/light theme, fonts, colors, layout detection |
| **Semantic enrichment** | JSON-LD, microdata, RDFa, Open Graph, Twitter Cards, canonical relations |
| **Content deduplication** | SimHash fingerprints skip near-duplicate pages during a crawl |
| **Language detection** | FastText-based ISO-639-1 classification (optional model) |
| **Responsible crawling** | robots.txt compliance, throttling, AutoThrottle, content-type filtering |
| **Phase 3 Playwright (opt-in)** | Headless browser rendering for JS-heavy pages via `NEXORA_PLAYWRIGHT=1` |

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

### Crawling

- Four depth strategies with safety caps (`max_pages`)
- Sitemap index recursion
- Domain locking for deep crawls
- User-Agent rotation
- Blocks non-HTML content and sensitive paths (`/login`, `/admin/`, etc.)
- HTTP cache for faster development re-runs
- Optional Playwright rendering for JavaScript-heavy SPAs

### Export

- Per-page JSON (full data including raw HTML)
- Per-page CSV (flattened row)
- Master dataset CSV (one summary row per page)

---

## Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                        ENTRY POINTS                             │
├──────────┬──────────┬──────────┬──────────┬───────────────────────┤
│ Streamlit│ Interactive│ FastAPI │ scrapy  │ Extractor/main.py   │
│ Dashboard│ CLI        │ REST    │ crawl   │ (Phase 1)           │
└────┬─────┴─────┬──────┴────┬─────┴────┬────┴──────────┬──────────┘
     │           │           │          │               │
     └───────────┴───────────┴──────────┴───────────────┘
                               │
┌──────────────────────────────▼──────────────────────────────────┐
│                   SCRAPY CRAWLER (Phase 2)                      │
│  NexoraSpider → Middlewares → Pipeline Chain                    │
└──────────────────────────────┬──────────────────────────────────┘
                               │
┌──────────────────────────────▼──────────────────────────────────┐
│              EXTRACTION LAYER (Phase 1 modules)                   │
│  BS4 │ Trafilatura │ Parser │ Style │ Cleaner                     │
└──────────────────────────────┬────────────────────────────────────┘
                               │
┌──────────────────────────────▼──────────────────────────────────┐
│                    FILE STORAGE                                   │
│  output/pages/*.json │ *.csv │ master_dataset.csv                 │
└───────────────────────────────────────────────────────────────────┘
```

### Pipeline Chain

| Order | Pipeline | Role |
|-------|----------|------|
| 100 | `NexoraExtractionPipeline` | BS4 + Trafilatura + semantic parsers + fingerprint + language |
| 150 | `NexoraStylePipeline` | CSS framework, theme, fonts, colors, layout |
| 200 | `NexoraExportPipeline` | Save per-page JSON + CSV to `output/pages/` |
| 300 | `NexoraDatasetPipeline` | Append row to `output/master_dataset.csv` |

### Tech Stack

| Layer | Technology |
|-------|------------|
| Crawling | Scrapy 2.11 |
| HTTP (Phase 1) | requests |
| HTTP (API / sitemap) | httpx |
| HTML parsing | BeautifulSoup4, lxml |
| Article extraction | Trafilatura |
| Dedup | simhash |
| Language | fasttext-wheel (optional) |
| API | FastAPI, uvicorn, pydantic |
| Dashboard | Streamlit |
| JS rendering (opt-in) | scrapy-playwright, Playwright |
| Output | JSON, CSV |

---

## Project Structure

```
NEXUS AURORA/
├── README.md                          ← this file
├── LICENSE                            MIT license
│
├── Nexora application/                ← canonical application source (use this)
│   ├── requirements.txt
│   ├── Extractor/                     Phase 1 — single-page extraction
│   │   ├── main.py                    CLI entry point
│   │   ├── Web_fetcher.py
│   │   ├── Beautifulsoup_extractor.py
│   │   ├── Trafilatura_extractor.py
│   │   ├── parser.py                  JSON-LD, OG, Twitter, assets
│   │   ├── cleaner.py                 SimHash + language detection
│   │   ├── style_extractor.py         CSS/design intelligence
│   │   ├── sitemap_parser.py
│   │   └── Save_web_exctract.py
│   │
│   ├── Crawler/                       Phase 2 / 2.6 — Scrapy project
│   │   ├── scrapy.cfg
│   │   ├── run_nexora.py              Cache-bypass Scrapy runner
│   │   └── nexora_crawler/
│   │       ├── api.py                 FastAPI + interactive CLI
│   │       ├── settings.py            Scrapy configuration
│   │       ├── items.py               NexoraPageItem schema
│   │       ├── pipelines.py           4-stage pipeline chain
│   │       ├── middlewares.py         UA rotation, content filtering, Playwright
│   │       ├── sitemap_detector.py    Async sitemap discovery
│   │       └── spiders/
│   │           └── nexora_spider.py   Main crawl spider
│   │
│   ├── dashboard/
│   │   └── app.py                     Streamlit UI (Phase 5)
│   │
│   └── tests/
│       └── test_nexora_phase26.py     Phase 2.6 test suite
│
├── nexora app v2/                     Legacy working copy with sample output
│   └── Nexora application/            Prefer canonical copy above
│
└── Project Tools/                     Architecture specs and phase roadmaps
```

> **Which copy to use?** Always use `Nexora application/` at the repo root. The `nexora app v2/` folder is a legacy snapshot with sample BBC crawl output; it lacks Phase 2.6 API and sitemap files.

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

### Optional: Playwright (Phase 3 JS rendering)

```powershell
pip install scrapy-playwright playwright
playwright install chromium
set NEXORA_PLAYWRIGHT=1
```

### Optional: Language Detection Model

Download the FastText model to:

```
Nexora application/Extractor/lid.176.ftz
```

Language detection falls back gracefully if the model is absent.

---

## Usage

### Phase 1 — Single Page Extraction

```powershell
cd "Nexora application/Extractor"
python main.py https://example.com
```

Output: `Nexora application/output/<domain>.json` and `.csv`

---

### Phase 2 — Scrapy Crawler

```powershell
cd "Nexora application/Crawler"

# Single page only
scrapy crawl nexora -a urls="https://example.com"

# Linked pages (depth 1)
scrapy crawl nexora -a urls="https://example.com" -a strategy="linked-pages"

# Whole website (sitemap auto-discovery)
scrapy crawl nexora -a urls="https://example.com" -a strategy="whole-website"

# Cache-bypass runner (clears __pycache__ before crawl)
python run_nexora.py -a urls="https://example.com" -a strategy="whole-website"
```

---

### Phase 2.6 — Interactive CLI

```powershell
cd "Nexora application/Crawler"
python -m nexora_crawler.api
```

---

### Phase 2.6 — FastAPI REST API

```powershell
cd "Nexora application/Crawler"
python -m nexora_crawler.api --server

# Or directly with uvicorn
uvicorn nexora_crawler.api:app --reload --port 8000
```

API docs: `http://localhost:8000/docs`

#### Endpoints

| Method | Path | Description |
|--------|------|-------------|
| `GET` | `/` | Service info and available strategies |
| `GET` | `/strategies` | Strategy list with descriptions |
| `POST` | `/crawl` | Start a new crawl job |
| `GET` | `/crawl/{job_id}` | Poll job status |
| `GET` | `/jobs` | List all jobs |

#### Example

```bash
curl -X POST http://localhost:8000/crawl \
  -H "Content-Type: application/json" \
  -d '{"url": "https://www.bbc.com", "strategy": "whole-website", "max_pages": 100}'
```

---

### Phase 5 — Streamlit Dashboard

Start the API server first, then launch the dashboard:

```powershell
# Terminal 1 — API
cd "Nexora application/Crawler"
uvicorn nexora_crawler.api:app --port 8000

# Terminal 2 — Dashboard
cd "Nexora application"
streamlit run dashboard/app.py
```

Open `http://localhost:8501` to start crawls, monitor progress, and browse results.

---

## Crawl Strategies

| Strategy | Depth | Mode | Description |
|----------|-------|------|-------------|
| `single-page` | 0 | single-page | Process only the seed URL |
| `linked-pages` | 1 | multi-page | Seed URL + all pages it directly links to |
| `whole-website` | 3 | auto | Auto-detect sitemap; fallback to depth-3 link crawl |
| `everything` | 5 | multi-page | Deep domain crawl (depth 5), locked to seed domain |

All strategies respect the `max_pages` safety cap (default: 1000, max: 50000).

---

## Output Format

```
output/
├── pages/
│   ├── example.com__about__20250624T143022.json
│   └── example.com__about__20250624T143022.csv
└── master_dataset.csv
```

### Key Output Fields

| Field | Description |
|-------|-------------|
| `url` | Final resolved URL |
| `title` | Page title |
| `clean_text` | Reader-mode article text |
| `fingerprint` | SimHash near-duplicate signature |
| `language_iso` | ISO-639-1 language code |
| `structured_schema` | JSON-LD / microdata / RDFa payloads |
| `social_graphs` | Open Graph + Twitter Card values |
| `styles` | CSS framework, theme, fonts, colors, layout |
| `html` | Raw HTML (included in JSON exports) |

---

## Data Schema

All crawled pages flow through `NexoraPageItem` in `Crawler/nexora_crawler/items.py` — 30+ fields covering spider metadata, extraction results, intelligence enrichments, style data, and export paths.

---

## Configuration

Key settings in `Crawler/nexora_crawler/settings.py`:

| Setting | Default | Purpose |
|---------|---------|---------|
| `ROBOTSTXT_OBEY` | `True` | Respect robots.txt |
| `DOWNLOAD_DELAY` | `1.5` | Base delay between requests (seconds) |
| `CONCURRENT_REQUESTS_PER_DOMAIN` | `1` | One request at a time per domain |
| `AUTOTHROTTLE_ENABLED` | `True` | Adapt delay to server response time |
| `DEPTH_LIMIT` | `0` | Hard ceiling (overridden per-run via spider args) |
| `HTTPCACHE_ENABLED` | `True` | Cache responses during development |

**Playwright:** Set environment variable `NEXORA_PLAYWRIGHT=1` to enable headless browser rendering for JS-heavy pages.

---

## Testing

```powershell
cd "Nexora application"
pytest tests/test_nexora_phase26.py -v

# Fast unit tests only
pytest tests/test_nexora_phase26.py -v -k "not real"

# Real HTTP tests (requires internet)
pytest tests/test_nexora_phase26.py -v -k "real" -m slow
```

---

## Development Roadmap

| Phase | Status | Scope |
|-------|--------|-------|
| **1** | Complete | Single-page extraction CLI |
| **2 / 2.5** | Complete | Multi-page Scrapy crawler + style extraction |
| **2.6** | Complete | FastAPI REST + interactive CLI + sitemap auto-discovery |
| **3** | Opt-in | Playwright headless browser for JS/SPA sites |
| **4** | Planned | AI summarization, embeddings, RAG pipeline |
| **5** | Partial | Streamlit dashboard (v2.6); React UI planned |

---

## Known Limitations (v2.6)

- **No authentication** — FastAPI endpoints are open; job store is in-memory only
- **No persistent job storage** — Jobs are lost on server restart
- **Playwright is opt-in** — Requires separate install and `NEXORA_PLAYWRIGHT=1`
- **Legacy copy** — `nexora app v2/` is a snapshot; use canonical `Nexora application/`

---

## License

MIT License — see [LICENSE](LICENSE) for details.

---

<p align="center">
  <strong>NEXUS AURORA v2.6</strong> — Website intelligence for ML, RAG, and competitive analysis.
</p>

# NEXUS AURORA v3b v0.4.0

> AI-powered website intelligence platform with static-first routing, browser-aware extraction, and hardened crawl safety for production-grade web intelligence workflows.

[![Version](https://img.shields.io/badge/version-3b%20v0.4.0-blue)]()
[![Python](https://img.shields.io/badge/python-3.11+-green)]()
[![License](https://img.shields.io/badge/license-MIT-lightgrey)]()
[![Status](https://img.shields.io/badge/status-phase%203b%20hardening-brightgreen)]()

---

## Table of Contents

- [Overview](#overview)
- [What's New in v3b v0.4.0](#whats-new-in-v3b-v040)
- [Features](#features)
- [Architecture](#architecture)
- [Dynamic Detection Engine](#dynamic-detection-engine)
- [Project Structure](#project-structure)
- [Installation](#installation)
- [Usage](#usage)
  - [Phase 1 — Single Page Extraction](#phase-1--single-page-extraction)
  - [Phase 2 — Scrapy Crawler](#phase-2--scrapy-crawler)
  - [Phase 2.6 — Interactive CLI & API](#phase-26--interactive-cli--api)
  - [Phase 3 — Dynamic Detection Middleware](#phase-3--dynamic-detection-middleware)
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

**NEXUS AURORA** (codename: **Nexora**) is a Python web intelligence pipeline with an intelligent **static-first routing engine**. It probes each URL via lightweight HTTP, decides if JavaScript rendering is needed using 8 detection signals, and routes accordingly — saving 150-300MB RAM per page for static sites while ensuring JS-heavy SPAs get full browser rendering.

> **Current Phase: 3.4** — Dynamic Detection Middleware with 85-90% accuracy on 50 real websites across 8 categories.

---

## What's New in v3b v0.4.0

| Feature | Description |
|---------|-------------|
| **DynamicDetectionMiddleware** | Scrapy middleware (Priority 542) that auto-routes between static HTTP and Playwright JS rendering |
| **8-Signal Decision Engine** | Framework markers, script ratio, text density, body length, anti-bot, SPA mount points, bundle patterns, error fallback |
| **SPA Mount Point Detection** | Detects `<div id="root">`, `<div id="__next">`, `<div id="app">` etc. for framework-agnostic SPA detection |
| **Anti-Bot Detection on HTTP 200** | Catches Cloudflare/DataDome stealth challenges that return 200 status |
| **JS Bundle Pattern Detection** | Vite/Webpack hashed asset patterns (`/assets/name.8chars.js`) |
| **SQLite Profile Cache** | 24-hour TTL caching prevents redundant probes per domain |
| **50-Site Benchmark Suite** | Automated validation across static, server, react, vue, angular, svelte, antibot, and spa categories |
| **Release v3b v0.4.0** | Full release notes in `Nexora application/output/release_notes_v3b_v0.4.0.md` |

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

### Benchmarking
- **50-site benchmark** across 8 categories with confusion matrix
- **Per-category accuracy metrics**
- **Quick validation script** for rapid testing

---

## Architecture

### High-Level Pipeline

```
                        ┌─────────────────┐
                        │  Incoming URL    │
                        └────────┬────────┘
                                 │
                                 ▼
              ┌──────────────────────────────────┐
              │   DYNAMIC DETECTION MIDDLEWARE    │
              │   (Priority 542 — Scrapy)         │
              │                                    │
              │   ┌──────────┐  ┌──────────┐     │
              │   │ Cache    │─▶│ Probe    │     │
              │   │ Check    │  │ (httpx)  │     │
              │   └──────────┘  └────┬─────┘     │
              │                      ▼            │
              │              ┌──────────────┐    │
              │              │ 8-Signal     │    │
              │              │ Decision     │    │
              │              └──────┬───────┘    │
              └─────────────────────┼────────────┘
                                    │
                    ┌───────────────┴───────────────┐
                    │                               │
                    ▼                               ▼
        ┌────────────────────┐         ┌────────────────────┐
        │  STATIC HTTP ROUTE  │         │ PLAYWRIGHT ROUTE   │
        │  httpx (0 MB RAM)   │         │ Chromium (150-300MB)│
        └────────┬───────────┘         └────────┬───────────┘
                 │                              │
                 └──────────────┬──────────────┘
                                │
                                ▼
              ┌──────────────────────────────────┐
              │       EXTRACTOR PIPELINE          │
              │  Sitemap → Parser → Cleaner → CSV │
              └──────────────────────────────────┘
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
├── Nexora application/            ← Main application source
│   ├── requirements.txt
│   ├── Crawler/                   Scrapy project with Phase 3 middleware
│   │   └── nexora_crawler/
│   │       ├── middlewares/
│   │       │   ├── dynamic_detection.py    ★ Phase 3 core engine
│   │       │   └── playwright_cleanup.py
│   │       ├── spiders/
│   │       │   └── nexora_spider.py
│   │       ├── api.py             FastAPI + interactive CLI
│   │       ├── settings.py
│   │       ├── pipelines.py
│   │       └── sitemap_detector.py
│   ├── Extractor/                 Phase 1 — single-page extraction
│   ├── Models/
│   │   └── lid.176.ftz            Language detection model
│   ├── output/
│   │   ├── audit/                 ★ Benchmark reports & architecture docs
│   │   ├── pages/                 Crawled page exports
│   │   └── master_dataset.csv
│   ├── tests/
│   │   ├── real_site_benchmark_phase3.py   ★ 50-site benchmark
│   │   ├── real_site_test_phase3.py        ★ Quick validation
│   │   └── test_phase3_*.py
│   └── release_notes_v3b_v0.4.0.md
├── data/
│   └── test_profiles.db           SQLite site profile cache
└── Project Tools/                 Specs and roadmaps
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

The middleware:
1. Probes each URL via HTTP (httpx)
2. Decides if JS rendering is needed (8 signals)
3. Caches the decision in SQLite (24-hour TTL)
4. Routes to Playwright only for JS-required pages

### Benchmark Suite
```powershell
# Quick validation (4 tests, ~10 sites)
cd "Nexora application"
python tests/real_site_test_phase3.py

# Full 50-site benchmark (~4 minutes, rate-limited)
python tests/real_site_benchmark_phase3.py
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
│   └── example.com__about__20250624T143022.csv
└── master_dataset.csv
```

### Key Fields
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

## Configuration

Key settings in `Crawler/nexora_crawler/settings.py`:

| Setting | Default | Purpose |
|---------|---------|---------|
| `NEXORA_PLAYWRIGHT_ENABLED` | `True` | Enable Playwright for JS pages |
| `NEXORA_STEALTH_ENABLED` | `True` | Apply bot-detection evasion |
| `NEXORA_SITE_PROFILE_DB` | `data/site_profiles.db` | Profile cache path |
| `ROBOTSTXT_OBEY` | `True` | Respect robots.txt |
| `DOWNLOAD_DELAY` | `1.5` | Base delay between requests (seconds) |
| `AUTOTHROTTLE_ENABLED` | `True` | Adapt delay to server response time |
| `HTTPCACHE_ENABLED` | `True` | Cache responses during development |

---

## Testing

```powershell
cd "Nexora application"

# Quick live-site validation (4 tests)
python tests/real_site_test_phase3.py

# Full 50-site benchmark (~4 min)
python tests/real_site_benchmark_phase3.py

# Unit tests
pytest tests/test_phase3_component.py -v
pytest tests/test_phase3_integration.py -v
```

---

## Development Roadmap

| Phase | Status | Scope |
|-------|--------|-------|
| **1** | ✅ Complete | Single-page extraction CLI |
| **2 / 2.5** | ✅ Complete | Multi-page Scrapy crawler + style extraction |
| **2.6** | ✅ Complete | FastAPI REST API + interactive CLI + sitemap discovery |
| **3** | ✅ Complete (3.4) | DynamicDetectionMiddleware with 8-signal engine, 85-90% accuracy |
| **3b** | 🔜 Next | Data storage pipeline + LLM integration |
| **4** | 📋 Planned | AI summarization, embeddings, RAG pipeline |
| **5** | 📋 Planned | Distributed crawling, shared profile cache |
| **6** | 📋 Planned | Tauri desktop application |

---

## Known Limitations (v3.4)

- **Network-dependent** — ~12% of sites may timeout; these correctly fallback to Playwright but add latency
- **Angular production builds** — `ng-version=` attribute is removed; detection relies on bundle patterns
- **No auth** — FastAPI endpoints are open; job store is in-memory only
- **Some heavy SPAs** — TikTok relies on script ratio (>0.35) rather than framework markers
- **Legacy copy** — `nexora app v2/` is a snapshot; use canonical `Nexora application/`

---

## License

MIT License — see [LICENSE](LICENSE) for details.

---

<p align="center">
  <strong>NEXUS AURORA v3.4.0</strong> — Intelligent website intelligence for ML, RAG, and competitive analysis.
</p>
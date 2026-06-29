Here is a comprehensive documentation draft summarizing the architecture, file modifications, and behavioral enhancements introduced in **Phase 2.6** of the NexoraCrawler application.

---

# 📝 Engineering Change Documentation: Phase 2.6 Implementation

**Project:** NexoraCrawler Application

**Version Scope:** Migration from Core Scrapy Framework to Hybrid Async API/CLI Framework

**Status:** Implementation Complete

---

## 1. Executive Summary

Phase 2.6 transitions the `nexoraspider` from a strict, terminal-bound Scrapy command-line tool into a flexible, production-ready backend application. This release introduces two primary layers:

1. **An Intelligent Control Plane:** Automatically determines optimal crawling depth and aggressively looks for sitemaps (`sitemap.xml`) to optimize data collection.
2. **A Dual-Interface Layer:** Wraps the crawler in both an interactive CLI for developers and a robust FastAPI web server for upcoming UI integrations (Phase 4).

---

## 2. Architectural Evolution

The architecture has decoupled the runtime engine from Scrapy's command line, shifting orchestration responsibilities to an asynchronous FastAPI wrapper.

```
┌─────────────────┐     ┌──────────────────┐     ┌─────────────────┐
│   User Input    │────▶│   FastAPI / CLI  │────▶│  NexoraSpider   │
│  (URL + Strategy)│     │   (api.py)       │     │  (nexora_spider)│
└─────────────────┘     └──────────────────┘     └────────┬────────┘
                                                          │
                              ┌───────────────────────────┼──────────┐
                              ▼                           ▼          ▼
                    ┌─────────────────┐          ┌──────────────┐  ┌─────────────┐
                    │ SitemapDetector │          │ Sitemap Mode │  │ Link-Follow │
                    │ (sitemap_detector)│        │ (parse_sitemap)│  │ (parse_page) │
                    └─────────────────┘          └──────────────┘  └─────────────┘
                                                          │
                                                          ▼
                                               ┌──────────────────┐
                                               │ ITEM_PIPELINES   │
                                               │ 100 Extraction   │
                                               │ 150 Style        │
                                               │ 200 Export       │
                                               │ 300 Dataset      │
                                               └──────────────────┘

```

### Key Workflow Changes:

* **The Interception Layer:** When a request hits `api.py`, it does not immediately boot Scrapy. It runs an asynchronous pre-flight check to verify URL reachability and evaluate crawl strategy parameters.
* **Asynchronous Offloading:** Crawls are treated as backgrounds tasks via `asyncio.create_task()`, allowing the client API to remain perfectly responsive while tracking job states in-memory.

---

## 3. File Inventory and Modifications

The code changes are concentrated into **three completely new or heavily refactored modules**, while core engine pipelines remain unchanged to prevent regression bugs.

| File Path | Status | Lines | Functional Impact |
| --- | --- | --- | --- |
| `api.py` | **NEW** | 250 | Acts as a dual-boot entry point. Spawns a high-performance **FastAPI** REST engine or an **Interactive ASCII CLI** depending on execution flags. |
| `sitemap_detector.py` | **NEW** | 175 | Lightweight, highly specialized module running on `httpx` to locate, stream, and un-gzip remote `sitemap.xml` records without blocking thread execution. |
| `spiders/nexora_spider.py` | **UPDATED** | 280 | Refactored internal spider initialization to interpret abstract strategic names (`whole-website`) into structural constraints (`depth`, `domain_lock`). |
| `items.py` | Unchanged | 80 | Retains data normalization schemas (including `status` tags). |
| `middlewares.py` | Unchanged | 140 | Backward compatible; async signatures verified. |
| `pipelines.py` | Unchanged | 290 | Confirmed item pipelines (Extraction $\rightarrow$ Style $\rightarrow$ Export $\rightarrow$ Dataset) process flawlessly without explicit spider argument bindings. |
| `settings.py` | Unchanged | 120 | System settings and global request delays are preserved. |

---

## 4. Advanced Crawl Strategy & Intelligent Mapping

The core value of this phase is abstracting technical settings (`depth`, `sitemap modes`) into high-level user intents.

### Strategy Lookup Reference

| User Menu Selection | `strategy` Parameter | Internal Engine Mode | Max Depth | Auto Sitemap Discovery | Domain Boundaries Lock |
| --- | --- | --- | --- | --- | --- |
| **1. Just this page** | `single-page` | `single-page` | `0` | ❌ | ❌ |
| **2. This page + linked pages** | `linked-pages` | `multi-page` | `1` | ❌ | ❌ |
| **3. The whole website** | `whole-website` | `auto` (Sitemap or Link Fallback) | `3` |  | ❌ |
| **4. Everything connected** | `everything` | `multi-page` | `5` | ❌ |  |

### Focus: Strategy 3 ("Whole Website") Execution Flow

When `whole-website` is engaged, NexoraCrawler runs an adaptive automation sequence:

1. **Robots Audit:** Reads `robots.txt` from the seed target to extract explicit `Sitemap:` declarations.
2. **Brute Force Scans:** If undetected, performs concurrent `HEAD` requests to common paths (`/sitemap.xml`, `/sitemap_index.xml`, `/wp-sitemap.xml`).
3. **Execution Fork:**
* **Sitemap Found:** Bypasses normal structural spidering, parses all target paths extracted from the XML file, and loads them sequentially.
* **Sitemap Miss:** Gracefully falls back to normal multi-page link-following restricted to a ceiling of `depth=3`.



---

## 5. Interface & Execution Guide

### Interface A: Interactive CLI (Local Development)

Launched by executing the module wrapper directly, this mode bypasses web dependencies to run validation testing inside a standard terminal:

```bash
python -m nexora_crawler.api

```

*Provides sequential prompt gates to specify the Target URL, interactive Strategy Index (1-4), and an absolute safety cap for maximum page allocations.*

### Interface B: FastAPI REST Engine (Programmatic Integration)

To launch the headless API instance capable of handling automated integrations:

```bash
python -m nexora_crawler.api --server
# OR
uvicorn nexora_crawler.api:app --reload --port 8000

```

#### Main Endpoints Available:

* `GET  /strategies` — Returns the mapping dictionary containing active strategy parameters.
* `POST /crawl` — Submits a crawl task payload. Returns a tracked `job_id`.
* `GET  /crawl/{job_id}` — Inspects in-memory dictionaries for real-time logs, execution states, and scraped counts.
* `GET  /jobs` — Comprehensive history log of past and ongoing tasks.

---

## 6. Deployment Dependencies & Pre-flight Steps

To prevent runtime errors (specifically directory locks or caching mismatches commonly found on Windows platforms), execute the following initialization tasks:

```powershell
# Step 1: Install explicit asynchronous and validation requirements
pip install httpx fastapi uvicorn pydantic

# Step 2: Flush stale bytecode compilation artifacts (CRITICAL)
Get-ChildItem -Recurse -Filter __pycache__ | Remove-Item -Recurse -Force
Get-ChildItem -Recurse -Filter *.pyc | Remove-Item -Force

```

---

## 7. Strategic Map Roadmap

Phase 2.6 establishes a predictable, isolated environment for your scrapers. This paves the way for upcoming development milestones:

* 🟩 **Phase 2.6 (Current):** Async Discovery Engine, Strategy Middleware, and REST Wrapper.
* 🟦 **Phase 3 (Next):** Playwright integration to support JavaScript-heavy target rendering.
* 🟦 **Phase 4:** Dedicated single-page frontend application (React/Vue) leveraging the Phase 2.6 endpoint ecosystem.

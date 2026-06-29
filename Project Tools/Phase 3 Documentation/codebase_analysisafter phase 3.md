# NEXUS AURORA — Deep Codebase Architecture Analysis
> Senior Software Engineering Review | June 2026

---

## 1. Project Identity & Mission

**NEXUS AURORA** (runtime codename: **Nexora**) is a Python-based **web intelligence pipeline**. Its job: crawl any website, decide intelligently whether raw HTTP or a full Chromium browser is needed, extract every meaningful signal from the page (text, semantic data, visual design, social metadata), and output structured datasets ready for ML, RAG pipelines, and competitive analysis.

Current status: **Phase 3.4 complete** (85–90% benchmark accuracy across 50 real sites). Phase 4 (AI enrichment + RAG) is the active next frontier.

---

## 2. Repository Structure

```
NEXUS AURORA/
├── Nexora application/           ← THE CODEBASE
│   ├── Crawler/                  ← Scrapy project (Phase 2+)
│   │   └── nexora_crawler/
│   │       ├── middlewares/
│   │       │   ├── __init__.py           (UA rotation, content filter, spider MW)
│   │       │   ├── dynamic_detection.py  ★ PHASE 3 CORE ENGINE
│   │       │   └── playwright_cleanup.py (memory leak prevention)
│   │       ├── spiders/
│   │       │   └── nexora_spider.py      ★ MAIN SPIDER
│   │       ├── storage/
│   │       │   ├── base.py               (abstract storage interfaces — Phase 4A)
│   │       │   └── models.py             (NexoraRecord, NexoraChunk dataclasses)
│   │       ├── api.py                    (FastAPI + interactive CLI)
│   │       ├── items.py                  (Scrapy Item contract)
│   │       ├── pipelines.py              ★ 4-STAGE PIPELINE
│   │       ├── settings.py               (Scrapy + Playwright config)
│   │       └── sitemap_detector.py       (async sitemap discovery)
│   ├── Extractor/                ← Phase 1 + shared extraction library
│   │   ├── main.py               (Phase 1 single-page CLI)
│   │   ├── Beautifulsoup_extractor.py   (structural metadata)
│   │   ├── Trafilatura_extractor.py     (clean article text)
│   │   ├── parser.py                    (JSON-LD, OG, Twitter, RDFa, images)
│   │   ├── style_extractor.py           (CSS framework, theme, fonts, colors)
│   │   └── cleaner.py                   (SimHash fingerprint, FastText language)
│   ├── Models/
│   │   └── lid.176.ftz          (FastText 176-lang model, optional)
│   ├── tests/                   (4-tier test pyramid)
│   └── output/                  (per-page JSON/CSV + master_dataset.csv)
└── Project Tools/               (specs, roadmaps, docs)
```

---

## 3. The Full Data Flow (End-to-End)

```
User invokes CLI / API
        │
        ▼
  ┌─────────────────────┐
  │   api.py / CLI      │   ← 3 entry modes: interactive, direct, FastAPI
  └────────┬────────────┘
           │  CrawlerProcess.crawl("nexora", url, strategy, max_pages)
           ▼
  ┌─────────────────────┐
  │   NexoraSpider      │   ← Resolves strategy → mode/depth/sitemap
  └────────┬────────────┘
           │  yields scrapy.Request(url)
           ▼
  ┌─────────────────────────────────────────────────────┐
  │              DOWNLOADER MIDDLEWARE CHAIN             │
  │  [50]  NexoraUserAgentMiddleware  → rotates UA       │
  │  [510] ContentTypeFilterMiddleware → blocks assets   │
  │  [542] DynamicDetectionMiddleware  ★ ROUTING BRAIN  │
  │        ├── Check SQLite profile cache (24h TTL)      │
  │        ├── If miss: httpx.GET(url) → 8-signal check  │
  │        └── → annotates request with playwright=True  │
  │  [543] ScrapyPlaywrightDownloadHandler (if needed)   │
  │  [550] PlaywrightCleanupMiddleware → closes pages    │
  └────────────────────────────────┬────────────────────┘
                                   │ HTML response
                                   ▼
  ┌─────────────────────┐
  │  parse_page()       │   ← Yields NexoraPageItem with raw HTML
  └────────┬────────────┘
           │
           ▼
  ┌─────────────────────────────────────────────────────┐
  │                 ITEM PIPELINE CHAIN                  │
  │  [100] NexoraExtractionPipeline                     │
  │        ├── BS4: title, meta, headings, images, links │
  │        ├── Trafilatura: clean_text, author, date     │
  │        ├── SimHash fingerprint → deduplication       │
  │        ├── FastText → language detection             │
  │        └── JSON-LD, OG, Twitter, RDFa, image assets │
  │  [150] NexoraStylePipeline                          │
  │        └── CSS framework, theme, fonts, colors,      │
  │            layout, animations                        │
  │  [200] NexoraExportPipeline                         │
  │        └── per-page .json + .csv → output/pages/    │
  │  [300] NexoraDatasetPipeline                        │
  │        └── append row → output/master_dataset.csv   │
  └─────────────────────────────────────────────────────┘
```

---

## 4. Component Deep-Dives

### 4.1 `DynamicDetectionMiddleware` — The Brain (Priority 542)

This is the most architecturally significant component. It implements an **8-signal static analysis decision tree** to route each URL to either plain HTTP or Chromium/Playwright, before the actual crawl download happens.

**Decision flow per URL:**
```
1. Is Playwright globally disabled? → skip (static only)
2. Is this a non-HTML asset (.jpg, .css, .js)? → skip
3. User override via meta["playwright"] True/False? → honor it
4. SQLite cache hit (same domain, within 24h TTL)? → use cached decision
5. If no cache: httpx.GET(url) → analyze HTML response:

   Signal 1: HTTP 403/429/503 + anti-bot patterns → Playwright
   Signal 2: HTTP 200 + stealth challenge markers → Playwright
   Signal 3: body < 200 chars AND script ratio > 0.15 → Playwright
   Signal 4: text_density < 0.05 AND body < 5000 chars → Playwright
   Signal 5: JS framework pattern match (7 frameworks) → Playwright
   Signal 6: SPA mount point (<div id="root">) + scripts → Playwright
   Signal 7: Hashed bundle patterns (Vite/Webpack) → Playwright
   Signal 8: script tag ratio > 0.35 → Playwright
   Fallback: Exception during probe → Playwright (safe default)

6. Cache decision in SQLite + in-memory dict
7. Apply: if needs_js → annotate request meta with playwright=True
```

**Architecture insight:** The middleware's genius is that it makes this routing decision on a **pre-probe** of the HTML — not the actual Scrapy download. It uses `httpx.AsyncClient` (not Scrapy) for the probe, keeping the two fetches orthogonal. The 24-hour SQLite TTL cache means subsequent pages of the same domain are served instantly from cache.

**Stealth engine:** When routing to Playwright, it injects a JavaScript anti-detection patch into the page context:
- `navigator.webdriver` → `undefined`
- `chrome.runtime` → present (mimics real Chrome)
- `navigator.plugins` → realistic Chrome PDF plugins
- `navigator.mimeTypes` → realistic MIME types
- `permissions.query` → safe notifications-only response
- WebGL vendor → "Intel Inc." / "Intel Iris Xe Graphics"

---

### 4.2 `NexoraSpider` — The Crawler

Supports 4 strategies, resolved at spider init time:

| Strategy | Mode | Depth | Auto Sitemap | Domain Lock |
|---|---|---|---|---|
| `single-page` | single-page | 0 | ❌ | ❌ |
| `linked-pages` | multi-page | 1 | ❌ | ❌ |
| `whole-website` | auto | 3 | ✅ | ❌ |
| `everything` | multi-page | 5 | ❌ | ✅ |

The `whole-website` strategy is the most complex — it first attempts async sitemap discovery via `SitemapDetector`, and only falls back to depth-3 link-following if no sitemap is found.

**Key behaviors:**
- `pages_crawled` counter with a configurable `max_pages` hard cap (default 1000, max 50000)
- Domain lock for `everything` strategy — never follows off-domain links
- `playwright_used` flag propagated from `response.meta` to the item
- Scrapy 2.16+ async-native: `async def start()` (not `start_requests`)

---

### 4.3 `SitemapDetector` — Async Discovery

An async context manager that:
1. Fetches `/robots.txt` and extracts `Sitemap:` directives
2. If none found, probes 9 common sitemap paths via HEAD requests
3. Handles sitemap indexes (recursion) and gzipped sitemaps
4. Namespace-agnostic XML parsing (strips `{}namespace` prefix)

---

### 4.4 The Extraction Library (`Extractor/`)

All extractors are **pure functions** (no I/O) operating on raw HTML strings. They're used by both Phase 1 (direct CLI) and Phase 2+ (via pipeline).

| Module | What it extracts |
|---|---|
| `Beautifulsoup_extractor.py` | Title, meta tags, headings (h1/h2/h3), images, internal links, raw word count |
| `Trafilatura_extractor.py` | Clean article text (reader-mode), author, date, language, sitename, tags |
| `parser.py` | JSON-LD, Microdata, RDFa, Open Graph, Twitter Cards, canonical/AMP/pagination links, rich image assets (srcset, loading, dimensions) |
| `style_extractor.py` | CSS framework (9 frameworks), dark/light theme (3 strategies), fonts (CSS + Google Fonts), colors (regex on CSS), layout (flex/grid/float/table), animations |
| `cleaner.py` | SimHash fingerprint (near-duplicate detection), FastText language detection (176 langs, lazy-loaded) |

**Dual-extraction pattern:** The pipeline merges BS4 data + Trafilatura data with a simple `{**bs4, **traf}` merge, where Trafilatura values win on conflicts (it's the higher-quality reader-mode extractor).

---

### 4.5 The 4-Stage Pipeline

```
[100] Extraction  →  [150] Styles  →  [200] Export  →  [300] Dataset
```

**Key design decisions:**
- All pipelines use `async def process_item()` — Scrapy 2.16+ async-native
- `__skip` sentinel flag: any pipeline can set `item["__skip"] = True` and all subsequent pipelines honor it (deduplication short-circuit)
- SimHash deduplication: an in-memory set of seen fingerprints, with a 50,000-entry cap (cleared to prevent unbounded memory)
- `NexoraDatasetPipeline` appends to `master_dataset.csv` with `f.flush()` after every row (ensures crash durability)
- Canonical URL override: if `graph_relations["canonical_url"]` exists, it overwrites `item["url"]`

---

### 4.6 `api.py` — Three Modes in One File

| Mode | How to trigger | Use case |
|---|---|---|
| Interactive CLI | `python -m nexora_crawler.api` | Human operator, prompts for URL/strategy |
| Direct CLI | `python -m nexora_crawler.api --url ... --strategy ...` | Scripting/automation |
| FastAPI server | `python -m nexora_crawler.api --server` | REST API, background jobs via `asyncio.create_task()` |

**Architecture note:** The FastAPI job store is `_jobs: dict[str, CrawlResponse]` — pure in-memory. This is flagged in the codebase itself as "replace with Redis/DB in production."

---

### 4.7 Storage Layer — Phase 4A Foundation

The `storage/` package is a forward-looking abstraction built for Phase 4:

- `base.py`: Two abstract base classes — `BaseMetadataStore` (relational) and `BaseVectorStore` (semantic search)
- `models.py`: Three dataclasses:
  - `NexoraRecord` — the enriched page record, full pipeline output
  - `NexoraChunk` — an LLM-ready text chunk derived from a record (RAG unit)
  - Supporting: `EntityExtraction`, `QualityScores`, `StyleAnalysis`

`NexoraChunk.to_llm_context()` formats a chunk as a structured RAG prompt injection with source URL, title, section heading chain, summary, and tags.

---

## 5. Middleware Priority Map

```
Priority  Middleware
──────────────────────────────────────────────────
    50    NexoraUserAgentMiddleware     → rotates User-Agent per request
   510    ContentTypeFilterMiddleware   → blocks assets, allows sitemap XML, filters non-HTML
   542    DynamicDetectionMiddleware    ★ static vs. Playwright routing decision
   543    ScrapyPlaywrightDownloadHandler → executes JS rendering if annotated
   550    PlaywrightCleanupMiddleware   → closes Playwright page objects (memory safety)
──────────────────────────────────────────────────
Spider middleware:
   543    NexoraSpiderMiddleware        → lifecycle + async output pass-through
```

The ordering is deliberate: DynamicDetection (542) runs *before* Playwright handler (543), so it can annotate requests with `playwright=True` before they're processed by the download handler.

---

## 6. Configuration Architecture

All Scrapy settings live in `settings.py` with explanatory comments for every value. Key toggles:

| Setting | Default | Effect |
|---|---|---|
| `NEXORA_PLAYWRIGHT_ENABLED` | `True` | Master switch — disables all JS routing |
| `NEXORA_STEALTH_ENABLED` | `True` | Injects JS anti-detection patches |
| `NEXORA_SITE_PROFILE_DB` | `data/site_profiles.db` | SQLite profile cache path |
| `DEPTH_LIMIT` | `0` | Scrapy-level hard ceiling for crawler depth |
| `DOWNLOAD_DELAY` | `1.5s` | Base request delay (doubled randomly) |
| `AUTOTHROTTLE_ENABLED` | `True` | Adapts delay to server response time |
| `CONCURRENT_REQUESTS_PER_DOMAIN` | `1` | Polite: one request at a time |
| `ROBOTSTXT_OBEY` | `True` | Respects robots.txt |

---

## 7. Data Contracts

### `NexoraPageItem` (Scrapy Item — runtime contract)
The item that flows through spider → pipeline. Key field groups:
- **Spider-set:** `url, status, html, depth, spider_name, crawled_at, playwright_used`
- **Extraction-set (by pipeline 100):** `title, description, headings, images, internal_links, clean_text, word_count_*, fingerprint, language_iso, structured_schema, social_graphs, graph_relations, image_assets`
- **Style-set (by pipeline 150):** `styles` dict
- **Pipeline bookkeeping:** `saved_json, saved_csv, __skip` flag
- **Phase 4 reserved:** `screenshot_path, render_time_ms`

### `NexoraRecord` (Phase 4A dataclass — storage contract)
The enriched record for persistence and LLM pipelines. Always has defaults — no field is ever `None`. Has `from_scrapy_item()` class method to convert from Scrapy pipeline items. Has `to_enriched_dict()` for canonical export format.

---

## 8. Dependency Stack

| Layer | Libraries |
|---|---|
| **Crawling** | Scrapy 2.11, scrapy-playwright, Playwright (Chromium) |
| **HTTP** | httpx (async, HTTP/2, used for probing) |
| **HTML parsing** | BeautifulSoup4 (lxml backend), parsel |
| **Content extraction** | Trafilatura (reader-mode), extruct (semantic schemas) |
| **Deduplication** | simhash |
| **Language detection** | fasttext (176-lang lid model, optional) |
| **API** | FastAPI, Pydantic, uvicorn |
| **Storage** | SQLite (profile cache, site profiles), CSV, JSON |
| **Testing** | pytest, pytest-asyncio |

---

## 9. Test Architecture (4-Tier Pyramid)

| Tier | File | Scope |
|---|---|---|
| Unit | `test_phase3_unit_and_vulns.py` | Signal functions, regex patterns, edge cases |
| Component | `test_phase3_component.py` | Middleware in isolation with mocks |
| Integration | `test_phase3_integration.py` | Middleware + spider together |
| Live benchmark | `real_site_benchmark_phase3.py` | 50 real sites, 8 categories, confusion matrix |
| Quick validation | `real_site_test_phase3.py` | 4 tests, ~10 sites, fast feedback |

---

## 10. Known Gaps & Technical Debt

| Area | Issue | Severity |
|---|---|---|
| **API job store** | In-memory `_jobs` dict — lost on restart | Medium |
| **Authentication** | FastAPI endpoints are completely open | Medium |
| **Scrapy version mismatch** | `requirements.txt` pins `scrapy==2.11.1` but code uses `async def start()` which is Scrapy 2.13+/2.16+ | High ⚠️ |
| **Playwright detection** | Angular production builds strip `ng-version=` — relies on bundle hash fallback | Low |
| **Network dependency** | ~12% of sites timeout during probe, correctly falling back to Playwright but adding latency | Low |
| **Phase 4 not implemented** | `storage/base.py` and `models.py` define the Phase 4A contracts but no concrete implementations exist yet | Pending |
| **`routing_reason` field missing** | Phase 3 spec calls for a `routing_reason` field in items, but it isn't in `items.py` | Minor |
| **Duplicate STRATEGY_MAP** | Defined in both `nexora_spider.py` and `api.py` — should be a shared constant | Minor |
| **Crawler TODO list** | `Crawler/TODO.md` and `Crawler/TODO_REVIEW_PLAN.md` exist — indicates known backlog |Pending |

---

## 11. Development Roadmap (Current State)

```
Phase 1  ✅  Single-page extraction CLI
Phase 2  ✅  Multi-page Scrapy crawler + style extraction
Phase 2.5✅  CSS framework, theme, font extraction
Phase 2.6✅  FastAPI REST API + interactive CLI + sitemap discovery
Phase 3  ✅  DynamicDetectionMiddleware (8-signal engine, 85-90% accuracy)
─────────────────────────────── CURRENT BOUNDARY ────────────────────────────
Phase 3b 🔜  Data storage pipeline + LLM integration (contracts defined in storage/)
Phase 4  📋  AI summarization, embeddings, RAG pipeline
Phase 5  📋  Distributed crawling, shared profile cache
Phase 6  📋  Tauri desktop application
```

---

## 12. Architectural Strengths

1. **Static-first doctrine** — Playwright is a controlled exception, not the default. Saves 150–300MB RAM per static page.
2. **Explainability** — every routing decision is logged with a specific reason string.
3. **Cache-first** — SQLite profile cache with 24h TTL prevents redundant probing of known domains.
4. **Separation of concerns** — `Extractor/` library is completely independent of Scrapy. Can be used standalone (Phase 1) or via pipeline (Phase 2+).
5. **Graceful degradation** — FastText model missing? Falls back to `("en", 0.0)`. SimHash missing? Falls back to deterministic hash. Probe fails? Falls back to Playwright.
6. **Forward-compatible storage layer** — `base.py` ABCs allow swapping SQLite → PostgreSQL → Supabase without touching pipelines.
7. **Async-native** — Scrapy 2.16+ async signatures throughout, Twisted + asyncio reactor for Playwright compatibility.

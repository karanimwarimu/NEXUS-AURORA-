# Nexora — AI Website Intelligence Engine
## Project Skeleton & Continuity Document
> Paste this at the start of a new chat to restore full context instantly.

---

## What Nexora Is

A modular, ML-portfolio-ready AI Website Intelligence Engine built in Python.
It scrapes, extracts, and structures web content into clean datasets for downstream
ML, LLM, and AI use cases.

**Core philosophy:**
- Each phase is independently runnable
- No phase modifies another phase's code
- Every component has one job
- Output is always structured JSON + CSV ready for pandas/ML

---

## Current Build Status

| Phase | Status | Description |
|---|---|---|
| Phase 1 | ✅ Complete | Single-page scraper + extraction layer |
| Phase 2 | ✅ Built, ready to test | Scrapy multi-page crawler hooked to Phase 1 |
| Phase 3 | 🔵 Stubbed | Playwright for JS/SPA sites — hooks already wired |
| Phase 4 | ⬜ Not started | AI layer (summarisation, classification, embeddings) |
| Phase 5 | ⬜ Not started | Streamlit dashboard + dataset browser |

---

## Full Project Structure

```
nexora/
├── extractor/                        ← PHASE 1 (never modified by later phases)
│   ├── __init__.py                   ← exports main, fetch_html, extract_with_bs4, extract_with_trafilatura
│   └── basic_extractor.py            ← monolithic Phase 1 (user is modularizing this)
│
│   [User's modularized version — update this section when shared]:
│   ├── fetcher.py                    ← fetch_html()
│   ├── parser.py                     ← extract_with_bs4()
│   ├── cleaner.py                    ← extract_with_trafilatura()
│   ├── saver.py                      ← save_json(), save_csv()
│   └── main.py                       ← orchestrator + CLI entry point
│
├── crawler/                          ← PHASE 2 (Scrapy engine)
│   ├── scrapy.cfg                    ← project root anchor for scrapy CLI
│   └── nexora_crawler/
│       ├── __init__.py
│       ├── items.py                  ← NexoraPageItem (typed data contract)
│       ├── middlewares.py            ← User-Agent rotation + Phase 3 Playwright stub
│       ├── pipelines.py              ← 3-stage processing chain
│       ├── settings.py               ← all crawl behaviour (delays, depth, robots.txt)
│       └── spiders/
│           ├── __init__.py
│           └── nexora_spider.py      ← multi-page crawler with Phase 3 hooks
│
├── output/                           ← generated automatically on first run
│   ├── pages/                        ← one JSON + CSV per crawled page
│   │   ├── <domain>__<path>__<timestamp>.json
│   │   └── <domain>__<path>__<timestamp>.csv
│   └── master_dataset.csv            ← one row per page, entire crawl history
│
├── docs/
│   ├── web_scraping_ai_workflow.md   ← original workflow reference
│   ├── phase2_crawler.md             ← Phase 2 architecture + usage
│   └── skeleton.md                   ← THIS FILE
│
└── requirements.txt
```

---

## Phase 1 — Extractor Detail

**Entry point (dev/debug):**
```bash
python extractor/basic_extractor.py https://example.com
# or after modularization:
python extractor/main.py https://example.com
```

**Core functions and what calls them:**

| Function | File | Called by |
|---|---|---|
| `fetch_html(url)` | `fetcher.py` | Phase 1 CLI only — Scrapy has its own fetcher |
| `extract_with_bs4(html, url)` | `parser.py` | Phase 1 CLI + Phase 2 pipeline (100) |
| `extract_with_trafilatura(html, url)` | `cleaner.py` | Phase 1 CLI + Phase 2 pipeline (100) |
| `save_json()` / `save_csv()` | `saver.py` | Phase 1 CLI only — Phase 2 has NexoraExportPipeline |
| `main(url)` | `main.py` | Phase 1 CLI only |

**Output fields per page:**

| Field | Source | Notes |
|---|---|---|
| `title` | BS4 | `<title>` tag |
| `description` | BS4 | meta description / og:description |
| `keywords` | BS4 | meta keywords |
| `meta_tags` | BS4 | all meta name/property → content dict |
| `headings` | BS4 | `{h1: [...], h2: [...], h3: [...]}` |
| `images` | BS4 | `[{src, alt, width, height}]` — absolute URLs |
| `internal_links` | BS4 | `[{url, text}]` — same domain only |
| `word_count_raw` | BS4 | total words in raw page text |
| `clean_text` | Trafilatura | boilerplate-stripped article text |
| `word_count_clean` | Trafilatura | words in clean text |
| `author` | Trafilatura | article author |
| `date` | Trafilatura | publication date |
| `language` | Trafilatura | detected language |
| `response_time_ms` | requests | server latency |

**Known behaviour:**
- JS-heavy sites (YouTube, Twitter, React SPAs) return near-empty results in Phase 1
  — this is expected and correct. Phase 3 (Playwright) fixes this.
- `fetch_html()` uses a rotating User-Agent header and 15s timeout
- All relative image/link URLs resolved to absolute via `urljoin`

---

## Phase 2 — Scrapy Crawler Detail

**Entry point:**
```bash
cd nexora/crawler                          # MUST be in this directory
scrapy crawl nexora -a urls="https://example.com" -a depth=1
```

**How the flow works:**
```
scrapy.cfg
  → settings.py (loads config)
    → nexora_spider.py (builds Requests, follows links)
      → middlewares.py (rotates User-Agent on every request)
        → [Internet fetch]
          → nexora_spider.py parse() (wraps HTML into NexoraPageItem)
            → Pipeline 100: NexoraExtractionPipeline  (calls Phase 1 functions)
            → Pipeline 200: NexoraExportPipeline       (saves per-page JSON + CSV)
            → Pipeline 300: NexoraDatasetPipeline      (appends to master_dataset.csv)
```

**Pipeline chain:**

| Order | Class | Input | Output |
|---|---|---|---|
| 100 | `NexoraExtractionPipeline` | `item[html]`, `item[url]` | all extraction fields added to item |
| 200 | `NexoraExportPipeline` | fully extracted item | `output/pages/<slug>.json` + `.csv` |
| 300 | `NexoraDatasetPipeline` | fully extracted item | row appended to `output/master_dataset.csv` |

**Key settings (settings.py):**

| Setting | Value | Why |
|---|---|---|
| `DEPTH_LIMIT` | 2 | how many link-hops from seed URL |
| `DOWNLOAD_DELAY` | 1.5s | politeness — min gap between requests to same domain |
| `RANDOMIZE_DOWNLOAD_DELAY` | True | varies delay 1.5–3.0s to appear more human |
| `CONCURRENT_REQUESTS_PER_DOMAIN` | 2 | don't hammer a single server |
| `ROBOTSTXT_OBEY` | True | always — never disable without permission |
| `HTTPCACHE_ENABLED` | True | caches responses for 1hr (dev only, disable in production) |

**Spider arguments:**

| Argument | Example | Default |
|---|---|---|
| `urls` | `-a urls="https://a.com,https://b.com"` | realpython.com + wikipedia |
| `depth` | `-a depth=1` | 2 (from settings) |

**JS-heavy domains (flagged for Phase 3, no browser launched yet):**
youtube.com, twitter.com, x.com, instagram.com, facebook.com, reddit.com, airbnb.com, linkedin.com

**Path bootstrap in pipelines.py:**
```python
# crawler/nexora_crawler/pipelines.py — two levels up = nexora/ root
_PROJECT_ROOT = os.path.abspath(
    os.path.join(os.path.dirname(__file__), "..", "..")
)
```
This must resolve to `nexora/` for the Phase 1 import to work.

**master_dataset.csv columns:**
`url, title, author, date, language, word_count_raw, word_count_clean,
images_count, links_count, playwright_used, crawled_at, depth`

---

## Phase 3 — Playwright Hooks (Already Wired, Not Yet Active)

Everything needed for Phase 3 is already in the codebase — just commented out.

**To activate (when ready):**
```bash
pip install scrapy-playwright
playwright install chromium
```

Then uncomment in `settings.py`:
```python
DOWNLOAD_HANDLERS = {
    "http":  "scrapy_playwright.handler.ScrapyPlaywrightDownloadHandler",
    "https": "scrapy_playwright.handler.ScrapyPlaywrightDownloadHandler",
}
TWISTED_REACTOR = "twisted.internet.asyncioreactor.AsyncioSelectorReactor"
PLAYWRIGHT_BROWSER_TYPE = "chromium"
PLAYWRIGHT_LAUNCH_OPTIONS = {"headless": True}
```

And in `DOWNLOADER_MIDDLEWARES`:
```python
"nexora_crawler.middlewares.PlaywrightRoutingMiddleware": 600,
```

**What's already wired without any changes needed:**
- Spider sets `meta['playwright'] = True` for JS-heavy domains automatically
- `PlaywrightRoutingMiddleware` stub exists in middlewares.py
- Pipelines handle both static and Playwright-rendered HTML identically
- `item['playwright_used']` field already tracked in master_dataset.csv

---

## Entry Points Summary

| Scenario | Command | Phase |
|---|---|---|
| Test single URL | `python extractor/main.py https://example.com` | 1 only |
| Multi-page crawl | `cd crawler && scrapy crawl nexora -a urls="..." -a depth=1` | 1 + 2 |
| JS-heavy site | same scrapy command — Playwright auto-flagged, browser in Phase 3 | 1 + 2 + 3 |

**Rule:** Phase 1 CLI = dev/debug tool. Scrapy = production entry point once Phase 2 is active.

---

## Requirements

```
# Phase 1 + 2 (current)
requests>=2.31.0
beautifulsoup4>=4.12.0
trafilatura>=1.6.0
lxml>=4.9.0
scrapy>=2.11.0

# Phase 3 (when ready)
# scrapy-playwright>=0.0.33
# playwright>=1.40.0

# Phase 4 (AI layer — not started)
# anthropic>=0.20.0
# openai>=1.0.0
```

---

## Key Design Decisions (for continuity)

1. **Phase 1 is never modified** — only `extract_with_bs4()` and `extract_with_trafilatura()` are imported by Phase 2. `fetch_html()`, `save_json()`, `save_csv()`, `main()` are Phase 1-only.

2. **Spider does one thing** — fetches HTML, wraps it in `NexoraPageItem`, yields it. Zero parsing logic in the spider.

3. **Pipelines are independent** — each can be disabled in settings.py with one line. Disabling pipeline 200 stops file saving without affecting extraction or the master dataset.

4. **`scrapy.cfg` must be present** — running `scrapy crawl nexora` from any directory other than `nexora/crawler/` will fail with `No scrapy.cfg found`.

5. **JS detection is domain-based** — `_needs_playwright()` in the spider checks against a hardcoded set. In Phase 4 this could be replaced with an ML classifier.

6. **`master_dataset.csv` appends, never overwrites** — running multiple crawls accumulates rows. Delete the file to start fresh.

---

## Outstanding / Next Steps

- [ ] User to share modularized Phase 1 structure so pipelines.py imports can be updated
- [ ] Test Phase 2 live against a real static site (realpython.com or wikipedia recommended)
- [ ] Verify `_PROJECT_ROOT` path resolves correctly on Windows (backslash vs forward slash)
- [ ] Phase 3: Playwright integration once Phase 2 tests pass
- [ ] Phase 4: AI summarisation layer on `clean_text` field
- [ ] Root `main.py` dispatcher (single entry point for all phases)

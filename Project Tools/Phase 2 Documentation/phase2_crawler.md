# Nexora — Phase 2: Multi-Page Crawler

## What Phase 2 adds (without touching Phase 1)

Phase 1 (`extractor/`) is **completely unchanged**. Phase 2 wraps it in a
Scrapy crawling engine that handles everything multi-page:

| Capability | How |
|---|---|
| Follow links across a whole site | `response.follow()` in the spider |
| Depth control | `DEPTH_LIMIT` in settings.py |
| Duplicate URL filtering | Scrapy's built-in `RFPDupeFilter` |
| Politeness (delays, robots.txt) | `DOWNLOAD_DELAY`, `ROBOTSTXT_OBEY` |
| Rotating User-Agents | `NexoraUserAgentMiddleware` |
| Per-page JSON + CSV | `NexoraExportPipeline` |
| Master dataset across all pages | `NexoraDatasetPipeline` → `output/master_dataset.csv` |
| Phase 3 JS routing hook | `meta['playwright']` flag already wired in |

---

## Quickstart

```bash
# From the crawler/ directory:
cd nexora/crawler

# Crawl default seed URLs (realpython.com + wikipedia)
scrapy crawl nexora

# Crawl your own URLs
scrapy crawl nexora -a urls="https://example.com,https://realpython.com"

# Limit crawl depth (0=seed only, 1=+direct links, 2=default)
scrapy crawl nexora -a urls="https://example.com" -a depth=1

# Verbose output
scrapy crawl nexora --loglevel=DEBUG
```

---

## Output structure

After a crawl, `output/` contains:

```
output/
├── pages/
│   ├── en_wikipedia_org__wiki_Web_scraping__20240601T183000.json
│   ├── en_wikipedia_org__wiki_Web_scraping__20240601T183000.csv
│   ├── realpython_com__root__20240601T183001.json
│   └── ...
└── master_dataset.csv     ← one row per page, entire crawl
```

`master_dataset.csv` columns:

| Column | Description |
|---|---|
| `url` | Final resolved URL |
| `title` | Page title |
| `author` | Article author (Trafilatura) |
| `date` | Publication date |
| `language` | Detected language |
| `word_count_raw` | Total words in raw HTML text |
| `word_count_clean` | Words in boilerplate-stripped text |
| `images_count` | Number of images found |
| `links_count` | Internal links found |
| `playwright_used` | False in Phase 2, True in Phase 3 |
| `crawled_at` | ISO timestamp |
| `depth` | Link hops from seed URL |

---

## Architecture: how the pieces connect

```
Spider (nexora_spider.py)
  │
  │  yields NexoraPageItem(url=..., html=..., depth=..., playwright_used=...)
  ▼
Pipeline 100 — NexoraExtractionPipeline
  │  calls extract_with_bs4(html, url)        ← Phase 1, untouched
  │  calls extract_with_trafilatura(html, url) ← Phase 1, untouched
  │  merges results into item
  ▼
Pipeline 200 — NexoraExportPipeline
  │  saves output/pages/<slug>.json
  │  saves output/pages/<slug>.csv
  ▼
Pipeline 300 — NexoraDatasetPipeline
     appends summary row to output/master_dataset.csv
```

---

## Configuration (settings.py)

```python
DEPTH_LIMIT              = 2      # link hops from seed
DOWNLOAD_DELAY           = 1.5    # seconds between requests (same domain)
CONCURRENT_REQUESTS      = 8      # total parallel requests
CONCURRENT_REQUESTS_PER_DOMAIN = 2
ROBOTSTXT_OBEY           = True   # always True — be a good bot
HTTPCACHE_ENABLED        = True   # cache responses for 1hr (dev only)
```

---

## Phase 3 hooks already in place

The entire Phase 3 (Playwright) wiring is **already in the codebase** — just
commented out or stubbed. When ready:

1. `pip install scrapy-playwright && playwright install chromium`
2. Uncomment 4 lines in `settings.py`
3. Uncomment 1 line in `middlewares.py` `DOWNLOADER_MIDDLEWARES`

Nothing in the spider, pipelines, or Phase 1 changes.

# Nexora v4.1 — Data Access & Storage Guide

> **Phase 4A:** Storage & Multi-Format Ingestion Engine  
> **Version:** 4.1.0  
> **Date:** 2026-06-30  
> **Principle:** *One crawl → multiple formats → one unified schema*

---

## Table of Contents

1. [Understanding the Markdown Output](#1-understanding-the-markdown-output)
2. [Output Formats Overview](#2-output-formats-overview)
3. [JSON + CSV — Per-Page Export](#3-json--csv--per-page-export)
4. [Parquet — Columnar / ML Export](#4-parquet--columnar--ml-export)
5. [SQLite — Relational Metadata Store](#5-sqlite--relational-metadata-store)
6. [Markdown — LLM-Ready Content](#6-markdown--llm-ready-content)
7. [Configuration Reference](#7-configuration-reference)
8. [Quick Reference — Access Cheatsheet](#8-quick-reference--access-cheatsheet)

---

## 1. Understanding the Markdown Output

**Important:** The `markdown` field is **NOT an AI summary**. It is **boilerplate-stripped, reader-mode text** — the same kind of clean content you get when using your browser's "Reader Mode."

### What happens:

| Step | Input → Output | Description |
|------|---------------|-------------|
| Raw HTML | `<html><body><nav>...</nav><article><h1>Title</h1><p>Article content...</p></article><footer>...</footer></body></html>` | Full page with navigation, ads, cookie banners, footer |
| After Trafilatura | `# Title\n\nArticle content...` | Boilerplate removed. Content preserved. |
| Token reduction | Raw: 10,000 tokens → Clean: 2,500 tokens | **~75% reduction** — savings come from removing HTML tags and boilerplate, NOT from truncation or summarization |

### What IS preserved:
- Article body text
- Tables (converted to pipe-delimited Markdown)
- Links (as `[text](url)`)
- Headings (`#`, `##`, etc.)
- Structured content

### What IS stripped:
- HTML tags, attributes, `<script>`, `<style>`
- Navigation menus, sidebars
- Cookie/consent banners
- Footer links, copyright text
- Ads and tracking elements

### What is NOT done (Phase 4B):
- AI summarization (`ai_summary` field is reserved for Phase 4B)
- Keyword extraction
- Semantic chunking
- Embedding generation

---

## 2. Output Formats Overview

All four formats are generated automatically from a single Scrapy crawl. No additional commands are needed.

```
                    ┌─────────────────────────────────────────┐
                    │           ONE SCRAPY CRAWL              │
                    └──────────────────┬──────────────────────┘
                                       │
              ┌────────────────────────┼────────────────────────┐
              │                        │                        │
              ▼                        ▼                        ▼
     ┌────────────────┐     ┌──────────────────┐     ┌──────────────────┐
     │  NexoraExport  │     │ ParquetExport    │     │ MetadataIndexer  │
     │  Pipeline 500  │     │ Pipeline 450     │     │ Pipeline 165     │
     └───────┬────────┘     └────────┬─────────┘     └────────┬─────────┘
             │                      │                        │
             ▼                      ▼                        ▼
     ┌───────────────┐    ┌─────────────────┐      ┌──────────────────┐
     │ output/pages/ │    │ output/parquet/  │      │ data/nexora_    │
     │  *.json       │    │  *.parquet       │      │ metadata.db     │
     │  *.csv        │    │ (compressed)     │      │ (SQLite)        │
     └───────────────┘    └─────────────────┘      └──────────────────┘
```

| Format | Location | Size | Best For |
|--------|----------|:----:|----------|
| **JSON** | `output/pages/*.json` | Full | Human inspection, API consumption, full-data access |
| **CSV** | `output/pages/*.csv` | Full | Spreadsheet analysis, Excel |
| **Parquet** | `output/parquet/*.parquet` | ~10-30% of JSON | ML pipelines, large-scale analytics, cloud storage |
| **SQLite** | `data/nexora_metadata.db` | Compact | Fast queries, filtering, cross-page joins, metadata |
| **Markdown** | Inside JSON (field: `markdown`) | N/A | LLM context, RAG, human reading |

---

## 3. JSON + CSV — Per-Page Export

### Location

```
Nexora application/output/pages/
├── example_com__about__20260630T143022.json
└── example_com__about__20260630T143022.csv
```

### File Naming

`{domain}__{path_slug}__{timestamp}.json|csv`

- `domain`: `example.com` → `example_com`
- `path_slug`: First 40 chars of URL path, sanitized
- `timestamp`: `20260630T143022` (UTC)

### Access via Python

```python
import json

# Load a single page export
with open("output/pages/example_com__about__20260630T143022.json") as f:
    data = json.load(f)

# ── Phase 4A fields available ──────────────────────────────
print(data["url"])                      # str
print(data["markdown"])                 # str — clean Markdown
print(data["markdown_word_count"])      # int
print(data["extraction_method"])        # str — "trafilatura"
print(data["token_reduction_pct"])      # float — e.g. 72.3

# Multimodal assets
print(data["image_assets"])             # list[dict] — structured image metadata
print(data["video_assets"])             # list[dict] — structured video metadata
print(data["total_images"])             # int
print(data["total_videos"])             # int
print(data["has_hero_image"])           # bool

# Unified schema
print(data["crawl_id"])                 # str
print(data["timestamp"])                # str — ISO 8601
print(data["domain"])                   # str
print(data["entities"])                 # dict — prices, currency, tickers, etc.
print(data["style_analysis"])           # dict — colors, tech_stack, framework
print(data["quality_scores"])           # dict — readability, duplication
print(data["website_type"])             # str — e.g. "article", "e-commerce"

# ── Phase 1-3 fields (unchanged) ──────────────────────────
print(data["title"])
print(data["clean_text"])
print(data["styles"])
print(data["structured_schema"])
```

### CSV Considerations

- Nested structures (entities, style_analysis, image_assets) are **JSON-stringified** into single CSV columns
- Extract specific nested values after loading:
  ```python
  import json
  entities = json.loads(row["entities"])
  print(entities["prices"])
  ```

### Batch Processing All Pages

```python
import os, json

pages_dir = "output/pages"
for fname in os.listdir(pages_dir):
    if fname.endswith(".json"):
        with open(os.path.join(pages_dir, fname)) as f:
            data = json.load(f)
        print(f"{data['url']:60s} | {data['website_type']:15s} | {data['markdown_word_count']:6d} words")
```

---

## 4. Parquet — Columnar / ML Export

### Location

```
Nexora application/output/parquet/
├── nexora_20260630_190925_0000.parquet
├── nexora_20260630_190925_0001.parquet
└── ...
```

### File Naming

`{spider_name}_{timestamp}_{counter:04d}.parquet`

- Buffered: every 100 rows are flushed as one file
- Compression: snappy (default; configurable to gzip, brotli, zstd)

### Access via Python

```python
import pandas as pd

# Read ALL parquet files in the directory
import glob
files = glob.glob("output/parquet/*.parquet")
df = pd.concat([pd.read_parquet(f) for f in files], ignore_index=True)

# ── Available columns ──────────────────────────────────────
# Columns that are preserved:
#   url, title, domain, timestamp, crawl_id, website_type,
#   markdown_word_count, token_reduction_pct, total_images,
#   total_videos, has_hero_image, language, extraction_method,
#   spider_name, depth, playwright_used, price_change_delta
#
# Columns stored as JSON strings (use json.loads to parse):
#   entities_json, style_analysis_json, quality_scores_json,
#   image_assets_json, video_assets_json, ai_tags_json
#
# Columns REMOVED (too heavy for columnar):
#   html, markdown, clean_text

# Query examples
articles = df[df["website_type"] == "article"]
print(f"Total articles: {len(articles)}")
print(articles[["url", "markdown_word_count", "token_reduction_pct"]])

# Parse nested JSON within a column
import json
df["entities"] = df["entities_json"].apply(lambda x: json.loads(x) if pd.notna(x) else {})
df["has_prices"] = df["entities"].apply(lambda e: len(e.get("prices", [])) > 0)

# Parquet size comparison
json_size = 50_000_000   # ~50 MB equivalent JSON
parquet_size = 12_000_000  # ~12 MB actual
print(f"Parquet is {parquet_size / json_size:.1%} of JSON size")
```

### Why Use Parquet?

| Feature | Benefit |
|---------|---------|
| Columnar storage | Only read the columns you need |
| Snappy compression | ~10-30% of equivalent JSON file size |
| Schema enforcement | Type-safe, no parsing errors |
| Predicate pushdown | Fast filtering without loading all data |
| ML-ready | Direct input to pandas, PyTorch, TensorFlow, Spark |

---

## 5. SQLite — Relational Metadata Store

### Location

```
Nexora application/data/nexora_metadata.db
```

### Tables

```sql
-- pages — one row per crawled URL
CREATE TABLE pages (
    id               INTEGER PRIMARY KEY AUTOINCREMENT,
    url              TEXT NOT NULL UNIQUE,
    domain           TEXT NOT NULL,
    title            TEXT,
    timestamp        TEXT NOT NULL,
    crawl_id         TEXT NOT NULL,
    markdown_preview TEXT,            -- first 500 chars of markdown
    markdown_word_count INTEGER DEFAULT 0,
    token_reduction_pct REAL DEFAULT 0.0,
    ai_summary       TEXT,
    ai_tags_json     TEXT,
    entities_json    TEXT DEFAULT '{}',
    price_change_delta REAL,
    style_analysis_json TEXT DEFAULT '{}',
    quality_scores_json TEXT DEFAULT '{}',
    image_assets_json TEXT DEFAULT '[]',
    video_assets_json TEXT DEFAULT '[]',
    total_images     INTEGER DEFAULT 0,
    total_videos     INTEGER DEFAULT 0,
    has_hero_image   INTEGER DEFAULT 0,
    language         TEXT,
    website_type     TEXT DEFAULT 'unknown',
    extraction_method TEXT,
    spider_name      TEXT,
    depth            INTEGER DEFAULT 0,
    playwright_used  INTEGER DEFAULT 0,
    created_at       TEXT DEFAULT (datetime('now'))
);

CREATE INDEX idx_pages_domain ON pages(domain);
CREATE INDEX idx_pages_crawl_id ON pages(crawl_id);
CREATE INDEX idx_pages_website_type ON pages(website_type);
CREATE INDEX idx_pages_timestamp ON pages(timestamp);
CREATE INDEX idx_pages_language ON pages(language);

-- crawl_jobs — one row per crawl session
CREATE TABLE crawl_jobs (
    job_id        TEXT PRIMARY KEY,
    url           TEXT NOT NULL,
    strategy      TEXT DEFAULT 'whole-website',
    max_pages     INTEGER DEFAULT 100,
    status        TEXT DEFAULT 'running',
    pages_crawled INTEGER DEFAULT 0,
    pages_failed  INTEGER DEFAULT 0,
    started_at    TEXT NOT NULL,
    completed_at  TEXT,
    error         TEXT
);
```

### Access via Python (Recommended)

```python
from nexora_crawler.storage.local_sqlite import MetadataStore

store = MetadataStore()   # connects to data/nexora_metadata.db

# ── Query by domain ────────────────────────────────────────
results = store.query_by_domain("example.com", limit=50)
for r in results:
    print(f"{r['url']:60s} | {r['website_type']:15s} | {r['markdown_word_count']} words")

# ── Query by crawl session ─────────────────────────────────
crawl_pages = store.query_by_crawl_id("crawl-uuid-here")
print(f"Pages in this crawl: {len(crawl_pages)}")

# ── Get database statistics ────────────────────────────────
stats = store.get_stats()
print(f"Total pages indexed: {stats['total_pages']}")
print(f"Unique domains: {stats['unique_domains']}")
```

### Access via SQLite CLI

```powershell
# Open the database
sqlite3 data/nexora_metadata.db

# Explore
.tables                                    # pages, crawl_jobs
.schema pages                              # Full table schema

# Queries
SELECT url, website_type, markdown_word_count
FROM pages
WHERE website_type = 'e-commerce'
ORDER BY markdown_word_count DESC
LIMIT 10;

SELECT domain, COUNT(*) as page_count
FROM pages
GROUP BY domain
ORDER BY page_count DESC;

SELECT crawl_id, url, strategy, status, pages_crawled
FROM crawl_jobs
ORDER BY started_at DESC;
```

### Access via Pandas

```python
import sqlite3, pandas as pd

conn = sqlite3.connect("data/nexora_metadata.db")

df = pd.read_sql_query("""
    SELECT url, domain, website_type, markdown_word_count,
           token_reduction_pct, total_images, total_videos
    FROM pages
    WHERE website_type IN ('article', 'blog')
    ORDER BY markdown_word_count DESC
    LIMIT 100
""", conn)

print(f"Found {len(df)} articles/blog posts")
print(df.groupby("website_type").agg({"url": "count", "markdown_word_count": "mean"}))
```

---

## 6. Markdown — LLM-Ready Content

### Where to Find It

| Source | How to Access |
|--------|--------------|
| **In-memory (during crawl)** | `item["markdown"]` |
| **JSON export** | `data["markdown"]` after `json.load()` |
| **SQLite** | `markdown_preview` column (first 500 chars — for full text, use JSON) |
| **Parquet** | **NOT included** — removed for columnar efficiency. Use JSON for full text. |

### Example: Using Markdown for LLM Context

```python
import json

with open("output/pages/example_com__article__20260630T143022.json") as f:
    data = json.load(f)

# Build an LLM prompt with the clean content
prompt = f"""You are analyzing a web page. Here is the content:

URL: {data['url']}
Title: {data['title']}
Type: {data['website_type']}
Language: {data['language']}

Content:
{data['markdown'][:4000]}  # First ~4000 chars for context window

Please provide:
1. A 2-3 sentence summary of this page
2. 3-5 relevant tags
3. Key entities mentioned (people, organizations, products)"""

print(prompt)
# → Send this to your LLM
```

### Markdown vs Clean Text

| Field | Source | Characteristics |
|-------|--------|-----------------|
| `markdown` | Trafilatura | Headings with `#`, tables with `\|`, links as `[text](url)` |
| `clean_text` | BS4 extractor | Plain text, no formatting, may include some boilerplate |

**For LLM use, prefer `markdown`** — the structure helps the model understand hierarchy.

---

## 7. Configuration Reference

All settings in `Crawler/nexora_crawler/settings.py`:

| Setting | Default | Description |
|---------|---------|-------------|
| `NEXORA_MARKDOWN_ENABLED` | `True` | Enable Markdown extraction |
| `NEXORA_PARQUET_ENABLED` | `True` | Enable Parquet export |
| `NEXORA_PARQUET_COMPRESSION` | `'snappy'` | `snappy` / `gzip` / `brotli` / `zstd` |
| `NEXORA_PARQUET_ROW_GROUP_SIZE` | `10000` | Rows per row group |
| `NEXORA_PARQUET_OUTPUT` | `'./output/parquet'` | Output directory |
| `NEXORA_METADATA_DB` | `'./data/nexora_metadata.db'` | SQLite database path |

### Pipeline Priorities

```python
ITEM_PIPELINES = {
    "NexoraExtractionPipeline":     100,   # Phase 1-2
    "MarkdownExtractionPipeline":   110,   # Phase 4A ← Markdown + multimodal
    "NexoraStylePipeline":          150,   # Phase 2
    "UnifiedSchemaEnricher":        160,   # Phase 4A ← Schema defaults
    "MetadataIndexerPipeline":      165,   # Phase 4A ← SQLite
    # Phase 4B at 250+
    "ParquetExportPipeline":        450,   # Phase 4A ← Parquet
    "NexoraExportPipeline":         500,   # Phase 1     ← JSON + CSV
    "NexoraDatasetPipeline":        600,   # Phase 1     ← master CSV
}
```

---

## 8. Quick Reference — Access Cheatsheet

### I want to...

| Task | Command |
|------|---------|
| **View all crawled URLs** | `sqlite3 data/nexora_metadata.db "SELECT url, website_type FROM pages;"` |
| **Read Markdown from a page** | `python -c "import json; d=json.load(open('output/pages/example.json')); print(d['markdown'])"` |
| **Count pages by type** | `sqlite3 data/nexora_metadata.db "SELECT website_type, count(*) FROM pages GROUP BY website_type;"` |
| **Load Parquet in Python** | `import pandas as pd; df = pd.read_parquet('output/parquet/file.parquet')` |
| **Find pages with prices** | See SQLite query on `entities_json` or use Parquet + JSON parsing |
| **Get crawl job stats** | `sqlite3 data/nexora_metadata.db "SELECT * FROM crawl_jobs;"` |
| **Export all pages to DataFrame** | `import pandas as pd; import glob; df = pd.concat([pd.read_parquet(f) for f in glob.glob('output/parquet/*.parquet')])` |
| **Check if pipeline ran** | Check `output/pages/` has files, or `data/nexora_metadata.db` exists |
| **Read image metadata** | `python -c "import json; d=json.load(open('output/pages/example.json')); print(json.dumps(d['image_assets'], indent=2))"` |
# Phase 3b v0.2 Data Extraction and Storage Structure

## Overview
This document describes what Nexora currently extracts, how it is structured in memory, and exactly where it is stored by the Phase 3b v0.2 pipeline.

The current production export paths are inside `Nexora application/output/` and include per-page JSON/CSV files plus a consolidated master dataset CSV.

---

## Data Sources and Extraction Modules

### 1. Scrapy item contract (`Crawler/nexora_crawler/items.py`)
The central data contract is `NexoraPageItem`. Items travel from spider → pipelines → exporter.

Key item fields:
- `url`
- `status`
- `html`
- `depth`
- `spider_name`
- `crawled_at`
- `playwright_used`
- `screenshot_path`
- `render_time_ms`
- `styles`
- `fingerprint`
- `language_iso`
- `language_confidence`
- `structured_schema`
- `social_graphs`
- `graph_relations`
- `image_assets`
- `title`
- `description`
- `keywords`
- `meta_tags`
- `headings`
- `images`
- `internal_links`
- `word_count_raw`
- `clean_text`
- `word_count_clean`
- `author`
- `date`
- `language`
- `sitename`
- `tags`
- `response_time_ms`
- `sitemap_lastmod`
- `sitemap_priority`
- `sitemap_changefreq`
- `from_sitemap`
- `saved_json`
- `saved_csv`

---

## Extraction pipeline mapping

### 2. HTML structural extraction (`Extractor/Beautifulsoup_extractor.py`)
Runs inside `NexoraExtractionPipeline` and fills these item fields:
- `title`
- `description`
- `keywords`
- `meta_tags` (dict of meta names/properties → values)
- `headings` (dict with `h1`, `h2`, `h3` lists)
- `images` (list of `{src, alt, width, height}`)
- `internal_links` (list of `{url, text}`)
- `word_count_raw`

### 3. Clean article & metadata extraction (`Extractor/Trafilatura_extractor.py`)
Also runs inside `NexoraExtractionPipeline` and fills:
- `clean_text`
- `word_count_clean`
- `author`
- `date`
- `language`
- `sitename`
- `tags`

### 4. Content quality and deduplication (`Extractor/cleaner.py`)
After extraction, the pipeline computes:
- `fingerprint` (SimHash or deterministic fallback)
- `language_iso` (ISO code from FastText, fallback `en`)
- `language_confidence`

### 5. Semantic and page relationships (`Extractor/parser.py`)
Also inside `NexoraExtractionPipeline`:
- `structured_schema` (list of JSON-LD / Microdata / RDFa objects)
- `social_graphs` (Open Graph + Twitter card meta values)
- `graph_relations` (canonical URL, AMP, pagination, alternates)
- `image_assets` (rich image descriptors with `src`, `alt`, `title`, dimensions, loading, class, etc.)

### 6. Style intelligence extraction (`Extractor/style_extractor.py`)
Populated by `NexoraStylePipeline` into:
- `styles` (dict containing):
  - `colors` (top palette values)
  - `fonts`
  - `framework`
  - `theme`
  - `has_animations`
  - `layout_type`
  - `inline_css_length`
  - `linked_stylesheets`

---

## Storage and export mapping

### 7. Per-page exports (`Crawler/nexora_crawler/pipelines.py`)
`NexoraExportPipeline` writes each non-skipped item to:
- `Nexora application/output/pages/<domain>__<path_slug>__<timestamp>.json`
- `Nexora application/output/pages/<domain>__<path_slug>__<timestamp>.csv`

The base name is generated from:
- domain from `url`
- a cleaned path slug from the URL path
- UTC timestamp `YYYYMMDDTHHMMSS`

#### JSON export
- Writes the full item as a plain dict.
- Nested fields remain nested.
- Example exact output location: `output/pages/bbc_com__news__20260101T123456.json`

#### CSV export
- Writes a single-row CSV with all item fields.
- Nested dict/list values are flattened using `json.dumps(...)`.
- This means the CSV retains every field, but complex values are stored as JSON strings.

#### Item fields persisted to per-page exports
All item fields defined in `NexoraPageItem` are saved in JSON. The CSV mirrors those fields by flattening nested structures.

### 8. Master dataset summary (`Crawler/nexora_crawler/pipelines.py`)
`NexoraDatasetPipeline` appends one row per item into:
- `Nexora application/output/master_dataset.csv`

Current columns:
- `url`
- `title`
- `author`
- `date`
- `language`
- `word_count_raw`
- `word_count_clean`
- `images_count`
- `links_count`
- `framework`
- `theme`
- `layout_type`
- `has_animations`
- `fonts`
- `playwright_used`
- `crawled_at`
- `depth`
- `sitemap_lastmod`
- `sitemap_priority`
- `sitemap_changefreq`
- `from_sitemap`

#### Master dataset field origins
- `url`: item URL, overridden by canonical URL when available
- `title`: from BS4 extraction
- `author`: from Trafilatura extraction
- `date`: from Trafilatura extraction
- `language`: from Trafilatura extraction
- `word_count_raw`: from BS4 extraction
- `word_count_clean`: from Trafilatura extraction
- `images_count`: count of `images` list
- `links_count`: count of `internal_links` list
- `framework`: `styles.get("framework", "unknown")`
- `theme`: `styles.get("theme", "unknown")`
- `layout_type`: `styles.get("layout_type", "unknown")`
- `has_animations`: `styles.get("has_animations", False)`
- `fonts`: comma-joined `styles.get("fonts", [])`
- `playwright_used`: page render mode flag from the spider / middleware
- `crawled_at`: fetch timestamp from the spider
- `depth`: crawl depth from the request metadata
- `sitemap_lastmod`: sitemap `lastmod` if request came from sitemap
- `sitemap_priority`: sitemap `priority` if present
- `sitemap_changefreq`: sitemap `changefreq` if present
- `from_sitemap`: boolean marker when the page originated from a sitemap

---

## Current storage structure summary

### `output/pages/`
- Each fetched page is persisted as two files:
  - JSON with full item structure and nested extraction results.
  - CSV with the same fields flattened for spreadsheet-friendly review.
- This directory is the detailed page-level storage layer and contains one file pair per successful item.

### `output/master_dataset.csv`
- This file is the summary layer for analytics and dataset-level inspection.
- It intentionally omits nested semantic fields and raw HTML/text to keep row widths manageable.
- It is append-only and persisted across spider runs; remove the file manually to reset.

### What is not stored in `master_dataset.csv`
- `html`
- `meta_tags`
- `headings`
- `images` (full list)
- `internal_links` (full list)
- `structured_schema`
- `social_graphs`
- `graph_relations`
- `image_assets`
- `styles.colors`
- `styles.linked_stylesheets`
- `fingerprint`
- `language_iso`
- `language_confidence`
- `clean_text`
- `response_time_ms`
- `saved_json`
- `saved_csv`

---

## Important data flow notes

- `NexoraPageItem` defines every field that may be exported by the crawler.
- `NexoraExportPipeline` serializes the item to JSON and then flattens it to CSV, so per-page exports contain _all extracted fields_.
- `NexoraDatasetPipeline` writes a reduced row of high-level metadata and style signals for fast analysis.
- Canonical URL detection can override `item["url"]` before both per-page and master dataset exports.
- The `styles` payload is computed after HTML extraction and is the only field in the master dataset that is partially expanded (`framework`, `theme`, `layout_type`, `has_animations`, `fonts`).

---

## Recommended export validation checkpoints

1. Verify `output/pages/` contains matching `.json` / `.csv` pairs for a sample URL.
2. Open a per-page JSON and confirm nested keys such as `structured_schema`, `social_graphs`, `graph_relations`, `image_assets`, and `styles` exist.
3. Check `output/master_dataset.csv` for expected summary columns and confirm row counts after a crawl.
4. If `master_dataset.csv` grows unexpectedly, remember it appends and is not recreated each spider run.

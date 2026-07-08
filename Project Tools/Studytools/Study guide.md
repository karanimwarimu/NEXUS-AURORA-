# Nexora Core Engine Study Guide: Phase 4A

**Target Substrate:** Scrapy + Playwright + httpx + Trafilatura + SQLite + Parquet

**Objective:** Operational Mastery of the Multi-Format Ingestion Engine

---

## System Overview & Worker Pipeline Flow

Before looking at any individual component, you must memorize how data morphs sequentially. The engine operates like an assembly line where an Item dictionary flows through specific execution numbers (priorities):

```
[Spiders / Middlewares]
   ├── httpx (Static Probe) ─────────────────────────► [Bypasses Browser if Static]
   └── Playwright (JS Render Hatch) ─────────────────► [Captures Dynamic Dom]
              │
              ▼
    [ Scrapy Engine Substrate ]
              │
              ├──► Priority 100: NexoraExtractionPipeline (Raw baseline parsing)
              │
              ├──► Priority 110: MarkdownExtractionPipeline (Intelligent extraction)
              │                     └── Inline Call: MultimodalAssetExtractor
              │
              ├──► Priority 150: NexoraStylePipeline (Visual layout parsing)
              │
              ├──► Priority 160: UnifiedSchemaEnricher (Contract enforcement)
              │
              ├──► Priority 165: MetadataIndexerPipeline (Fast relational storage)
              │                     └── Target: SQLite Database
              │
              └──► Priority 450: ParquetExportPipeline (Columnar compression)
                                    └── Target: Snappy-compressed .parquet
```

---

## Weekend Study Breakdown Plan

### Friday Night: The Boundary Constraints

**Focus:** The Orchestration Substrate and The Data Contract

**Target Code Units:** `crawler/settings.py`, `spiders/nexora_spider.py`, `items.py`

#### 1. Core Architectural Strategy

**Scrapy Substrate:** Chosen as the primary runtime loop because of its mature asynchronous engine, automated request deduplication (dupefilter), and built-in pipeline processing sequence.

**The Static-vs-Dynamic Gate:** To prevent massive performance bottlenecks, the network layer uses an httpx static probe middleware before resorting to an expensive, heavy headless browser. If the page is static, httpx captures it with zero browser overhead. If dynamic JS rendering is detected, the engine drops into the Playwright escape hatch to extract the browser-rendered DOM.

#### 2. Hand-Note Target Blueprint

Open your physical notebook to Page 1 and sketch The Nexora Item Schema. Note these explicit field zones:

- **Identity Group:** `url`, `domain`, `title`, `crawl_id`
- **Content/Refinement Group:** `html`, `markdown`, `markdown_word_count`, `token_reduction_pct`
- **Multimodal Asset Dictionaries:**
  - `image_assets` (containing `src`, `alt`, `width`, `height`, `is_hero`)
  - `video_assets` (containing `platform`, `poster`, `source type`)
- **AI & Analytical Placeholders:** `entities`, `style_analysis`, `quality_scores`, `website_type`

> **Notebook Check:** Draw an exclamation point next to this list and write: "Every single downloader pipeline downstream expects these keys to exist exactly as typed. Missing keys cause analytical pipeline failures."

---

### Saturday: The Refinement Loops (Priorities 110 & 160)

**Focus:** Turning raw markup into clean, normalized text.

**Target Code Units:** `markdown_pipeline.py`, `multimodal_extractor.py`, `schema_enricher.py`

#### Step 1: Markdown Extraction (Priority 110)

**The Trafilatura Engine:** This module is responsible for reader-mode markdown conversion. It bypasses menus, navigation headers, footers, and advertisement blocks to achieve a 50% total token footprint reduction.

**The Inline Helper (MultimodalAssetExtractor):** While Trafilatura strips general media, this component inspects raw HTML tags (`<img>`, `<video>`, `<iframe>`) to build a map of structural images, identify high-resolution images via srcset parsers, and tag embedded media arrays without downloading binary data.

**Input Data Shape:**

```json
{
  "url": "https://example.com/item",
  "html": "<html><nav>Navbar</nav><main><h1>Title</h1></main></html>"
}
```

**Transformation Applied:**

Runs `trafilatura.extract()`. Triggers beautifulsoup fallback rules if text output length < 50 characters.

**Output Data Shape:**

```json
{
  "url": "https://example.com/item",
  "markdown": "# Title",
  "extraction_method": "trafilatura",
  "token_reduction_pct": 65.4,
  "image_assets": [...]
}
```

#### Step 2: Unified Schema Enrichment (Priority 160)

**The Data Guard:** Web data is highly inconsistent. This step ensures that even if a crawl step completely misses metadata fields, the item dictionary is immediately repaired by injecting empty baseline types (e.g., standard dictionary keys for prices, tickers, product data, and style signatures).

**Heuristic Classification:** Analyzes structural metrics (URL slugs, markdown length, headers, and specific object matches) to auto-categorize the text as e-commerce, blog, documentation, or article.

> **Notebook Check:** Write this defensive pattern rule down by hand: "Access dictionary keys using `.get('key', default)` rather than `item['key']`. If an error occurs or data is missing, `.get()` handles it gracefully without a KeyError crash."

---

### Sunday: The Permanent Record (Storage Layers)

**Focus:** Splitting metadata queries from bulk analytical files.

**Target Code Units:** `local_sqlite.py`, `metadata_indexer.py`, `parquet_export.py`

#### 1. Relational Staging: SQLite (MetadataStore)

**Role:** Tracks fast operational metadata. It stores index targets, titles, operational timestamps, crawling performance metrics, and short strings.

**Optimization:** Contains strict database indices (`idx_pages_domain`, `idx_pages_crawl_id`) to ensure near-instant historical lookup queries when analysts look up data by domain or batch identifiers.

#### 2. Analytical Columns: Parquet (ParquetExportPipeline at Priority 450)

**Role:** Collects structural data matrices for machine learning pipelines.

**The Conversion Rule:** Parquet requires static, non-nested schemas. To bypass this constraint, the code applies a serialization step: heavy nested items (like asset arrays, entity maps, and score maps) are dynamically flattened into flat JSON string tracks (`entities_json`, `style_analysis_json`). Heavy textual contents (`html`, `markdown`) are explicitly dropped from this matrix to maximize file efficiency.

**Compression Benefit:** Uses highly optimized Snappy columnar compression libraries to ensure final storage dimensions are compressed to under 30% of standard equivalent JSON formats.

---

## Sunday Evening Diagnostic Lab & Challenges

To finish your study plan and verify your practical understanding of how Nexora manages memory, async data processing, and error conditions, review these architecture checkpoints.

### Self-Interrogation Quiz

#### Memory Management

**Question:** Why is it absolutely required to wrap browser operations inside an explicit `try...finally: await browser.close()` architecture?

**Answer Summary:** If an extraction failure occurs mid-execution and the browser shutdown step is bypassed, headless Chromium execution processes remain silently active in your machine's background memory, leaking RAM until the server encounters an out-of-memory lockup.

#### Data Typing

**Question:** Why do we explicitly pass heavy text collections (`html`, `markdown`) out of the dictionary matrix before invoking PyArrow Parquet table compilation?

**Answer Summary:** Parquet is optimized for fast, columnar structural records. Storing arbitrary-length long bulk text strings inside narrow columns undermines the compression gains of the binary structure and causes excessive memory row allocation during downstream dataset analysis.

#### Data Flows

**Question:** If you notice that your analytical Parquet export directory contains empty collections, but your SQLite database tracking records are displaying records normally, which pipeline priorities are malfunctioning?

**Answer Summary:** The pipeline sequence layout proves that priority stages 110 through 165 executed successfully. The breakdown is isolated exclusively to Priority 450 (ParquetExportPipeline), likely caused by a schema data-type mismatch when converting nested list tracks using the PyArrow data engine.

---

## Where to Start Right Now

1. Open your physical notebook to a fresh page and draw the Pipeline Factory Line (110 → 160 → 165 → 450).
2. Open `Phase_4A.md` in your editor and copy down the explicit field map for `NexoraUnifiedRecord` into your notebook by hand.
3. Run a baseline command test from your terminal to verify your pipeline execution priority setup works without any framework dependencies:

```bash
scrapy crawl nexora_spider -a url="https://example.com"
```

4. Verify that `./data/nexora_metadata.db` and `./output/parquet/` are populated correctly on your file system.

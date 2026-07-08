# 🗺️ Nexora Mastery Weekend: Step-by-Step Execution Plan

Save this file directly as `NEXORA_WEEKEND_PLAN.md` in your project folder. Use it as your tracker as you fill out your physical notebook.

---

## 🗓️ TONIGHT (FRIDAY NIGHT): THE ENTRY GATE & INGESTION
**Focus:** Phase A (Ingestion Trigger) & Phase B (Message Queueing Status)
**Target Code Units:** `app/main.py` (or your entry point file) and `items.py`

### 📋 What to check for in the code:
1. Open your main API file and locate the `POST /crawl` route.
2. Find the line executing `loop.run_in_executor()`. Ensure you see how it encapsulates the synchronous `CrawlerProcess()`.
3. Open `items.py` and verify the exact string keys match your schema parameters.

### ✍️ Notebook Configuration:
* **Left Page:** Draw an entry gateway labeled `POST /crawl`. Map a line leading directly into a thread executor boundary box (`loop.run_in_executor`).
* **Right Page:** Copy the four structural zones of your `Item` schema (Identity, Refinement, Assets, Placeholders). Write this clear consequence down:
  > `[WHY IT MATTERS]:` Scrapy is fundamentally synchronous when running its core processing loops. `loop.run_in_executor()` prevents the FastAPI event loop from completely freezing. Without it, the entire API server drops offline and rejects traffic whenever a crawl starts.

---

## 🗓️ SATURDAY MORNING: THE NETWORK FILTER & MIDDLEWARES
**Focus:** Phase C (Active Crawling & Fetching Downloader Middlewares)
**Target Code Units:** `crawler/settings.py` and `middlewares/dynamic_detection.py`

### 📋 What to check for in the code:
1. Open `settings.py` and locate the `DOWNLOADER_MIDDLEWARES` dictionary matrix. Verify the priority integer order (`50` to `700`).
2. Open `middlewares/dynamic_detection.py` and analyze the exact logic handles for the text density check (`<5%`) and script ratio check (`>15%`).

### ✍️ Notebook Configuration:
* **Left Page:** Draw a sequence of five defensive walls in a top-down column layout: 
  `50 (UserAgent)` ──► `100 (ContentType)` ──► `541/542 (Playwright / Dynamic)` ──► `550 (Cleanup)` ──► `700 (Backoff)`.
* **Right Page:** Document the precise criteria used to trigger a browser fallback:
  1. Detects anti-bot indicators.
  2. Text density is lower than 5%.
  3. Total body contents fall under 200 characters with script ratios above 15%.
  > `[WHY IT MATTERS]:` Running headless Chromium instances through Playwright requires heavy CPU allocations. The `DynamicDetectionMiddleware` acts as an efficiency checkpoint. It restricts browser launching only to JavaScript-heavy sites, processing raw HTML text over static connection instances to maximize scraping velocity.

---

## 🗓️ SATURDAY AFTERNOON: THE PIPELINE ASSEMBLY LINE (100 → 160)
**Focus:** Phase D (Pipeline Processing Chain - First Half)
**Target Code Units:** `pipelines/extraction.py`, `pipelines/markdown_pipeline.py`

### 📋 What to check for in the code:
1. Locate the `process_item` functions for `NexoraExtractionPipeline` (100) and `MarkdownExtractionPipeline` (110).
2. Look for the invocation of `calculate_fingerprint()` at priority 100.
3. Check the token reduction calculation variable formula at priority 110.

### ✍️ Notebook Configuration:
* **Left Page:** Draw an Input-Transformation-Output (ITO) diagram showing raw HTML changing into clean Markdown text.
* **Right Page:** Document why priority order must be strictly preserved:
  * **Priority 100:** Pulls baseline metadata, fingerprints text using SimHash, and handles language profiles.
  * **Priority 110:** Runs reader-mode extractions to drop menus/footers, and isolates multimedia targets via `MultimodalAssetExtractor`.
  * **Priority 160:** Fallback checker. Enforces consistent dictionary keys across all processed records.
  > `[WHY IT MATTERS]:` Data transformation requires a strict order of operations. Priority 110 needs the raw text isolated by priority 100, and downstream metrics trackers rely on the fixed structure verified by priority 160.

---

## 🗓️ SUNDAY: STORAGE EXPORTS & FLUSHING TO DISK
**Focus:** Phase D (Pipelines 165 & 450) & Phase E (Storage Destinations)
**Target Code Units:** `storage/local_sqlite.py`, `storage/parquet_export.py`

### 📋 What to check for in the code:
1. Open `local_sqlite.py` and inspect the tracking data insert script method (`insert_page()`).
2. Open `parquet_export.py` and locate the schema flattening logic. Ensure you see the `json.dumps()` conversion step applied to nested dictionaries.
3. Locate where `html` and `markdown` variables are explicitly dropped before writing the row table to disk.

### ✍️ Notebook Configuration:
* **Left Page:** Draw a fork split leading to two separate storage bins: `SQLite Metadata` and `Parquet Analytical Storage`.
* **Right Page:** Write down the distinct technical design criteria for each storage layer:
  * **SQLite Database:** Stores immediate index lookups, crawling status reports, and execution titles.
  * **Parquet File Datasets:** Compresses large analytical data blocks row-by-row into Snappy binary files. Drops long raw HTML string contents to maintain low memory constraints during machine learning passes.
  > `[WHY IT MATTERS]:` Relational databases degrade rapidly when storing massive uncompressed raw text elements. Splitting data into fast operational indices (SQLite) and structured analytical files (Parquet) ensures fast queries while cutting storage costs by 70%.
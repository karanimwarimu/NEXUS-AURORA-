# Repo walkthrough plan (Phase 2 crawler + Extractor)

## Information gathered
- Read and reviewed:
  - `Crawler/nexora_crawler/spiders/nexora_spider.py`
  - `Crawler/nexora_crawler/items.py`
  - `Crawler/nexora_crawler/middlewares.py`
  - `Crawler/nexora_crawler/pipelines.py`
  - `Crawler/nexora_crawler/settings.py`
  - `Extractor/parser.py`
  - `Extractor/cleaner.py`
  - `Crawler/TODO.md`
  - `Crawler/phase2_crawler.md`
  - `requirements.txt`
- Identified current architecture:
  - Spider only fetches page HTML (no extraction in spider)
  - Pipeline 100 extracts with BS4 + Trafilatura
  - Pipeline 150 extracts visual design styles
  - Pipeline 200 exports JSON/CSV per page to `output/pages/`
  - Pipeline 300 appends a row into `output/master_dataset.csv`
- Crawl discipline already implemented:
  - Default is seed-only (`DEPTH_LIMIT = 0`, spider enforces `_depth`)
  - Link-follow only when crawl mode is enabled
  - Same-domain filtering
  - URL canonicalization + tracking param stripping
  - Sitemap discovery is opt-in (only when crawl mode enabled)
- Active “phase 3” support is stubbed (Playwright middleware exists but is not enabled in settings).

## Plan
1. Walk remaining Extractor modules that are referenced but not yet read:
   - `Extractor/Beautifulsoup_extractor.py`
   - `Extractor/Trafilatura_extractor.py`
   - `Extractor/style_extractor.py`
   - `Extractor/Web_fetcher.py`
   - `Extractor/Save_web_exctract.py`
   - `Extractor/extractor_prototype.py`
   - `Extractor/main.py`
2. Review any cross-module contracts:
   - Confirm output keys from extractor functions match what pipelines expect.
   - Confirm `extract_styles()` output schema matches `NexoraDatasetPipeline.MASTER_FIELDS`.
3. Re-check `Crawler/` integration:
   - `scrapy.cfg`
   - `requirements.txt` for version compatibility.
4. Produce a consolidated checklist for continuation (bugs, TODOs, next steps).

## Dependent files to be read next
- `Extractor/Beautifulsoup_extractor.py`
- `Extractor/Trafilatura_extractor.py`
- `Extractor/style_extractor.py`
- `Extractor/Web_fetcher.py`
- `Extractor/Save_web_exctract.py`
- `Extractor/extractor_prototype.py`
- `Extractor/main.py`
- `Crawler/scrapy.cfg`

## Followup steps
- Run a dry crawl (single-page) to validate pipeline output and ensure no missing fields crash the export/dataset pipelines.
- If needed, install missing dependencies (e.g., extruct, fasttext model) in the local environment.



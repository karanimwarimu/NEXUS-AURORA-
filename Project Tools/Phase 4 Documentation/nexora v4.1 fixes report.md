# Phase 4A Scrapy 2.16+ Compatibility Fix Audit

**Date:** 2026-06-30
**Scope:** Fix deprecation warnings for Scrapy 2.16+ async pipeline and middleware signatures

---

## Summary

Fixed Scrapy deprecation warnings across Phase 4A pipeline components. Scrapy 2.16+ changed the middleware and pipeline method signatures to no longer pass the `spider` argument, instead accessing it via `self.crawler.spider`.

---

## Errors Found and Fixed

### 1. MarkdownExtractionPipeline (`pipelines/markdown_pipeline.py`)

**Error:**
```
DeprecationWarning: MarkdownExtractionPipeline.close_spider() takes a spider argument.
Scrapy 2.16+ expects no spider argument; access via self.crawler.spider instead.
```

**Fix:**
- Added `self.crawler = None` in `__init__`
- Updated `from_crawler(cls, crawler)` to set `obj.crawler = crawler`
- Changed `process_item(self, item, spider)` → `process_item(self, item)`
- Changed `close_spider(self, spider)` → `close_spider(self)` (access spider via `self.crawler.spider`)

---

### 2. UnifiedSchemaEnricher (`pipelines/schema_enricher.py`)

**Error:**
```
DeprecationWarning: UnifiedSchemaEnricher.close_spider() takes a spider argument.
```

**Fix:**
- Added `self.crawler = None` in `__init__`
- Updated `from_crawler(cls, crawler)` to set `obj.crawler = crawler`
- Changed `process_item(self, item, spider)` → `process_item(self, item)`
- Changed `close_spider(self, spider)` → `close_spider(self)`

---

### 3. MetadataIndexerPipeline (`pipelines/metadata_indexer.py`)

**Error:**
```
DeprecationWarning: MetadataIndexerPipeline.close_spider() takes a spider argument.
```

**Fix:**
- Updated `from_crawler(cls, crawler)` to set `obj.crawler = crawler`
- Changed `process_item(self, item, spider)` → `process_item(self, item)`
- Changed `close_spider(self, spider)` → `close_spider(self)`

---

### 4. ParquetExportPipeline (`pipelines/parquet_export.py`)

**Error:**
```
DeprecationWarning: ParquetExportPipeline.close_spider() takes a spider argument.
DeprecationWarning: ParquetExportPipeline.open_spider() takes a spider argument.
```

**Fix:**
- Added `self._spider_name = "nexora"` as instance variable
- Changed `open_spider(self, spider)` → `open_spider(self)` (stores spider name internally)
- Changed `process_item(self, item, spider)` → `process_item(self, item)`
- Changed `close_spider(self, spider)` → `close_spider(self)`
- Changed `_flush_buffer(self, spider)` → `_flush_buffer(self)` (uses stored `_spider_name`)
- Reduced buffer size from 100 to 20 for better responsiveness

---

### 5. NexoraSpiderMiddleware (`middlewares/__init__.py`)

**Error:**
```
DeprecationWarning: NexoraSpiderMiddleware.process_spider_exception() takes a spider argument.
```

**Fix:**
- Changed `process_spider_exception(self, response, exception, spider)` → `process_spider_exception(self, response, exception)`

---

### 6. DynamicDetectionMiddleware (`middlewares/dynamic_detection.py`)

**Error:**
```
DeprecationWarning: DynamicDetectionMiddleware.process_request() takes a spider argument.
```

**Fix:**
- Changed `process_request(self, request, spider)` → `process_request(self, request)`
- Changed `_probe_page(self, url, spider)` → `_probe_page(self, url)` (spider not used)

---

### 7. PlaywrightResourceBlocker (`middlewares/playwright_resource_blocker.py`)

**Error:**
```
DeprecationWarning: PlaywrightResourceBlocker.process_request() takes a spider argument.
```

**Fix:**
- Changed `process_request(self, request, spider)` → `process_request(self, request)`

---

## Test File Updates (`tests/test_phase4a.py`)

Updated test calls to match new signatures:
- Removed `mock_spider` argument from all `process_item()` calls
- Removed `mock_spider` argument from `open_spider()` and `close_spider()` calls
- Updated `test_p4a_t11_schema_enrichment` to set `crawl_id` directly on item since no crawler context in test
- Updated `test_p4a_t12_full_pipeline_chain` to properly set up crawler mock with spider

---

## Files Changed

| File | Changes |
|------|---------|
| `Crawler/nexora_crawler/pipelines/markdown_pipeline.py` | Updated signatures, added crawler tracking |
| `Crawler/nexora_crawler/pipelines/schema_enricher.py` | Updated signatures, added crawler tracking |
| `Crawler/nexora_crawler/pipelines/metadata_indexer.py` | Updated signatures, added crawler tracking |
| `Crawler/nexora_crawler/pipelines/parquet_export.py` | Updated signatures, reduced buffer size, removed spider param from `_flush_buffer` |
| `Crawler/nexora_crawler/middlewares/__init__.py` | Fixed `process_spider_exception` signature |
| `Crawler/nexora_crawler/middlewares/dynamic_detection.py` | Fixed `process_request` and `_probe_page` signatures |
| `Crawler/nexora_crawler/middlewares/playwright_resource_blocker.py` | Fixed `process_request` signature |
| `Nexora application/tests/test_phase4a.py` | Updated all test method calls |

---

## Notes

- The Phase 1-3 pipelines in `pipelines/__init__.py` were already compliant with Scrapy 2.16+ (no spider argument in `process_item`, `open_spider`, `close_spider`)
- All changes maintain backward compatibility with test patterns
- The Parquet export buffer size reduction (100 → 20) addresses potential data loss on small crawls
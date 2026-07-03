# Phase 4A Implementation Guide

## Objective
This guide explains how to implement Phase 4A in the current Nexora codebase so that the system can move from raw HTML extraction to a richer, schema-aware ingestion layer.

## Phase 4A v4.2 scope limit (applies to this pass)
This implementation pass is intentionally limited to the Phase 4A storage and ingestion scope. The Phase 7 items that are relevant to 4A are retained only where they directly support the 4A data contract:

- Preserve the existing 100 → 160 → 165 → 450 → 500 → 600 pipeline ordering.
- Keep the local SQLite metadata store as the canonical relational index.
- Preserve Parquet export as a compressed analytical sink.
- Do not introduce Phase 7-only features such as vector stores, webhook delivery, or quota enforcement in this pass.

## Current reality check
Phase 4A is a strong design direction, but it is not a drop-in implementation for the current repository as-is.

The following items are still required before Phase 4A can be expected to work end-to-end:

1. Add the new Phase 4A pipeline modules and import paths.
2. Extend the item schema with Phase 4A fields.
3. Register the new pipelines in settings.
4. Install any missing dependencies such as `pandas` and `pyarrow`.
5. Align pipeline method signatures with the active Scrapy version.
6. Resolve path mismatches between the implementation spec and the actual repository layout.

## Target architecture
The intended Phase 4A flow is:

1. `NexoraExtractionPipeline` produces the baseline extracted item.
2. `MarkdownExtractionPipeline` converts HTML into clean Markdown.
3. `MultimodalAssetExtractor` extracts image/video metadata.
4. `UnifiedSchemaEnricher` applies defaults and a unified record structure.
5. `MetadataIndexerPipeline` stores metadata in SQLite.
6. `ParquetExportPipeline` exports compressed Parquet files.
7. Existing export and dataset pipelines continue to emit JSON/CSV summaries.

## Required file changes

### 1. Item schema update
Update [Nexora application/Crawler/nexora_crawler/items.py](Nexora%20application/Crawler/nexora_crawler/items.py) to add the following Phase 4A fields:

- `markdown`
- `markdown_word_count`
- `extraction_method`
- `token_reduction_pct`
- `video_assets`
- `total_images`
- `total_videos`
- `has_hero_image`
- `crawl_id`
- `timestamp`
- `domain`
- `entities`
- `price_change_delta`
- `style_analysis`
- `quality_scores`
- `website_type`

### 2. Create new pipeline modules
Create the following new modules under the crawler package:

- `nexora_crawler/pipelines/markdown_pipeline.py`
- `nexora_crawler/extractors/multimodal_extractor.py`
- `nexora_crawler/pipelines/schema_enricher.py`
- `nexora_crawler/pipelines/parquet_export.py`
- `nexora_crawler/pipelines/metadata_indexer.py`

### 3. Update settings
In [Nexora application/Crawler/nexora_crawler/settings.py](Nexora%20application/Crawler/nexora_crawler/settings.py), register the Phase 4A stages in the pipeline order:

- `NexoraExtractionPipeline`: 100
- `MarkdownExtractionPipeline`: 110
- `NexoraStylePipeline`: 150
- `UnifiedSchemaEnricher`: 160
- `MetadataIndexerPipeline`: 165
- `ParquetExportPipeline`: 450
- `NexoraExportPipeline`: 500
- `NexoraDatasetPipeline`: 600

### 4. Dependency installation
Install the missing packages needed for the Parquet path:

- `pandas`
- `pyarrow`

### 5. Validation checklist
Before claiming Phase 4A is complete, verify the following:

- Markdown extraction produces a non-empty `markdown` field.
- Images and videos are captured with metadata.
- Unified schema defaults are present for all records.
- Parquet files are written to `output/parquet/`.
- Metadata rows are inserted into the SQLite store.
- Existing Phase 3 export behavior still works without regressions.

## Expected risks and known caveats

### Likely integration issues
- Import paths in the spec may not match the live repository layout.
- The current Scrapy pipeline signatures may require adjustment.
- The item schema must be expanded before new fields can be written safely.
- Some Phase 4A components may overlap with existing extractors and should be carefully deduplicated.

### What should remain stable
- Existing Playwright routing logic should remain unaffected.
- Current per-page JSON and CSV outputs should continue to function.
- The master dataset should continue to append summary rows.

## Implementation recommendation
The guide is best used as a staged rollout plan rather than a single immediate patch.

The safest progression is:

1. Add the fields to the item schema.
2. Add the Markdown extraction stage.
3. Add schema enrichment.
4. Add metadata indexing.
5. Add Parquet export.
6. Run targeted regression tests.

## Final assessment
This is a workable implementation strategy for the current codebase, but it is not yet a fully ready-to-run solution until the schema, dependency, and layout issues are resolved.

# 🚀 NEXORA **v4.1.0** — Release Notes

## Release Title
**NEXORA v4.1.0 — Phase 4A: Storage & Multi-Format Ingestion Engine**

## Overview
This release introduces Nexora's Phase 4A storage infrastructure — a unified data ingestion and structural refinement layer that transforms raw HTML from the Scrapy pipeline (Phases 1-3) into clean, structured, multi-format outputs serving three downstream consumers: human analysts, ML pipelines, and Phase 4B RAG systems.

**Core principle:** *One crawl → multiple formats → one unified schema. No data is lost; every field is traceable back to its source.*

---

## What's New in Phase 4A

### 🔧 Pipeline Components

#### 1. MarkdownExtractionPipeline (Priority 110)
- Converts raw HTML to clean, LLM-ready Markdown via Trafilatura
- Intelligent boilerplate removal (strips nav, footers, cookie banners, ads)
- Preserves tables (pipe-delimited), links, structured content
- Token reduction metric: typically >50-80% reduction vs raw HTML
- Graceful fallback chain: Trafilatura → clean_text → error fallback

#### 2. MultimodalAssetExtractor (Inline)
- Isolates image references with structured metadata: `src`, `alt`, `width`, `height`, `loading`
- `srcset` resolution — picks highest resolution candidate
- Hero image heuristic — first large image (≥600px width) flagged
- Video detection: `<video>` tags, YouTube/Vimeo/Dailymotion `<iframe>` embeds
- NO binary downloads — metadata-only capture
- Integrated directly into MarkdownExtractionPipeline (all 3 code paths: success, fallback, error)

#### 3. UnifiedSchemaEnricher (Priority 160)
- Enforces the `NexoraRecord` unified schema on every item
- Auto-populates: `crawl_id`, `timestamp` (ISO 8601 UTC), `domain`
- Defaults for: `entities`, `style_analysis`, `quality_scores` (never missing)
- Website type classification heuristic:
  - `/product`, `/item`, `/shop`, `/store`, `/cart` → **e-commerce**
  - Title contains "blog", "article", "post", "news" → **blog**
  - `/docs`, `/documentation`, `/api`, `/guide` → **documentation**
  - Long Markdown with headings → **article**
  - Fallback → **unknown**

#### 4. MetadataIndexerPipeline (Priority 165)
- Scrapy pipeline wrapper around SQLite `MetadataStore`
- Persists every crawled page to relational database
- Stats tracking: items indexed vs failed

#### 5. ParquetExportPipeline (Priority 450)
- Buffered export (100 rows per flush) to compressed Apache Parquet
- Supported compression: snappy (default), gzip, brotli, zstd
- Flattens nested structures to JSON strings for columnar storage
- Removes heavy text fields (raw HTML, markdown) — stored separately
- File pattern: `{spider_name}_{timestamp}_{counter:04d}.parquet`
- Typical compression: <30% of equivalent JSON file size

### 🗄️ Storage Layer

#### SQLite MetadataStore (`storage/local_sqlite.py`)
| Feature | Details |
|---------|---------|
| Tables | `pages` (15+ columns), `crawl_jobs` |
| Indexes | domain, crawl_id, website_type, timestamp, language |
| Queries | `query_by_domain(domain, limit)`, `query_by_crawl_id(crawl_id)`, `get_stats()` |
| Insert | `INSERT OR REPLACE` — idempotent by URL |
| Path | `./data/nexora_metadata.db` (auto-created) |

#### Unified Schema Dataclass (`storage/models.py`)

```python
@dataclass
class NexoraRecord:
    # Identity: record_id, crawl_id, url, domain, title, timestamp
    # Content: raw_html, markdown_content, clean_text
    # Metadata: website_type, language, status_code, playwright_used
    # Structural: style_analysis, quality_scores, structured_schema
    # Entities: entities (prices, tickers, products, etc.), price_change_delta
    # Multimodal: image_assets, video_assets
    # AI Enrichment (Phase 4B): ai_summary, ai_tags, embedding, chunk_ids
```

#### Abstract Base Classes (`storage/base.py`)
- `BaseMetadataStore` — 9 abstract methods (connect, close, save_record, get_record, search, count, save_job, update_job, get_job)
- `BaseVectorStore` — 8 abstract methods (connect, close, add_chunks, search, search_by_text, delete_chunks, get_collection_stats, count)
- Cloud-ready: designed for Supabase PostgreSQL + pgvector + S3 migration

### 📋 Items & Configuration Updates

#### `items.py` — 19 New Fields

| Section | Fields Added |
|---------|-------------|
| Markdown & Content | `markdown`, `markdown_word_count`, `extraction_method`, `token_reduction_pct` |
| Multimodal | `video_assets`, `total_images`, `total_videos`, `has_hero_image` |
| Unified Schema | `crawl_id`, `timestamp`, `domain`, `entities`, `price_change_delta`, `style_analysis`, `quality_scores`, `website_type` |
| Phase 4B Reserved | `ai_summary`, `ai_tags`, `ai_embedding`, `chunk_count`, `chunk_ids`, `has_embedding` |

#### `settings.py` — Complete Pipeline Chain

```
Priority  Pipeline                       Phase
100       NexoraExtractionPipeline       1-2
110       MarkdownExtractionPipeline     4A (NEW)
150       NexoraStylePipeline            2
160       UnifiedSchemaEnricher          4A (NEW)
165       MetadataIndexerPipeline        4A (NEW)
250       Phase 4B pipelines             Future
450       ParquetExportPipeline          4A (NEW)
500       NexoraExportPipeline           1
600       NexoraDatasetPipeline          1
```

### 🧪 Testing

#### 18-Test Phase 4A Suite
| ID | Scenario | Result |
|:--:|---|---|
| P4A-T01 | Markdown extraction + token reduction | ✅ PASS |
| P4A-T02 | Boilerplate removal (cookie policy stripped) | ✅ PASS |
| P4A-T03 | Table preservation (pipe-delimited) | ✅ PASS |
| P4A-T04 | Image extraction (src, alt, dimensions, hero) | ✅ PASS |
| P4A-T05 | Video extraction (MP4, YouTube, Vimeo) | ✅ PASS |
| P4A-T06 | Unified schema defaults (all 3 dicts present) | ✅ PASS |
| P4A-T07 | Website classification (6 types) | ✅ PASS |
| P4A-T08 | Parquet export readable by pandas | ✅ PASS |
| P4A-T09 | Parquet compression (< 30% of JSON) | ✅ PASS |
| P4A-T10 | SQLite insert + query by domain/crawl_id | ✅ PASS |
| P4A-T11 | Schema enrichment (defaults populated) | ✅ PASS |
| P4A-T12 | Full pipeline chain (no regression) | ✅ PASS |
| Edge | Empty HTML fallback | ✅ PASS |
| Edge | Clean text fallback | ✅ PASS |
| Edge | Empty multimodal HTML | ✅ PASS |
| Edge | None video input | ✅ PASS |
| Edge | Multiple crawl_id query | ✅ PASS |
| Edge | get_stats counts | ✅ PASS |

**Pass Rate:** 100% (18/18 tests)  
**Test File:** `tests/test_phase4a.py`  
**Fixture:** `tests/_fixtures/html/article_with_multimodal.html`  
**Audit Report:** `output/audit/phase4a_test1_report.md`

---

## Data Flow

```
Raw HTML from Scrapy Pipeline
         │
         ▼
[100] NexoraExtractionPipeline     → BS4 + Trafilatura extraction
         │
         ▼
[110] MarkdownExtractionPipeline   → HTML → clean Markdown
      └─ MultimodalAssetExtractor  → Image/video metadata (inline)
         │
         ▼
[150] NexoraStylePipeline          → CSS framework, theme, fonts
         │
         ▼
[160] UnifiedSchemaEnricher        → Defaults + classification
         │
         ▼
[165] MetadataIndexerPipeline      → SQLite persistence
         │
         ▼
[450] ParquetExportPipeline        → Compressed columnar files
         │
         ▼
[500] NexoraExportPipeline         → JSON + CSV per page
[600] NexoraDatasetPipeline        → Master dataset CSV
         │
         ▼
    ┌──────┬──────┬──────┬──────┐
    │  MD  │JSON  │CSV   │Parq. │SQLite│
    │(LLM) │      │      │(ML)  │(Meta)│
    └──────┴──────┴──────┴──────┘
```

---

## Files Added/Modified

### New Files
| File | Purpose |
|------|---------|
| `Crawler/nexora_crawler/pipelines/markdown_pipeline.py` | Markdown extraction pipeline |
| `Crawler/nexora_crawler/pipelines/schema_enricher.py` | Unified schema enforcer |
| `Crawler/nexora_crawler/pipelines/metadata_indexer.py` | SQLite metadata persistence |
| `Crawler/nexora_crawler/pipelines/parquet_export.py` | Compressed Parquet export |
| `Extractor/multimodal_extractor.py` | Image/video asset extraction |
| `Crawler/nexora_crawler/storage/base.py` | Abstract storage interfaces |
| `Crawler/nexora_crawler/storage/models.py` | Unified schema dataclass |
| `Crawler/nexora_crawler/storage/local_sqlite.py` | SQLite MetadataStore implementation |
| `tests/test_phase4a.py` | 18-test Phase 4A suite |
| `tests/_fixtures/html/article_with_multimodal.html` | HTML test fixture |
| `output/audit/phase4a_test1_report.md` | Test audit report |

### Modified Files
| File | Changes |
|------|---------|
| `Crawler/nexora_crawler/items.py` | +19 Phase 4A fields (markdown, multimodal, unified schema, AI placeholders) |
| `Crawler/nexora_crawler/settings.py` | Pipeline chain reordered (100→600), duplicate removed, Phase 4A settings added |
| `Crawler/nexora_crawler/pipelines/__init__.py` | No changes (Phase 1-3 pipelines unaffected) |
| `README.md` | Updated to v4.1.0 with Phase 4A docs |
| `REPOSITORY_STRUCTURE.md` | Updated with Phase 4A components |

---

## Performance Characteristics

| Metric | Value |
|--------|:-----:|
| Markdown token reduction | >50% (typical: 65-85%) |
| Parquet compression vs JSON | <30% of JSON size |
| Parquet buffer flush | Every 100 rows |
| SQLite insert | ~1ms per page |
| SQLite indexes | 5 (domain, crawl_id, website_type, timestamp, language) |
| Test suite execution | ~7 seconds (18 tests) |
| No regression | Phase 3 tests unaffected |

---

## Dependencies

| Package | Required For | New? |
|---------|-------------|:----:|
| `trafilatura` | Markdown extraction | Existing |
| `pandas` | Parquet DataFrame construction | **NEW** |
| `pyarrow` | Parquet file writing | **NEW** |
| `beautifulsoup4` | Multimodal asset extraction | Existing |
| `sqlite3` | Metadata store | stdlib |

---

## Known Limitations
1. Phase 4B (AI enrichment, embeddings, RAG chunking) is not yet implemented — fields are reserved as placeholders
2. Parquet export requires `pandas` and `pyarrow` — must be installed separately
3. The `entities` field uses heuristic extraction (no NLP) — Phase 4B will add LLM-based entity extraction
4. MetadataStore currently local-only — cloud Supabase adapter is designed but unimplemented

---

## Next Up: Phase 4B
- AI summarization (LLM-generated 2-3 sentence summaries)
- Semantic chunking for RAG context windows
- Vector embeddings (text-embedding-ada-002 or local models)
- ChromaDB / pgvector integration
- Full-text search via SQLite FTS5

---

## Installation

```bash
# Install new Phase 4A dependencies
pip install pandas pyarrow

# Run Phase 4A test suite
cd "Nexora application"
python -m pytest tests/test_phase4a.py -v
```

---

## Requirements
- Python 3.11+
- Scrapy 2.16+
- pandas 2.0+
- pyarrow 10+
- trafilatura 1.6+
- beautifulsoup4 4.12+
- SQLite3 (built-in)

---

*Release Date: 2026-06-30*
*Previous Release: v3b v0.4.0 (Phase 3 — Dynamic Detection Middleware)*
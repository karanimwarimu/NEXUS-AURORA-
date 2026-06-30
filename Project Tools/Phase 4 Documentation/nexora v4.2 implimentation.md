# Nexora Phase 4A vs Phase 7 Specification Review

## Current Phase 4A Implementation Status

The Phase 4A implementation is well-structured but incomplete compared to the Phase 7 specification. Let me break down what exists versus what's specified:

---

## Storage Layer - Current State Analysis

### What exists (`nexora_crawler/storage/`):

- **base.py** - Abstract classes exist but are synchronous (not async as specified in Phase 7)
- **models.py** - Has NexoraUnifiedRecord dataclass but uses different field naming (`markdown_content` vs `markdown`)
- **local_sqlite.py** - MetadataStore implemented correctly with SQLite

### Phase 7 Requirements (Missing):

- Async methods (`initialize`, `close`, `save_record`, `get_record`, etc.) are defined as abstract but the SQLite implementation uses sync SQLite
- BaseVectorStore exists but no implementation - this is Phase 4B/7 feature
- The Phase 7 spec uses `nexora_crawler/vector_store/` as the path (vs `storage/`)

---

## Pipeline Chain - Alignment Check

| Priority | Current Implementation | Phase 7 Spec | Status |
|----------|----------------------|-------------|--------|
| 100 | NexoraExtractionPipeline | ✓ | Match |
| 110 | MarkdownExtractionPipeline | ✓ | Match |
| 150 | NexoraStylePipeline | ✓ | Match |
| 160 | UnifiedSchemaEnricher | ✓ | Match |
| 165 | MetadataIndexerPipeline | ✓ | Match |
| 250 | Phase 4B pipelines (empty) | VectorIndex | Missing |
| 280 | Not implemented | SchemaExtractionPipeline | Missing |
| 450 | ParquetExportPipeline | ✓ | Match |

---

## Critical Gaps Identified

### Gap 1: Vector Store Implementation

- **Required for Phase 7:** `nexora_crawler/vector_store/pgvector_store.py`
- **Current state:** Only `base.py` abstract class exists (synchronous)
- **Missing:** VectorRecord, SearchQuery, SearchResult dataclasses, async methods

### Gap 2: Job Type Registry

- **Required for Phase 7:** `nexora_crawler/jobs/registry.py`
- **Current state:** No job abstraction system
- **Missing:** Celery integration, generic job dispatch, handler registration

### Gap 3: Schema Extraction Pipeline

- **Required for Phase 7:** `nexora_crawler/pipelines/schema_extraction_pipeline.py` (priority 280)
- **Current state:** Not implemented
- **Missing:** LiteLLM integration, Pydantic model generation from JSON Schema

### Gap 4: Webhook System

- **Required for Phase 7:** Complete webhook subsystem
- **Missing:** API endpoints, delivery worker, Redis pub/sub, database tables

### Gap 5: Quota Engine

- **Required for Phase 7:** `nexora_crawler/entitlements/engine.py`
- **Missing:** rate limiting, workspace quotas, soft/hard quota enforcement

---

## Migration Path Required

To align Phase 4A with Phase 7 specifications, the following structural changes are needed:

```
nexora_crawler/
├── storage/                    # Keep existing (SQLite metadata)
│   ├── base.py                 # Enhance to async interface
│   ├── models.py               # Align field names
│   └── local_sqlite.py
└── vector_store/               # NEW - per Phase 7 spec
    ├── base.py                 # Async BaseVectorStore + dataclasses
    ├── factory.py              # Backend selection from env
    ├── pgvector_store.py       # Supabase/pgvector implementation
    ├── chroma_store.py         # Backward compatibility
    └── qdrant_store.py         # Scale option
```

---

## Storage Architecture Recommendations

### Immediate Actions for Phase 4A → 7 alignment:

1. **Add Vector Store Directory with async interface:**
   - Create `nexora_crawler/vector_store/` directory
   - Implement VectorRecord, SearchQuery, SearchResult dataclasses
   - Make BaseVectorStore methods async (add `async` keyword)

2. **Enhance Job Abstraction:**
   - Create JobTypeRegistry for crawl types
   - Add `/v1/jobs` endpoint pattern
   - Integrate with existing Celery path (or prepare for it)

3. **Add Schema Extraction Pipeline:**
   - Implement priority 270-280 for structured extraction
   - Add LiteLLM dependency and embedding engine

4. **Quota Integration Points:**
   - Add quota checking to MetadataIndexerPipeline
   - Add rate limiting middleware for API

---

## Integration Points Map

```
┌─────────────────────────────────────────────────────────────┐
│                    NEXORA Phase 4A → 7                        │
├─────────────────────────────────────────────────────────────┤
│  Storage:                                                   │
│    metadata_store.db ──→ Already working (SQLite)          │
│    vector_store/ ──→ MISSING (needs pgvector/async)        │
│    parquet/ ──→ Already working                             │
│                                                             │
│  Pipelines:                                                 │
│    100-165 ──→ OK (content extraction)                    │
│    250-280 ──→ MISSING (vector + schema extract)           │
│                                                             │
│  API Layer:                                                 │
│    /crawl/* ──→ OK (basic endpoint)                        │
│    /v1/search/* ──→ MISSING                                │
│    /v1/extract/* ──→ MISSING                               │
│    /v1/webhooks/* ──→ MISSING                              │
│    /v1/jobs/* ──→ MISSING                                  │
└─────────────────────────────────────────────────────────────┘
```

---

## Data Flow Enhancement Required

### Current flow terminates at Parquet/JSON. Phase 7 requires:

**Current (4A):**
```
HTML → Markdown → SQLite → Parquet
```

**Required (7):**
```
HTML → Markdown → Vector Embeddings → Vector Store → Search API
```

### Steps to implement:

1. Add chunking logic (per-page to multiple text chunks)
2. Add embedding generation (text → vector)
3. Persist to vector store
4. Expose `/v1/search/semantic` and `/v1/search/hybrid` endpoints

---

## Configuration Updates Needed

### Add to `settings.py`:

```python
# Phase 7 additions
NEXORA_VECTOR_BACKEND = "pgvector"  # or "chroma" for dev
NEXORA_DATABASE_URL = "postgresql://..."
NEXORA_EMBEDDING_DIM = 768
NEXORA_SCHEMA_EXTRACTION_ENABLED = False
NEXORA_SCHEMA_EXTRACTION_MODEL = "gpt-4o-mini"
```

---

## Summary

Phase 4A is a solid foundation but Phase 7 requires significant additions:

| Component | Status | Action Required |
|-----------|--------|-----------------|
| SQLite MetadataStore | ✅ Complete | None |
| Parquet Export | ✅ Complete | None |
| Markdown Pipeline | ✅ Complete | None |
| Vector Store | ❌ Missing | Implement `vector_store/` with async interface |
| Schema Extraction | ❌ Missing | Add `schema_extraction_pipeline.py` |
| Job Registry | ❌ Missing | Create `jobs/registry.py` |
| Webhooks | ❌ Missing | Full subsystem needed |
| Quotas | ❌ Missing | Add `entitlements/engine.py` |

The Phase 4A codebase is well-organized and production-ready for its current scope, but achieving the "industry-standard" maturity called out in Phase 7 requires addressing the six gaps identified in the specification.
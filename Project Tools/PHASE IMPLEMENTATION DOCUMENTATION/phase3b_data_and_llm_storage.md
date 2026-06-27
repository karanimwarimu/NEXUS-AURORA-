# ⚠️ PHASE 3B — DEPRECATED AND MERGED INTO PHASE 4A

## Status: SUPERSEDED

The old Phase 3B design (`chunk → embed → ChromaDB → dual SQLite`) contained **duplicate embedding generation** and **inconsistent database architecture**. It has been replaced by the unified Phase 4A → 4B → 4C pipeline.

## What Changed

| Old Phase 3B | New Home | Reason |
|-------------|----------|--------|
| `pipelines/llm_ingestion_pipeline.py` | Phase 4A `pipelines/metadata_indexer.py` | Embedding moved to Phase 4B single engine |
| `storage/vector_store.py` | Phase 4B `ai/embedding_engine.py` + `storage/chroma_vector.py` | Abstracted behind `BaseVectorStore` interface |
| `storage/metadata_store.py` | Phase 4A `pipelines/metadata_indexer.py` + `storage/local_sqlite.py` | Uses unified enriched schema |
| `storage/models.py` | Phase 4A `storage/models.py` (rewritten) | Now `NexoraRecord` + `NexoraChunk` with full enriched schema |
| `scripts/check_ollama_embedding.py` | Phase 4B diagnostic tool | Single embedding engine via LiteLLM |

## Migration Path

See the following files for the new architecture:
- **[Phase 4A](./PHASE_4_AI_ANALYTICS.md#phase-4a-core-storage--multi-format-ingestion-engine)** — Enriched schema, multi-format export, metadata store
- **[Phase 4B](./PHASE_4_AI_ANALYTICS.md#phase-4b-deduplicated-ai-enrichment--rag-pipeline)** — Single embedding engine, structural chunker, vector DB indexing
- **[Phase 4C](./PHASE_4_AI_ANALYTICS.md#phase-4c-api-task-distribution--sdk-infrastructure)** — FastAPI, async tasks, CLI, SDK

## Critical Guardrail

> **Do NOT implement the old Phase 3B design.** The new architecture uses a single embedding engine (`ai/embedding_engine.py`) via LiteLLM for ALL embedding generation — never direct HTTP calls to Ollama.
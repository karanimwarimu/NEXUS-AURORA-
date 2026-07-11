# NEXUS AURORA — Release Notes v4.2.1

**Release date:** 2026-07-12
**Codename:** Nexora
**Status:** Phase 4B — AI Enrichment & Vector Indexing (complete)

---

## Overview

v4.2.1 completes **Phase 4B**: the crawler now enriches every crawled page with an AI
summary, topic tags, and a sentence-transformers embedding, chunks the Markdown into
semantic pieces, and indexes those chunks into a vector store (Chroma locally, pgvector/
Supabase in production). The embedding path was reworked to use the Hugging Face router's
**legacy `feature-extraction` endpoint**, because the router's OpenAI-compatible
`/v1/embeddings` does **not** support sentence-transformers models.

This release also fixes two critical bugs that silently prevented any vector from being
stored, and switches the default embedding model to the fast, free
`sentence-transformers/all-MiniLM-L6-v2` (384-dim).

---

## What's New

| Feature | Description |
|---------|-------------|
| **AIEnrichmentPipeline** (250) | Per-page LLM summary (2-3 sentences) + 3-5 topic tags, plus a page-level embedding. |
| **UnifiedEmbeddingEngine** | Provider-aware embedding generator (`AI_Utilities/embedding_engine.py`). `huggingface` → HF router legacy `feature-extraction` endpoint; any other provider → LiteLLM `aembedding`. |
| **StructuralChunkingPipeline** (260) | Markdown → ~512-token semantic chunks; each chunk inherits the page `ai_summary`, `ai_tags`, and `ai_embedding`. |
| **VectorIndexPipeline** (270) | Converts `NexoraChunk` → `VectorRecord` and persists via `BaseVectorStore`. |
| **Vector Store Layer** | `BaseVectorStore` contract + `ChromaVectorStore` (local) + `PgVectorStore` (Supabase/Postgres), selected by `build_vector_store()`. |
| **Default embedding model** | `sentence-transformers/all-MiniLM-L6-v2` (384-dim) — fast, free, serverless via the HF router. |
| **Verification scripts** | `test_ai.py`, `test_ai_direct_hf.py` (connectivity), `test_vector_store.py` (proves embeddings are stored & retrieveable). |
| **Model-switch guide** | `Project Tools/switch_model_guide.md` — change model / provider / backend with zero code changes. |

---

## Bug Fixes

- **`NexoraChunk.source_type` missing attribute** — `VectorIndexPipeline` read
  `chunk.source_type`, but the dataclass had no such field, raising `AttributeError` on
  every page and silently dropping all indexing. Added the `source_type` field
  (defaults to `"chunk"`).
- **`ChromaVectorStore.add()` metadata crash** — the code did `**_json(r.metadata)`,
  but `_json()` returns a **string**, so `**"..."` raised `TypeError` on every `add()`.
  Rewrote the metadata builder to unpack the dict directly and stringify list/dict
  fields (e.g. `ai_tags`, `heading_chain`) so Chroma (scalar-only metadata) accepts them.
- **`.env` / `settings.py` drift** — `.env` still pointed at the decommissioned
  `api-inference.huggingface.co` host and `all-mpnet-base-v2`/768. Synced `.env` to
  `settings.py` (`router.huggingface.co/v1`, `all-MiniLM-L6-v2`, `384`) to prevent a
  future mismatch (notably on the pgvector switch, where the factory reads dims from env).

---

## Configuration Changes

Default AI / vector settings in `settings.py` (overridable in `.env`):

| Setting | v4.1.0 | v4.2.1 |
|---------|--------|--------|
| `NEXORA_AI_PROVIDER` | — | `huggingface` |
| `NEXORA_AI_MODEL` | — | `Qwen/Qwen2.5-7B-Instruct` |
| `NEXORA_AI_EMBEDDING_MODEL` | — | `sentence-transformers/all-MiniLM-L6-v2` |
| `NEXORA_EMBEDDING_DIM` | — | `384` |
| `NEXORA_VECTOR_BACKEND` | — | `chroma` |
| `NEXORA_VECTOR_INDEX_ENABLED` | — | `True` |
| `NEXORA_CHROMA_PATH` | — | `./data/chroma` |

---

## Upgrade / Migration Notes

- **Wipe the vector store on a model/dimension change.** The Chroma HNSW index bakes in
  the vector dimension. If you switch to a model with a different dim, delete
  `data/chroma` before re-crawling, or `add()`/`search()` will fail.
- **Switching to pgvector / Supabase:** set `NEXORA_VECTOR_BACKEND=pgvector` and put
  `NEXORA_DATABASE_URL` + `NEXORA_EMBEDDING_DIM` into `.env` (the factory reads these
  from the environment, not Scrapy settings). Use the Supabase **direct** connection
  string (port 5432), not the 6543 transaction pooler. `pip install asyncpg` first.
- **Switching models / providers** is a settings-only change — see
  `Project Tools/switch_model_guide.md`.

---

## Dependencies Added

```
litellm>=1.40.0      # LLM + non-HF embeddings
chromadb>=0.5.0      # local vector store
# requests (already present) — HF legacy embedding endpoint
# optional: huggingface_hub — used by test_ai_direct_hf.py
```
See `Nexora application/application documents/requirements.txt`.

---

## Verification

Run from `Nexora application/Crawler`:

```powershell
# Connectivity: LLM via LiteLLM + embedding via HF legacy endpoint
python -m nexora_crawler.pipelines.test_ai

# Chroma storage & retrieval round-trip
python -m nexora_crawler.pipelines.test_vector_store
```

Live run result (v4.2.1): `health_check: True`, **124 records indexed**, `dim=384`,
round-trip search top hit `score=1.0000`, live HF query `score=0.9718`.

---

## Known Limitations

- **Page-level embeddings:** the embedding is generated once per page (on the whole
  Markdown) and inherited by all chunks, so retrieval behaves at page granularity until
  per-chunk embeddings are implemented.
- **HF router rate limits:** free-tier 429/503 degrade gracefully (embedding skipped,
  crawl continues).
- **Chroma dimension lock:** switching embedding models with a different dimension
  requires wiping `data/chroma`.

---

## Full Changelog vs v4.1.0

- Added `AI_Utilities/embedding_engine.py` (provider-aware `UnifiedEmbeddingEngine`).
- Added `pipelines/ai_enrichment.py`, `pipelines/chunking_pipeline.py`,
  `pipelines/vector_index_pipeline.py`.
- Added `vector_store/` (`base.py`, `chroma_store.py`, `pgvector_store.py`, `factory.py`).
- Added `pipelines/test_ai.py`, `pipelines/test_ai_direct_hf.py`,
  `pipelines/test_vector_store.py`.
- Added `Project Tools/switch_model_guide.md`.
- Wired Phase 4B into `settings.py` `ITEM_PIPELINES` (250 / 260 / 270).
- Fixed `NexoraChunk.source_type` and `ChromaVectorStore.add()` metadata bugs.
- Synced `.env` to `settings.py`.
- Updated `README.md` and `REPOSITORY_STRUCTURE.md` to v4.2.1.

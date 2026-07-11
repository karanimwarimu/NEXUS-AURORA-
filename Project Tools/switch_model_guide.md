# Switch Model / Provider / Vector Backend Guide

**Project:** NEXUS AURORA → Nexora (`Nexora application/Crawler/nexora_crawler`)
**Scope:** Changing the embedding model, the AI provider, or the vector backend (Chroma ⇄ pgvector/Supabase).
**Status:** As of Phase 4B. The embedding engine is provider-aware and the vector store is behind a `build_vector_store()` factory, so **no code changes are required** for any switch described here — only settings (and, for a dimension change, wiping the index).

---

## How the embedding path is wired (so the "no code change" claim holds)

- `pipelines/ai_enrichment.py` (priority 250) builds a `UnifiedEmbeddingEngine` from settings:
  - `NEXORA_AI_PROVIDER`, `NEXORA_AI_EMBEDDING_MODEL`, `NEXORA_AI_BASE_URL`, `NEXORA_AI_API_KEY`.
- `AI_Utilities/embedding_engine.py` (`UnifiedEmbeddingEngine`) decides the HOW from `provider`:
  - `provider == "huggingface"` → **legacy HF feature-extraction endpoint**
    `https://router.huggingface.co/hf-inference/models/<model>/pipeline/feature-extraction`
    (derived from `base_url`; the model id is URL-encoded).
    This is required because the HF router's OpenAI-compatible `/v1/embeddings` does **NOT** support sentence-transformers models.
  - any other provider (ollama / openai / anthropic / …) → LiteLLM `aembedding` (OpenAI-compatible).
- `pipelines/vector_index_pipeline.py` (priority 270) converts `NexoraChunk` → `VectorRecord` and calls `build_vector_store(backend)` from `vector_store/factory.py`. It is backend-agnostic.
- `vector_store/chroma_store.py` and `vector_store/pgvector_store.py` both implement `BaseVectorStore`.

---

## 1. Change the embedding model (still HF / sentence-transformers)

- **Code:** No change. The engine derives the URL from `NEXORA_AI_EMBEDDING_MODEL` + `base_url` and URL-encodes the model.
- **Settings:** Update `NEXORA_AI_EMBEDDING_MODEL` **and** `NEXORA_EMBEDDING_DIM` to match the new model:

  | Model | Dim |
  |---|---|
  | `sentence-transformers/all-MiniLM-L6-v2` | 384 |
  | `sentence-transformers/all-mpnet-base-v2` | 768 |
  | `BAAI/bge-small-en-v1.5` | 384 |
  | `BAAI/bge-base-en-v1.5` | 768 |

- **Chroma storage:** **Yes — must wipe & recreate.** The HNSW index bakes in the vector dimension; adding a different-dim vector errors. Delete `./data/chroma` (or the collection) after a dimension change.
- **Caveat:** the HF legacy `feature-extraction` endpoint only serves sentence-transformers / feature-extraction models. Do not point it at, e.g., an OpenAI model.

---

## 2. Change the provider (e.g. → OpenAI / Ollama)

- **Code:** No change. The engine routes to LiteLLM `aembedding` for any provider ≠ `huggingface`.
- **Settings:** `NEXORA_AI_PROVIDER`, `NEXORA_AI_MODEL`, `NEXORA_AI_BASE_URL`, `NEXORA_AI_API_KEY`, plus `NEXORA_AI_EMBEDDING_MODEL` + `NEXORA_EMBEDDING_DIM`.
- **Chroma:** wipe only if the **dimension** changed.

---

## 3. Switch backend to pgvector + Supabase

- **Code:** No change. `PgVectorStore` already implements `BaseVectorStore`; `VectorIndexPipeline` only calls `build_vector_store()` + `.add()`. Set `NEXORA_VECTOR_BACKEND = "pgvector"`.
- **⚠ Gotcha — the factory reads `os.getenv`, not Scrapy settings.** In `vector_store/factory.py`, `NEXORA_DATABASE_URL` and `NEXORA_EMBEDDING_DIM` come from the *environment*, not `settings.py`. So for pgvector you must put these in the **`.env`** file (which `load_dotenv` exports into `os.environ`):
  - `NEXORA_DATABASE_URL=<supabase direct URI>` — use the **direct** connection (port 5432), **not** the 6543 transaction pooler (pgvector + asyncpg prepared statements are unreliable on the pooler).
  - `NEXORA_EMBEDDING_DIM=384` — **required**; the factory default is `768`, which would mismatch MiniLM's 384 and fail inserts.
- **Deps:** `pip install asyncpg` (pgvector itself is pre-installed on Supabase; `initialize()` runs `CREATE EXTENSION IF NOT EXISTS vector`).
- **Chroma:** becomes unused — delete `./data/chroma`.
- **Supabase RLS:** none by default, so the DB role can read/write `vector_records`. If you later add RLS policies, make sure the connecting role is exempt or has policies.

---

## Summary table

| Switch | Code | Settings | Index wipe? | Extra |
|---|---|---|---|---|
| HF model (same dim) | – | model | no | – |
| HF model (diff dim) | – | model + dim | **yes** | del `./data/chroma` |
| Provider (openai/ollama) | – | provider/model/url/key/dim | only if dim changes | – |
| Backend → pgvector/Supabase | – | `NEXORA_VECTOR_BACKEND`, `DATABASE_URL`, `EMBEDDING_DIM` in `.env` | fresh table | `pip install asyncpg`, direct URI |

---

## Optional hardening (not required)

Make `vector_store/factory.py` read `NEXORA_DATABASE_URL` / `NEXORA_EMBEDDING_DIM` from Scrapy settings instead of `os.getenv`. This makes the Supabase switch truly settings-only and removes the `.env` env-var dependency flagged above.

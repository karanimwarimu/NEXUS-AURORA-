# NEXORA — Session Handoff & Project Context

> Purpose: give a **new chat session** everything it needs to continue work on Nexora
> without re-deriving context. Last updated: **2026-07-12** (end of the v4.2.1 session).
>
> **Design decision added this session — On-Demand Enrichment:** the crawl is being
> re-scoped so AI summary + tags + embeddings run **on user request**, not during the
> crawl. Settled design + lean plan in Section 8. This is the bridge into Phase 4C/5/7
> (those phases already assume on-demand). NOT yet implemented — code is pending.

---

## 1. What Nexora Is

**Nexora** is the core product of the **NEXUS AURORA** project — an AI-powered **web
intelligence platform** built on **Scrapy** (Python). It crawls websites, extracts and
transforms content into clean structured formats, enriches pages with AI (summaries,
tags, embeddings), chunks the content, and indexes it into a vector store for RAG /
semantic search.

- **Current version:** **v4.2.1** (Phase 4B complete).
- **Location:** `F:\DSF\stsh projects\NEXUS AURORA\`
- **Main app:** `Nexora application\Crawler\nexora_crawler\`
- **Stack:** Scrapy crawler + async middleware chain, Trafilatura (Markdown),
  LiteLLM (LLM), Hugging Face router (embeddings), Chroma / pgvector (vectors),
  FastAPI + SQLite (CLI/API + metadata).

---

## 2. Workflow (Pipeline Chain)

A URL is fetched by the spider, then flows through the Scrapy `ITEM_PIPELINES` chain
(**lowest priority number runs first**, one page at a time):

| Pri | Pipeline | Phase | What it does |
|----|----------|-------|--------------|
| 100 | `NexoraExtractionPipeline` | 1–2 | Raw HTML → structured fields, fingerprint dedup |
| 110 | `MarkdownExtractionPipeline` | 4A | HTML → clean Markdown (Trafilatura) + multimodal assets |
| 150 | `NexoraStylePipeline` | 2 | CSS / design intelligence |
| 160 | `UnifiedSchemaEnricher` | 4A | Schema defaults, `website_type`, `workspace_id` |
| 165 | `MetadataIndexerPipeline` | 4A | Persist to SQLite `MetadataStore` (`data/nexora_metadata.db`) |
| 250 | `AIEnrichmentPipeline` | 4B | LLM **summary** + **tags** + page-level **embedding** |
| 260 | `StructuralChunkingPipeline` | 4B | Markdown → `List[NexoraChunk]` (~512 tokens); inherits parent `ai_summary`/`ai_tags`/`ai_embedding` |
| 270 | `VectorIndexPipeline` | 4B | `NexoraChunk` → `VectorRecord` → `BaseVectorStore` |
| 450 | `ParquetExportPipeline` | 4A | Compressed Parquet export |
| 500 | `NexoraExportPipeline` | 1 | Per-page JSON/CSV |
| 600 | `NexoraDatasetPipeline` | 1 | Master dataset CSV |

**Embedding path (important):** `AI_Utilities/embedding_engine.py` →
`UnifiedEmbeddingEngine` is **provider-aware**:
- `provider == "huggingface"` → direct HTTP POST to the HF router legacy
  `feature-extraction` endpoint
  (`https://router.huggingface.co/hf-inference/models/<model>/pipeline/feature-extraction`).
  This is required because the HF router's OpenAI-compatible `/v1/embeddings` does
  **NOT** support sentence-transformers models.
- any other provider (ollama/openai/anthropic/…) → LiteLLM `aembedding`.

**Vector store:** `vector_store/base.py` (`BaseVectorStore` contract +
`VectorRecord`/`SearchQuery`/`SearchResult`) → `chroma_store.py` (local),
`pgvector_store.py` (Supabase/Postgres), selected by `vector_store/factory.py`
`build_vector_store()`.

---

## 3. What Was Done in This Chat Session

### Embedding model / provider rework
- Diagnosed that the main `UnifiedEmbeddingEngine` used LiteLLM's OpenAI-compatible
  `/v1/embeddings`, which fails for sentence-transformers models on the HF router.
- Reworked `UnifiedEmbeddingEngine` to be **provider-aware** (HF legacy endpoint vs
  LiteLLM), so "both worlds" work and switching models is settings-only.
- Switched the active model to **`sentence-transformers/all-MiniLM-L6-v2` (384-dim)**
  in `settings.py` (`NEXORA_AI_EMBEDDING_MODEL`, `NEXORA_EMBEDDING_DIM=384`).
- Created `Project Tools\switch_model_guide.md` documenting model/provider/backend
  switching (settings-only).

### Critical indexing bug fixes (these blocked ALL vector storage)
1. `NexoraChunk` (`pipelines/chunking_pipeline.py`) was missing the `source_type`
   attribute that `VectorIndexPipeline` read → `AttributeError` on every page.
   **Fix:** added `source_type: str = "chunk"` to the dataclass.
2. `ChromaVectorStore.add()` (`vector_store/chroma_store.py`) did
   `**_json(r.metadata)` — but `_json()` returns a **string**, so `**"..."` raised
   `TypeError`. **Fix:** unpack the dict directly and stringify list/dict fields
   (`ai_tags`, `heading_chain`) for Chroma's scalar-only metadata.
3. Synced stale `.env` (was pointing at the decommissioned `api-inference.huggingface.co`
   host and `all-mpnet-base-v2`/768) to match `settings.py`.

### Verification tooling
- Created `pipelines/test_vector_store.py` — proves embeddings are **stored in and
  retrieveable from** Chroma (health, count, sample records w/ dim, round-trip search).
- Patched a numpy-array truthiness bug in that script (`r.embedding` comes back as a
  numpy array from Chroma).

### Docs / release (v4.2.1)
- Rewrote `README.md` to v4.2.1 (Phase 4B documented, full pipeline chain, 4B config,
  testing, switching guide, known limitations).
- Updated `REPOSITORY_STRUCTURE.md` to reflect Phase 4B files.
- Updated `Nexora application\application documents\requirements.txt` (added
  `litellm`, `chromadb`).
- Created `release_notes_v4.2.1.md` in the **project root** (matching v4.1.0 style).
- Fixed README install path to `application documents/requirements.txt`.

### Verification result (live run)
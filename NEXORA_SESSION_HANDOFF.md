# NEXORA — Session Handoff & Project Context

> Purpose: give a **new chat session** everything it needs to continue work on Nexora
> without re-deriving context. Last updated: **2026-07-12** (end of the on-demand
> enrichment rework session).
>
> **Status:** On-Demand Enrichment is now **implemented and wired into every runner**
> (CLI / FastAPI / `enrich.py`). Default crawl mode is `on_demand` (fast, no AI); `eager`
> (inline enrichment) is fully supported as a fallback. Both modes are stable after the
> bug fixes below.

---

## 1. What Nexora Is

**Nexora** is the core product of the **NEXUS AURORA** project — an AI-powered **web
intelligence platform** built on **Scrapy** (Python). It crawls websites, extracts and
transforms content into clean structured formats, enriches pages with AI (summaries,
tags, embeddings), chunks the content, and indexes it into a vector store for RAG /
semantic search.

- **Current version:** **v4.2.1** (Phase 4B complete) + on-demand rework (post-v4.2.1).
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

**Enrichment gating (NEW):** pipelines 250/260/270 run **only** when
`NEXORA_ENRICH_MODE == "eager"`. In the default `on_demand` mode the crawl stops at 165
(clean markdown saved, no AI/vectors). They are invoked later via `enrich.py`.

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

## 3. On-Demand Enrichment (the rework — was "Section 8" in the prior handoff)

### Why
Crawling was slow because every page was enriched (summary/tags/vectors) inline. The work
was split into two stages so crawls are fast and AI runs only when asked.

### How it works
1. **Crawl (`on_demand`, default)** — fetch + clean + save the page. No AI calls. The full
   cleaned Markdown is stored in the SQLite `pages.markdown` column (and per-page JSON/CSV
   + Parquet).
2. **Enrich (offline)** — `enrich.py` reads saved pages whose `ai_summary` is still empty,
   runs the **existing** `AIEnrichmentPipeline` → `StructuralChunkingPipeline` →
   `VectorIndexPipeline` over them, and writes results back to the same `pages` table
   (`ai_summary`, `ai_tags_json`) plus the vector store.

### The switch — `NEXORA_ENRICH_MODE`
Defined in `settings.py`:
```python
NEXORA_ENRICH_MODE = os.getenv("NEXORA_ENRICH_MODE", "on_demand").lower()
```
- `"eager"` — enrichment runs inline during the crawl (old behavior).
- `"on_demand"` — enrichment skipped during crawl; run `enrich.py` later (default).

`ITEM_PIPELINES` is built conditionally on this value, so flipping it just changes which
pipelines are registered — no pipeline code is altered or duplicated.

### How to choose the mode from each runner
| Runner | How |
|--------|-----|
| `scrapy crawl nexora -a urls=...` | `NEXORA_ENRICH_MODE=eager scrapy crawl ...` (env var) or set it in `.env` |
| FastAPI `POST /crawl` | request body field `enrich_mode`: `"eager"` \| `"on_demand"` |
| Interactive CLI (`python -m nexora_crawler.api`) | prompted: *Enrichment mode (1 on_demand / 2 eager)* |
| Direct CLI (`--url ...`) | `--enrich-mode eager\|on_demand` |
| `enrich.py` | n/a — it always enriches (it *is* the on-demand runner) |

When omitted everywhere, the `on_demand` default applies.

### `enrich.py` (new CLI)
Run from the `Crawler/` directory:
```
python enrich.py                      # enrich all unenriched pages
python enrich.py --domain example.com
python enrich.py --crawl-id <id>
python enrich.py --url https://example.com/page
python enrich.py --limit 50
```
It reuses the exact same pipeline classes/settings as the eager path, so output is
identical by construction. Selection uses `MetadataStore.get_unenriched_pages()`
(`ai_summary` empty); write-back uses `MetadataStore.update_enrichment()`.

### Where the markdown is saved
The `markdown` field (full text) is persisted by the chain to:
- **SQLite** `data/nexora_metadata.db` → `pages.markdown` (the store `enrich.py` reads back).
- **Per-page files** `output/pages/<domain>__<path>__<ts>.json` (+ `.csv`).
- **Parquet** `output/parquet/...`.
- **Vector store** (after enrich) `./data/chroma` as `VectorRecord.content`.

---

## 4. Bug Fixes Applied This Session (eager-mode stability)

From a live on_demand-vs-eager test run:
1. **`items.py`** — added `vector_backend = scrapy.Field()`. The `VectorIndexPipeline`
   sets `item["vector_backend"]` after indexing; Scrapy Items reject unknown keys, so eager
   mode crashed after inserting chunks. Now fixed.
2. **`storage/local_sqlite.py`** — added `_migrate_schema()` (called from `_init_schema`):
   renames `markdown_preview` → `markdown` on existing DBs (non-destructive, preserves data),
   falls back to `ADD COLUMN` only if no old column. Fixes `no column named markdown` on
   pre-rework databases.
3. **`api.py`** — the crawl subprocess now receives `--enrich-mode` so its status line shows
   the real mode (previously printed "default (on_demand)" even when `eager` was active).
4. **`pipelines/ai_enrichment.py`** — added `_truncate_text()` (cuts at last
   paragraph/sentence boundary, not mid-word) and used it for the summary (4000) and tags
   (3000) prompts. Removes mid-word cuts like `temperatur` that risk corrupting JSON-tag
   extraction.

---

## 5. What Was Done in This Chat Session (summary)

- **Embedding model / provider rework** (carried over from v4.2.1 handoff): provider-aware
  `UnifiedEmbeddingEngine`; active model `sentence-transformers/all-MiniLM-L6-v2` (384-dim);
  `switch_model_guide.md`.
- **On-demand rework (Steps 1–5):** `NEXORA_ENRICH_MODE` flag + conditional `ITEM_PIPELINES`;
  full `markdown` storage (was 500-char preview); `enrich.py` offline command;
  `get_unenriched_pages` / `update_enrichment` on `MetadataStore`; default flipped to
  `on_demand`.
- **Runner wiring:** `enrich_mode` selectable from FastAPI `/crawl`, interactive CLI prompt,
  and direct CLI `--enrich-mode`.
- **Eager-mode bug fixes:** `vector_backend` field, `markdown` schema migration, CLI display,
  prompt truncation.
- Companion doc: `NEXORA_ONDEMAND_REWORK_SUMMARY.md` (concise changelog for this session).

---

## 6. Verification Status

- `py_compile` clean on all changed files.
- `markdown` migration proven on a simulated old-schema DB (rename + data preserved + fresh
  full-markdown insert works).
- `enrich` selection / write-back / idempotency verified against the test DB.
- Gating verified: on_demand = 8 pipelines, eager = 11.
- **Live full run NOT executed in this sandbox** — it lacks `trafilatura` / `scrapy` /
  `litellm` / `chromadb`. Run `scrapy crawl nexora ...` (and `python enrich.py`) in the
  configured environment to close the loop.

---

## 7. How to Continue (next steps)

- **Phase 4C / 5 / 7** already assume on-demand. The natural next piece is a
  **scheduled/background home for `enrich`** (the prior handoff's "EnrichmentRunner" /
  `ai_enrich_batch` job). This is NOT a new pipeline — it wraps the existing `enrich.py`
  flow in a background/scheduled runner (Celery/RQ/async task). Do not duplicate the
  enrichment logic.
- **Search/RAG**: confirm the query path hits `BaseVectorStore.search()` and that
  unenriched pages are simply absent (they are — only `VectorIndexPipeline` writes vectors).
- **Docs**: `README.md` / `REPOSITORY_STRUCTURE.md` still describe enrichment as happening
  "during the crawl" (the old `eager` default). Optionally update them to reflect the new
  `on_demand` default and the `enrich` command.
- **Schema**: if you change the `pages` schema again, extend `_migrate_schema()` (not a
  destructive wipe) so existing dev DBs keep working.

## Key file map
- `Nexora application/Crawler/nexora_crawler/settings.py` — `NEXORA_ENRICH_MODE`, conditional `ITEM_PIPELINES`.
- `Nexora application/Crawler/enrich.py` — offline on-demand enrichment CLI.
- `Nexora application/Crawler/nexora_crawler/storage/local_sqlite.py` — `MetadataStore`, `get_unenriched_pages`, `update_enrichment`, `_migrate_schema`.
- `Nexora application/Crawler/nexora_crawler/items.py` — `vector_backend` field.
- `Nexora application/Crawler/nexora_crawler/pipelines/ai_enrichment.py` — `_truncate_text`.
- `Nexora application/Crawler/nexora_crawler/api.py` — FastAPI `/crawl` `enrich_mode` + CLI flags/prompt.

# Nexora — On-Demand Enrichment Rework (Session Summary)

**Date:** 2026-07-12 · **Build state after this session:** v4.2.1 + on-demand rework + eager-mode bug fixes

## Goal
Decouple crawling from AI enrichment. A crawl should be fast (fetch → clean → save) with
**no AI calls**. Summaries, tags, and vectors are produced later by a separate, on-demand
`enrich` step that reuses the existing Phase 4B pipelines.

## What was done

### Rework (Steps 1–5)
1. **Enrichment mode flag** — `settings.py` gained `NEXORA_ENRICH_MODE`
   (`"eager"` | `"on_demand"`). `ITEM_PIPELINES` is built conditionally: the three Phase 4B
   pipelines (250 AI, 260 chunking, 270 vector index) are included **only** when `eager`.
2. **Full markdown storage** — `local_sqlite.py` column `markdown_preview` → `markdown`
   (full text, no 500-char truncation). Test DB wiped/recreated.
3. **Offline `enrich` command** — new `Crawler/enrich.py` reuses `AIEnrichmentPipeline` →
   `StructuralChunkingPipeline` → `VectorIndexPipeline` over saved pages. Added
   `MetadataStore.get_unenriched_pages()` and `update_enrichment()` (same table/fields).
4. **Validation** — confirmed on_demand gating + on_demand→enrich→search data flow.
5. **Default flipped** — `NEXORA_ENRICH_MODE` now defaults to `"on_demand"`. `eager` stays
   fully supported.

### Mode selection across every runner
- `scrapy crawl nexora` → env var (`NEXORA_ENRICH_MODE=...`) or `.env`.
- FastAPI `POST /crawl` → new optional `enrich_mode` field (`eager`/`on_demand`).
- Interactive CLI → new prompt for enrichment mode.
- Direct CLI → new `--enrich-mode` flag (reloads `settings.py` in-process).
- `enrich.py` → always enriches (it *is* the on-demand runner).

### Bug fixes (from a live on_demand-vs-eager test run)
- **`items.py`** — added `vector_backend = scrapy.Field()` so the vector pipeline no longer
  crashes on `item["vector_backend"] = ...` in `eager` mode.
- **`local_sqlite.py`** — added `_migrate_schema()` that renames `markdown_preview` →
  `markdown` on existing DBs (non-destructive; preserves data). Fixes `no column named
  markdown` on pre-rework databases.
- **`api.py`** — crawl subprocess now receives `--enrich-mode`, so its status line shows the
  real mode (previously printed "default (on_demand)" even when `eager` was active).
- **`ai_enrichment.py`** — added `_truncate_text()` (boundary-aware) and used it for the
  summary (4000) and tags (3000) prompts, removing mid-word cuts like `temperatur`.

## Verification
- `py_compile` clean on all changed files.
- `markdown` migration proven on a simulated old-schema DB (rename + data preserved + fresh
  full-markdown insert works).
- Selection / write-back / idempotency of `enrich` verified against the test DB.
- Gating verified: on_demand = 8 pipelines, eager = 11.

## Not verified live (environment)
This sandbox lacks `trafilatura` / `scrapy` / `litellm` / `chromadb`, so a full
`scrapy crawl` + `python enrich.py` + API run was **not** executed end-to-end. Run it in the
configured environment to close the loop.

## Files changed
- `Nexora application/Crawler/nexora_crawler/settings.py`
- `Nexora application/Crawler/nexora_crawler/storage/local_sqlite.py`
- `Nexora application/Crawler/nexora_crawler/items.py`
- `Nexora application/Crawler/nexora_crawler/pipelines/ai_enrichment.py`
- `Nexora application/Crawler/nexora_crawler/api.py`
- `Nexora application/Crawler/enrich.py` (new)

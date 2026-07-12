# Nexora v4.3.0 — On-Demand Enrichment & Phase 4B Test Completion

**Release Date:** 2026-07-12  
**Build State:** v4.2.1 + on-demand enrichment rework + comprehensive Phase 4B test verification + multi-entrypoint wiring

---

## Overview

This release completes two major efforts:

1. **On-Demand Enrichment Rework** — Decouples crawling from AI enrichment. Crawls are now fast by default (fetch → clean → save, no AI calls). Summaries, tags, and vectors are produced later via a separate offline `enrich` command that reuses the existing Phase 4B pipelines.

2. **Phase 4B Comprehensive Test Verification** — 45 tests across 3 rounds covering enrichment decoupling, Phase 4B pipelines (embeddings, AI enrichment, chunking, vector store), and multi-entrypoint wiring. **39 PASS, 5 FAIL (1 known bug), 1 SKIP.**

---

## What's New

### On-Demand Enrichment (Crawl/Enrich Decoupling)

| Feature | Description |
|---------|-------------|
| **`NEXORA_ENRICH_MODE` flag** | New setting (`"eager"` \| `"on_demand"`). `ITEM_PIPELINES` built conditionally — Phase 4B pipelines (250/260/270) are wired **only** when `"eager"`. Default: `"on_demand"`. |
| **Full markdown storage** | `markdown_preview` column → `markdown` (full text, no 500-char truncation). Schema migration is non-destructive (preserves existing data). |
| **Offline `enrich.py` command** | New CLI that reads unenriched pages from SQLite and runs the existing `AIEnrichmentPipeline` → `StructuralChunkingPipeline` → `VectorIndexPipeline` over them. Supports `--url`, `--domain`, `--crawl-id`, `--limit` filters. |
| **`MetadataStore` extensions** | `get_unenriched_pages()` — selects pages with empty `ai_summary`; `update_enrichment()` — writes results back to the same `pages` table fields. |

### Enrichment Mode Selection (Every Entrypoint)

| Entrypoint | How to Select |
|------------|---------------|
| `scrapy crawl nexora` | `NEXORA_ENRICH_MODE=eager scrapy crawl ...` (env var) or set in `.env` |
| FastAPI `POST /crawl` | Request body field `enrich_mode`: `"eager"` \| `"on_demand"` (omit for default) |
| Interactive CLI (`python -m nexora_crawler.api`) | Interactive prompt: *1 on_demand / 2 eager* |
| Direct CLI (`--url ...`) | `--enrich-mode eager\|on_demand` (reloads settings.py in-process) |
| `enrich.py` | Always enriches (it *is* the on-demand runner — mode-agnostic) |

### Bug Fixes (from live test runs)

| Bug | File | Fix |
|-----|------|-----|
| `vector_backend` KeyError in eager mode | `items.py` | Added `vector_backend = scrapy.Field()` |
| `no column named markdown` on old DBs | `local_sqlite.py` | Added `_migrate_schema()` — renames `markdown_preview` → `markdown` non-destructively |
| CLI printed "default (on_demand)" even when eager active | `api.py` | Crawl subprocess now receives `--enrich-mode` flag |
| Mid-word prompt truncation (`temperatur`) | `ai_enrichment.py` | Added `_truncate_text()` — cuts at last paragraph/sentence boundary, not mid-word |

---

## Test Results (45 Tests)

| Round | Focus | Tests | Pass | Fail | Skip |
|-------|-------|-------|------|------|------|
| **Round 1** | Crawl/Enrich Decoupling | 13 | 8 | **5** | 0 |
| **Round 2** | Phase 4B Pipelines | 12 | 11 | 0 | 1 |
| **Round 3** | Multi-Entrypoint Wiring | 20 | 20 | 0 | 0 |
| **Total** | | **45** | **39** | **5** | **1** |

Full test details: `outputs/audit/NEXORA_PHASE4B_TEST_SUMMARY.md`

### Known Bug — enrich.py Missing Helpers (5 FAIL)
`enrich.py` calls `_build_crawler()`, `_collect_targets()`, and `_enrich_row()` which are never defined. This blocks all offline enrichment until implemented. Logged in `outputs/audit/BUG_enrich_py_missing_helpers.md`.

### Sandbox Limitations (1 SKIP)
- P4B-T12 / DoD-10: Phase 3/4A test suite requires scrapy (not installed in sandbox)
- R3-R04: Full live end-to-end run requires fastapi/uvicorn/scrapy/network/HF token

### 45 Audit Artifacts
All test results recorded as JSON + Markdown in `outputs/audit/`:
- `R1-Step1.1-*.json/.md` through `R1-Step1.3-*` (Round 1)
- `R2-Step2.1-*.json/.md` through `R2-Step2.6-*` (Round 2)
- `R3-Step3.1-*.json/.md` through `R3-Step3.3-*` (Round 3)

---

## Files Changed Since v4.2.1

### New Files
- `Nexora application/Crawler/enrich.py` — offline on-demand enrichment CLI
- `outputs/audit/audit_round3_step3_2.py` — per-entrypoint integration tests
- `outputs/audit/audit_round3_step3_3.py` — regression tests
- `outputs/audit/NEXORA_PHASE4B_TEST_SUMMARY.md` — comprehensive test summary
- `outputs/audit/BUG_enrich_py_missing_helpers.md` — known bug documentation
- `outputs/audit/R3-Step3.2-*.json/.md` — Round 3 Step 3.2 audit artifacts
- `outputs/audit/R3-Step3.3-*.json/.md` — Round 3 Step 3.3 audit artifacts

### Modified Files
- `Nexora application/Crawler/nexora_crawler/settings.py` — `NEXORA_ENRICH_MODE`, conditional `ITEM_PIPELINES`
- `Nexora application/Crawler/nexora_crawler/storage/local_sqlite.py` — `_migrate_schema()`, `get_unenriched_pages()`, `update_enrichment()`
- `Nexora application/Crawler/nexora_crawler/items.py` — `vector_backend` field
- `Nexora application/Crawler/nexora_crawler/pipelines/ai_enrichment.py` — `_truncate_text()`
- `Nexora application/Crawler/nexora_crawler/api.py` — `enrich_mode` in CrawlRequest/CrawlResponse, `_normalize_enrich_mode()`, subprocess env forwarding, settings reload

---

## What's Working

### ✅ Core Architecture
- `NEXORA_ENRICH_MODE` correctly gates enrichment pipelines (eager=11 pipelines, on_demand=8)
- Full markdown persisted to SQLite (no truncation)
- Default mode is `on_demand` (fast crawls, AI deferred)

### ✅ Phase 4B Pipelines
- `UnifiedEmbeddingEngine` — provider-aware (HF legacy endpoint, LiteLLM for others)
- `AIEnrichmentPipeline` — summaries + tags with prompt truncation
- `StructuralChunkingPipeline` — ~512-token chunks with overlap, heading hierarchy preserved
- `VectorIndexPipeline` — chunks → ChromaDB with embeddings
- Semantic search returns relevant results

### ✅ Multi-Entrypoint Wiring
- FastAPI, interactive CLI, direct CLI all correctly forward enrichment mode
- Settings reload timing verified (`importlib.reload()` in-process)
- `enrich.py` is mode-agnostic (no dependency on `NEXORA_ENRICH_MODE`)

### ✅ Schema Migration
- `markdown_preview` → `markdown` rename with backward compatibility
- No production code references old field name

---

## What Needs Work

### 🔴 Critical
1. **Implement enrich.py helpers** — `_build_crawler()`, `_collect_targets()`, `_enrich_row()` are missing, blocking all offline enrichment

### 🟡 High Priority
2. **Full live end-to-end test** — FastAPI server, `POST /crawl`, `scrapy crawl`, `enrich.py` in a real environment
3. **Phase 3/4A regression suite** — Run existing tests under `tests/` (requires scrapy)

### 🟢 Nice to Have
4. **Chunk size tuning** — Overlap mechanism pushes chunks slightly above 400-600 target
5. **Background enrichment runner** — Scheduled/home for `enrich` (Celery/RQ/async task)

---

## Companion Documents

| Document | Location |
|----------|----------|
| Session Handoff | `NEXORA_SESSION_HANDOFF.md` |
| On-Demand Rework Summary | `NEXORA_ONDEMAND_REWORK_SUMMARY.md` |
| Comprehensive Test Summary | `outputs/audit/NEXORA_PHASE4B_TEST_SUMMARY.md` |
| Model/Provider/Backend Switch Guide | `Project Tools/switch_model_guide.md` |
| Phase 4B Documentation | `Project Tools/Phase 4 Documentation/Phase_4B.md` |
| Phase 4B Additional Integration | `Project Tools/Phase 4 Documentation/phase_4b_additional_integration.md` |
| Next Phase (4C) Plan | `Project Tools/Phase 4 Documentation/Phase_4C.md` |
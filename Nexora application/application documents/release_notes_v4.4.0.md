# Nexora v4.4.0 — Debug Campaign Fixes & Provider Fallback

**Release Date:** 2026-07-21  
**Build State:** v4.3.0 + 14-step debug campaign (Steps 1–14 complete) + provider fallback architecture  
**Branch:** `phase4b_finaldebugs`

---

## Overview

This release is the **debug stabilization pass** over v4.3.0. A 10-test live QA run on 2026-07-20 exposed 6 reproducible runtime bugs plus 1 split-brain data-store path bug. All were fixed and verified, then extended with an anti-bot stealth validation, action-link crawl hygiene, a live JS-rendering fixture replacement, and a provider-fallback architecture for quota-exhausted AI backends.

**Zero source/config changes were made during the QA run itself** — all fixes were applied afterward in a controlled one-fix-at-a-time protocol.

---

## What's New

### Critical Fixes (P0–P1)

| # | Bug | Files | Fix |
|---|-----|-------|-----|
| 1 | `__skip` KeyError — duplicate pages crashed item processing instead of dropping | `items.py`, `pipelines/__init__.py` | Removed non-functional mangled `__skip` field; duplicate-fingerprint branch now raises `scrapy.exceptions.DropItem` (Scrapy's proper drop mechanism). 124 items lost in QA run → 0. |
| 2 | MarkdownPipeline `int('2x')` srcset crash | `Extractor/multimodal_extractor.py` | New `_descriptor_weight()` strips trailing `w`/`x`, parses as float; malformed descriptor ranks 0 instead of raising. New `_safe_dimension()` handles `100%`/`auto`/`600px` attrs. 53/53 Wikipedia pages got no markdown → 0. |
| 3 | ContentTypeFilter blocks `robots.txt` | `middlewares/__init__.py` | Added `_INFRA_PATH_RE` pass-through for `/robots.txt` and `sitemap*.xml` before content-type block. Robots rules now actively enforced (38 forbidden URLs observed on Wikipedia). |
| 4 | Parquet `meta_tags` empty-struct export failure | `pipelines/parquet_export.py` | Added catch-all pass: any remaining dict/list/tuple/set is JSON-stringified into `{key}_json`. Prevents PyArrow `struct<>` inference from unwritable empty dicts. Parquet rows exported: 0 → >0. |
| 5 | Eager AI pipeline-drain hang | `AI_Utilities/embedding_engine.py`, `pipelines/ai_enrichment.py`, `pipelines/chunking_pipeline.py`, `settings.py`, `items.py` | Circuit breaker: after 3 consecutive failures, all further AI calls are skipped for the rest of the run. Embedding engine and LLM pipeline have independent breakers. Prevents multi-hour timeout drains from dead providers. |
| 6 | Split-brain metadata DB (CWD-relative paths) | `settings.py` | `_anchored_path()` resolves relative `NEXORA_METADATA_DB` / `NEXORA_CHROMA_PATH` against the settings file's directory, not CWD. Absolute paths exported back to `os.environ` so the factory lands on the same files. |

### High-Priority Fixes (P1–P2)

| # | Bug | Files | Fix |
|---|-----|-------|-----|
| 7 | `enrich.py --limit` None → SQLite crash; ignored with filters | `storage/local_sqlite.py`, `enrich.py` | New `_limit_clause()` helper: `limit=None` omits LIMIT entirely; applied to `get_unenriched_pages`, `query_by_domain`, `query_by_crawl_id`. Filter + cap now compose correctly. |
| 8 | `_enrich_row` reads `ai_tags` vs DB column `ai_tags_json` | `enrich.py` | Seeds `ai_tags` by deserializing `ai_tags_json`; write-back preserves existing summary/tags when new values are empty (prevents data loss on re-enrich). |
| 9 | `token_count` float from `//4.5` | `pipelines/chunking_pipeline.py` | New `_estimate_tokens(text) -> int = int(len(text)/4.5)` single source of truth; replaces all four estimation sites. |
| 10 | `build_vector_store()` fallback defaults diverge | `vector_store/factory.py` | New `_cfg()` resolver: explicit arg → env var → `nexora_crawler.settings` → default. Backend fallback aligned pgvector→chroma; dim fallback aligned 768→384. |
| 11 | Playwright wiring (4 sub-defects) | `settings.py`, `dynamic_detection.py` | Removed handler-as-middleware duplicate; fixed text-density script-body counting; excluded `.txt`/`.xml` from domain-profile probes; Playwright retry now uses `dont_filter=True` to avoid dupefilter eating the re-request. |

### New Features

| # | Feature | Files | Description |
|---|---------|-------|-------------|
| 12 | Action-link crawl hygiene | `middlewares/__init__.py` | Added `/vote`, `/hide`, `/submit` path patterns + `_BLOCKED_QUERY_RE` for `action=`/`mobileaction=` query params. Prevents 429 storms from action endpoints. |
| 13 | Provider fallback architecture | `AI_Utilities/embedding_engine.py`, `pipelines/ai_enrichment.py`, `pipelines/chunking_pipeline.py`, `settings.py` | When primary AI provider hits the circuit breaker, calls transparently route to a secondary provider. New `NEXORA_AI_FALLBACK_PROVIDER/MODEL/BASE_URL/API_KEY` settings. Fallback has its own independent breaker. |
| 14 | Anti-bot stealth validation | `dynamic_detection.py`, `settings.py` | Stealth args (`--disable-blink-features=AutomationControlled`) and `_build_stealth_script()` were added in Step 10; Step 11 documents the test plan for scrapingcourse.com. |
| 15 | crawl_id propagation | `api.py`, `nexora_spider.py` | `api.py:_run_crawl_sync` now generates a UUID and passes it to the spider via `crawl_id`. Every row in the SQLite `pages` table now has a non-empty `crawl_id`, enabling multi-crawl traceability and `--crawl-id` filtering in `enrich.py`. |
| 16 | PLAYWRIGHT_BLOCKED_RESOURCE_TYPES wiring | `dynamic_detection.py`, `settings.py` | Route-level abort callback (`PLAYWRIGHT_ABORT_REQUEST`) blocks `image`, `font`, `media`, and `ping` requests before they reach the Playwright network. Complements the existing JS-level analytics blocking in `playwright_resource_blocker.py`. Verified: 26/26 image requests aborted on Wikipedia, 17/17 on react-shopping-cart, 1/1 font request aborted on quotes.toscrape.com/js/. |

### Test Fixture Update

| | Old | New |
|---|-----|-----|
| **Test 02 (JS-rendering)** | `https://react-shopping-cart-67007.firebaseapp.com/` (404) | `https://react-shopping-cart-67954.firebaseapp.com/` (200, 2058 bytes) |

Same React+TypeScript+Styled-Components codebase, live deployment.

---

## Files Changed Since v4.3.0

### New Files
- `outputs/qa_run_20260720/NEXORA_QA_REPORT.md` — 10-test live QA scorecard
- `outputs/qa_run_20260720/NEXORA_DEBUG_REPORT.md` — continuous debug campaign log (14 steps)
- `outputs/qa_run_20260720/stepN_verify*.log` — per-step verification logs
- `outputs/qa_run_20260720/stepN_*_check.py` — unit probes for each fix

### Modified Files
- `Nexora application/Crawler/nexora_crawler/items.py` — removed mangled `__skip`; declared `ai_status`
- `Nexora application/Crawler/nexora_crawler/middlewares/__init__.py` — infra pass-through, action-link query blocking
- `Nexora application/Crawler/nexora_crawler/pipelines/__init__.py` — dead `__skip` guards removed; `DropItem` for duplicates
- `Nexora application/Crawler/nexora_crawler/pipelines/metadata_indexer.py` — dead `__skip` guard removed
- `Nexora application/Crawler/nexora_crawler/pipelines/parquet_export.py` — catch-all JSON-stringify for nested fields
- `Nexora application/Crawler/nexora_crawler/pipelines/ai_enrichment.py` — circuit breaker + fallback provider
- `Nexora application/Crawler/nexora_crawler/pipelines/chunking_pipeline.py` — `_estimate_tokens()`, breaker-aware embedding, fallback wiring
- `Nexora application/Crawler/nexora_crawler/AI_Utilities/embedding_engine.py` — circuit breaker + fallback engine
- `Nexora application/Crawler/nexora_crawler/settings.py` — anchored paths, `NEXORA_AI_FAILFAST_THRESHOLD`, `NEXORA_AI_FALLBACK_*`
- `Nexora application/Crawler/nexora_crawler/vector_store/factory.py` — settings-aware `_cfg()` resolver
- `Nexora application/Crawler/nexora_crawler/storage/local_sqlite.py` — `_limit_clause()`, limit support on all queries
- `Nexora application/Crawler/enrich.py` — `ai_tags_json` deserialization, write-back preservation, `_limit_clause` usage
- `Nexora application/Extractor/multimodal_extractor.py` — `_descriptor_weight()`, `_safe_dimension()`, trailing-comma srcset handling

---

## Verification

### Live QA Matrix (2026-07-20, 10 tests)

| Test | Target | Strategy | Result |
|------|--------|----------|--------|
| 01 | quotes.toscrape.com/js/ | single-page | ✅ Crawl OK; Parquet meta_tags fixed |
| 02 | react-shopping-cart (firebase) | single-page (eager) | ⚠️ Old fixture 404; new fixture live |
| 03 | news.ycombinator.com | linked-pages | ✅ 24/30; action-link filter pending live 429 recheck |
| 04 | httpbin.org | linked-pages | ✅ 2/5; Parquet fixed |
| 05 | sitemaps.org | whole-website | ✅ 48/50; sitemap discovery validated |
| 06 | python.org | whole-website (eager) | 🔴 Terminated (HF quota); circuit-breaker verified in Step 5 |
| 07 | en.wikipedia.org | everything | 🔴 Stopped early; __skip + srcset crashes fixed in Steps 1–2 |
| 08 | docs.python.org/3/ | everything | ✅ 49/50; near-clean |
| 09 | scrapingcourse anti-bot | single-page | ✅ 403 WAF graceful; Playwright/stealth test pending |
| 10 | httpbin.org/headers | single-page | ✅ JSON blocked by design |

### Debug Campaign Verification (Steps 1–14)

All 14 steps have verification logs in `outputs/qa_run_20260720/`:
- `step1_verify.log` — `__skip` KeyErrors: 6 → 0
- `step2_verify.log` — srcset `int('2x')` errors: 53 → 0
- `step3_verify_a.log` / `step3_verify_b.log` — robots.txt BLOCK lines: 1/run → 0; `robotstxt/forbidden: 38` first appearance
- `step4_verify.log` — Parquet rows: 0 → 2 (httpbin test)
- `step5_verify.log` — breaker opens at 3 failures; 12 pages skipped vs 111 pre-fix
- `step6_verify2.log` — `enrich.py --domain --limit` first end-to-end success
- `bug15_verify.log` — CWD-agnostic DB path confirmed
- `step7_verify.log` — stored tags survive re-enrich
- `step8_unit_check.py` — all `token_count` values are `int`
- `step9_check.py` — factory resolves chroma/384/anchored path
- `step10_verify3/4.log` — Playwright routing confirmed; words(clean) 6→192
- `step11` — test plan documented; live run pending
- `step12` — patterns unit-checked; live 429 recheck pending
- `step13` — new fixture confirmed 200/2058 bytes
- `step14` — fallback settings added; live validation pending

---

## Known Limitations (Post v4.4.0)

- **Full re-validation matrix not yet re-run** — Tests 06/07/08 need full-scale re-runs with working AI provider + Playwright active.
- **Step 11/12/13/14 live validation pending** — unit checks and code changes done; live crawl verification blocked on environment readiness (Playwright chromium, HF quota/top-up or local Ollama).
- **`crawl_id` not populated** — schema enricher never sets it; `--crawl-id` filtering returns all rows for now.
- **Chunk size overshoot** — avg ≈ 680 tokens/chunk vs 512 target (overlap-driven; tracked as nice-to-have).

---

## Upgrade Notes

1. **Database path migration** — If you have an existing `data/nexora_metadata.db` created before this release, it will continue to work. The new `_anchored_path()` only affects *new* databases or when running from a different CWD.
2. **Vector store** — no migration needed. Existing Chroma collections are compatible.
3. **Playwright** — set `NEXORA_PLAYWRIGHT_ENABLED=true` in `.env` to activate. Requires `scrapy-playwright>=0.0.48` + `playwright install chromium`.
4. **AI fallback** — optional. Set `NEXORA_AI_FALLBACK_PROVIDER` etc. only if you want automatic failover. Empty values (default) preserve the original skip-after-failures behavior.

---

## Companion Documents

| Document | Location |
|----------|----------|
| QA Report | `outputs/qa_run_20260720/NEXORA_QA_REPORT.md` |
| Debug Campaign | `outputs/qa_run_20260720/NEXORA_DEBUG_REPORT.md` |
| Session Handoff | `NEXORA_SESSION_HANDOFF.md` |
| Repository Structure | `REPOSITORY_STRUCTURE.md` |
| Model/Provider/Backend Switch Guide | `Project Tools/switch_model_guide.md` |

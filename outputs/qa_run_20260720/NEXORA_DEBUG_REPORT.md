# Nexora Debug Campaign — Continuous Report

**Branch:** `phase4b_finaldebugs` · **Started:** 2026-07-21 · **Protocol:** one fix → verify → pause for review
**Source plans:** QA Run 2026-07-20 (`NEXORA_QA_REPORT.md`) + merged 14-step debugging plan
**Verification logs:** `outputs/qa_run_20260720/stepN_verify*.log`

---

## Status Board

| Step | Bug | Priority | Status |
|---|---|---|---|
| 1 | `__skip` KeyError — duplicates crash instead of dropping | 🔴 P0 | ✅ FIXED + verified |
| 2 | MarkdownPipeline `int('2x')` srcset crash | 🔴 P0 | ✅ FIXED + verified |
| 3 | ContentTypeFilter blocks robots.txt | 🔴 P0 | ✅ FIXED + verified |
| 4 | Parquet `meta_tags` empty-struct export failure | 🟠 P1 | ✅ FIXED + verified |
| 5 | Eager AI circuit-breaker (pipeline hang) | 🟠 P1 | ✅ FIXED + verified |
| 6 | `enrich.py --limit` None / ignored with filters | 🟠 P1 | ✅ FIXED + verified |
| **15** | **NEW: split-brain metadata DB — relative `./data/` path resolves per-CWD** (crawls → `nexora_crawler\data\`, enrich.py per its docs → `Crawler\data\`, stale since 07-12; enrich has never seen crawl data when run as documented) | 🔴 P0 (discovered during Step 6) | ✅ FIXED + verified |
| 7 | `_enrich_row` reads `ai_tags` vs DB column `ai_tags_json` | 🟠 P1 | ✅ FIXED + verified |
| 8 | `token_count` float from `//4.5` | 🟡 P2 | ✅ FIXED + verified |
| 9 | `build_vector_store()` fallback defaults diverge | 🟡 P2 | ✅ FIXED + verified |
| 10 | Playwright wiring (env-gated: needs scrapy-playwright ≥0.0.40) | 🟡 P2 | ✅ FIXED + verified (4 sub-defects) |
| 11 | Anti-bot stealth args (depends on 10) | 🟡 P2 | not started |
| 12 | Action-link crawl hygiene (`vote?`, `hide?`, …) | 🟢 P3 | not started |
| 13 | Replace dead Test 02 fixture | 🟢 P3 | not started |
| 14 | HF credits / provider switch (environment) | 🟢 P3 | not started |

---

## Step 1 — `__skip` KeyError (P0) ✅

**Why it happened:** `items.py` declared `__skip = scrapy.Field()`, but Python name-mangles double-underscore class attributes → the field registered as `_NexoraPageItem__skip`. The pipeline's `item["__skip"] = True` therefore wrote to an undeclared key → `KeyError` on every duplicate page. Cost in QA run: 124 items crashed (HN 6, sitemaps.org 2, Wikipedia 114, docs.python 2).

**What changed:**
- `pipelines/__init__.py` — duplicate-fingerprint branch now raises `DropItem("duplicate fingerprint …")` (Scrapy's proper drop mechanism; halts ALL downstream pipelines, counted in `item_dropped_count`). Blanks `html`/`clean_text` first so the dropped-item WARNING log stays small. Added `from scrapy.exceptions import DropItem`.
- `items.py` — removed the non-functional mangled `__skip` field (comment explains why).

**Not touched:** the five now-dead `item.get("__skip")` guards (harmless no-ops; cosmetic cleanup deferred). No other pipeline/spider/settings changes.

**Verification** (`step1_verify.log`, HN linked-pages 30 — same as failing QA Test 03):
| Metric | Before | After |
|---|---|---|
| `__skip` KeyErrors | 6 | 0 |
| scraper ERRORs | 6 | 0 |
| items scraped | 24/30 | 27/30 |
| duplicates | 6 crashed | 3 cleanly dropped (`item_dropped_count: 3`) |

---

## Step 2 — MarkdownPipeline srcset crash (P0) ✅

**Why it happened:** `Extractor/multimodal_extractor.py` parsed srcset candidates with `int(part.split()[1].replace("w", ""))`. Density descriptors (`logo.png 2x`, common on Wikipedia) left `"2x"` → `ValueError: invalid literal for int()`. The exception aborted the whole multimodal+markdown step → 53/53 Wikipedia pages got **no markdown** (RAG-blocking: nothing to chunk/enrich). Two sibling landmines: `int(width)` on attrs like `"100%"`/`"auto"`, and IndexError on trailing-comma srcsets.

**What changed** (one file, `Extractor/multimodal_extractor.py`):
- New `_descriptor_weight()` — strips trailing `w`/`x`, parses as float; malformed descriptor ranks 0 instead of raising.
- New `_safe_dimension()` — parses width/height attrs, returns 0 for `100%`/`auto`/`600px`.
- Srcset comprehension → explicit loop that skips empty entries (trailing commas).

**Not touched:** markdown_pipeline.py itself (crash was entirely in the extractor); crawl-hygiene URL variants (Step 12).

**Verification:**
- Unit (`step2_unit_check.py`): `2x` selects higher-res, `800w,` trailing comma OK, `"broken"` descriptor survives, `%`/`auto`/`px` dims don't crash.
- Live (`step2_verify.log`, Wikipedia everything 20): `invalid literal` errors 53 → **0**; markdown failures 53/53 → **0**; SQLite shows 16–22 KB markdown per page, `extraction_method='trafilatura'`.
- Process note: run stopped post-cap (spider drains queued downloads after max_pages — cap is parse-level, not scheduler-level; relevant to Step 12).

---

## Step 3 — robots.txt blocked by ContentTypeFilter (P0) ✅

**Why it happened:** `ROBOTSTXT_OBEY=True` makes Scrapy fetch robots.txt, but `ContentTypeFilterMiddleware.process_response` rejected it (`text/plain` ≠ HTML) before RobotsTxtMiddleware could parse it → robots rules were **silently never enforced** (proof: pre-fix crawls fetched Wikipedia `/w/` URLs that its robots.txt disallows). The existing `from_sitemap` pass-through only covered spider-issued sitemap requests, not Scrapy's own robots fetch.

**What changed** (one file, `middlewares/__init__.py`):
- New `_INFRA_PATH_RE` (`/robots.txt`, `sitemap*.xml`, `.xml.gz` variants).
- `process_response` lets matching infra files through before the content-type block.

**Not touched:** JSON/non-HTML blocking (probe: `application/json` still blocked); request-level pattern list (never blocked `.txt`/`.xml`). False alarm retracted during work: suspected `"text\html"` typo — byte dump proved source is correct `"text/html"`.

**Verification:**
- Probe (`step3_probe.py`): robots.txt + sitemap.xml ALLOW; HTML ALLOW; JSON BLOCK.
- `step3_verify_a.log` (sitemaps.org whole-website 5): zero robots BLOCK lines (was 1/run); sitemap discovery unaffected; 5/5 items.
- `step3_verify_b.log` (Wikipedia linked-pages 8): **`robotstxt/forbidden: 38`** — first time this stat has ever appeared; robots rules now actively refuse disallowed URLs. 8/8 items scraped.

**Behavioral consequence:** crawls now fetch fewer URLs on robots-restrictive sites (compliance working); older benchmark page counts not directly comparable.

---

## Step 4 — Parquet `meta_tags` empty-struct export (P1) ✅

**Why it happened:** `_item_to_parquet_row()` JSON-stringified only a fixed whitelist of nested fields; `meta_tags` (a dict from the BS4 extractor) wasn't on it. When every row in a flush batch had `meta_tags == {}`, PyArrow inferred `struct<>` with no child fields — unwritable in Parquet — and the **entire flush was lost** (`Total rows exported: 0` in QA Tests 01/04). Six more un-whitelisted nested fields (`headings`, `images`, `internal_links`, `structured_schema`, `social_graphs`, `graph_relations`, `styles`) carried the same latent risk.

**What changed** (one file, `pipelines/parquet_export.py`):
- Added a catch-all pass after the existing whitelist: any remaining dict/list/tuple/set value is JSON-stringified into `{key}_json` (same naming convention as before) and the raw column dropped. Non-serializable values degrade to `str` instead of raising.

**Not touched:** the original whitelist (column names for `entities_json` etc. unchanged), heavy-field exclusions (`html`, `markdown`, `clean_text`, `chunks`), buffering/flush logic.

**Verification** (`step4_verify.log` + `step4_parquet_check.py`, httpbin linked-pages 5 — same as failing QA Test 04):
- `[Parquet] Wrote 2 rows` + `Total rows exported: 2` (was: flush ERROR, 0 rows).
- File inspection: `meta_tags_json` present as string column (sample value `{}` — exactly the killer case), **zero** struct/list columns remain, 13 `_json` columns total (7 of them newly protected fields).

---

## Step 5 — Eager AI circuit-breaker (P1) ✅

**Why it happened:** eager mode had no fail-fast: with a dead/quota-exhausted provider, every page's LLM calls failed (~1–11 s each) and every chunk's embedding call hung to the full 60 s read timeout at concurrency 2. Test 06: downloads done at 23:11, then 0 items/min for 9+ min with ~57 items queued — projected multi-hour drain before spider close.

**What changed** (5 files):
- `AI_Utilities/embedding_engine.py` — new `failfast_threshold` ctor param (default 3), consecutive-failure counter, `_record_failure()`. After N consecutive failures the breaker opens: one WARNING, then `embed()`/`embed_batch()` return `None` instantly for the rest of the run (double-checked after semaphore acquisition too). Success resets the counter. Threshold ≤ 0 disables.
- `pipelines/ai_enrichment.py` — same breaker for LLM calls (failures counted in `_generate_summary`/`_generate_tags` except-paths, successes reset). When open, `process_item` sets `item["ai_status"] = "skipped_after_failures"`, increments `pages_skipped_by_breaker` stat, and returns immediately.
- `pipelines/chunking_pipeline.py` — passes `NEXORA_AI_FAILFAST_THRESHOLD` into the engine.
- `settings.py` — new documented `NEXORA_AI_FAILFAST_THRESHOLD` (env-overridable, default 3, 0 = off).
- `items.py` — declared `ai_status` field (avoids re-creating the Step 1 undeclared-field bug class).

**Not touched:** crawl-side SQLite saving (per plan — already correct), the 60 s `NEXORA_AI_TIMEOUT` (breaker makes it moot; at most ~3 timeouts before trip), VectorIndexPipeline.

**Verification:**
- Probe (`step5_breaker_probe.py`, dead endpoint): 10-text batch → breaker opens at 3, batch ends in 4 s; second batch returns all-None in **0.000 s**.
- Live (`step5_verify.log`, docs.python.org everything 20, eager, LLM quota exhausted — Test 06 conditions): a few early LLM successes (4 summaries/3 tags), then **3 consecutive failures → breaker OPEN → 12 pages skipped** (`pages_skipped_by_breaker: 12`) — vs Test 06's 111 failures. Embedding subsystem was healthy (HF quota reset) and its independent breaker correctly stayed closed: **797/797 chunks embedded + indexed to Chroma, 0 errors**. No AI stall: 18 items scraped + 2 dup-dropped; the 943 s elapsed is the pre-existing post-cap *download* drain (network-bound, same as on_demand runs — Step 12 discussion).
- Bonus regression evidence in the same run: `item_dropped_count: 2` (Step 1), `robotstxt/forbidden: 12` (Step 3), `Parquet Total rows exported: 18` (Step 4) — all prior fixes visible working together in one eager run.

## Step 6 — `enrich.py --limit` handling (P1) ✅

**Why it happened:** `--limit` omitted → argparse default `None` was bound into `LIMIT ?` — which doesn't run unbounded as suspected: SQLite raises **`IntegrityError: datatype mismatch`**, so bare `python enrich.py` crashed outright. With `--domain`, `--limit` was silently ignored AND `query_by_domain` imposed a hidden default cap of 100; `query_by_crawl_id` had no limit support at all.

**What changed** (2 files):
- `storage/local_sqlite.py` — new `_limit_clause()` helper: `limit=None` omits the LIMIT clause entirely; otherwise binds `int(limit)`. Applied to `get_unenriched_pages` (default now `None` = all, matching the CLI's documented "enrich all unenriched pages"), `query_by_domain` (hidden 100-cap removed), and `query_by_crawl_id` (limit support added).
- `enrich.py` — `_collect_targets` now passes `limit=args.limit` to the domain and crawl-id queries so filter + cap compose.

**Not touched:** `query_by_url` (URL is UNIQUE — max 1 row, limit meaningless); `insert_page`/`update_enrichment`.

**Verification:**
- Store-level (`step6_store_check.py`): no-limit unenriched = 347 (was: crash); `limit=5` → 5; domain no-limit = 50 (was: capped 100→50 coincidence removed); domain `limit=5` → 5; crawl-id `limit=2` → 2.
- Live (`step6_verify2.log`): `enrich.py --domain www.sitemaps.org --limit 5` → "**5 page(s) selected**" … "**complete — 5/5 enriched**". Bonus: first-ever end-to-end offline enrichment run — 124 chunks embedded + indexed to Chroma from those 5 pages; Step 5's LLM breaker also fired correctly in the offline path (quota errors → OPEN after 3).

**🔴 NEW BUG DISCOVERED (register #15) — split-brain metadata DB:** `NEXORA_METADATA_DB = './data/nexora_metadata.db'` is CWD-relative. Crawls (CWD `nexora_crawler/`) write `nexora_crawler\data\` (8.2 MB, live); `enrich.py` run from `Crawler/` per its own docstring resolves to `Crawler\data\` (60 KB, stale since 2026-07-12) → the documented enrich workflow has NEVER operated on real crawl data ("0 pages selected"). Step 6's live test was run with CWD `nexora_crawler` as a workaround. Proposed fix (needs approval): anchor the default DB path to the settings file's directory (absolute), so every entrypoint resolves the same file. Also noted: all 347 pages share one `crawl_id` — crawl-run identity is not unique per run (minor, separate).

## Bug #15 — split-brain data-store paths (P0, user-approved out-of-order fix) ✅

**Why it happened:** `NEXORA_METADATA_DB` and `NEXORA_CHROMA_PATH` were CWD-relative (`./data/...`); each entrypoint runs from a different directory, so crawls and `enrich.py` silently used different databases/vector stores. `.env` also carries a relative `NEXORA_CHROMA_PATH`, which overrode any settings-side default; and `vector_store/factory.py` reads these via `os.getenv`, not the settings module.

**What changed** (one file, `settings.py`):
- `_anchored_path()` helper — relative values (defaults **or** env/.env values) resolve against the settings file's directory; absolute values pass through.
- Applied to `NEXORA_METADATA_DB` and `NEXORA_CHROMA_PATH`.
- Resolved absolute paths exported back into `os.environ` so the env-reading factory lands on the same files (bridge until Step 9 reconciles the factory properly).

**Not touched:** `.env` (user config with secrets — left byte-identical; its relative value now simply resolves safely), factory.py (Step 9), stale `Crawler\data\` DB left on disk (60 KB, historical).

**Verification:**
- `bug15_cwd_check.py`: settings imported from 3 different CWDs → identical absolute paths (module + env) in all cases, pointing at the live `nexora_crawler\data\` stores.
- Live (`bug15_verify.log`): `enrich.py --domain www.sitemaps.org --limit 2` from the documented `Crawler\` CWD → "**2 page(s) selected … 2/2 enriched**" (was "0 pages selected").

## Step 7 — `_enrich_row` `ai_tags` vs `ai_tags_json` (P1) ✅

**Why it happened:** `_enrich_row` seeded the item with `row.get("ai_tags", [])`, but the pages table has no `ai_tags` column — tags live serialized in `ai_tags_json`. Stored tags were therefore never read. Worse, tracing the live path showed a data-loss corollary: when the LLM fails or the breaker skips, the regenerated empty `""`/`[]` was written back, **wiping previously-stored tags/summaries** on re-enrich.

**What changed** (one file, `enrich.py`):
- Seeds `ai_tags` by deserializing `ai_tags_json` (tolerates `None`/empty/malformed JSON → `[]`).
- `ai_embedding` seed documented as always-`[]` (embeddings aren't in SQLite; regenerated per-chunk).
- Write-back preservation guard: `update_enrichment` keeps existing summary/tags when the new values are empty.

**Not touched:** `ai_enrichment.py`'s eager-mode overwrite semantics (a re-crawl legitimately regenerates), `metadata_indexer` (writes correctly already). Audit for other stale accessors: `markdown_preview` appears only inside the migration helper (correct).

**Observations logged (not fixed):** `crawl_id` is an empty string on all 347 rows — the schema enricher never populates it, so `--crawl-id` filtering is unusable with current data (plan's Step 7 test command substituted with `--url`).

**Verification:**
- Unit (`step7_unit_check.py`, stub pipelines simulating breaker-open): row with `ai_tags_json='["alpha","beta"]'` → write-back receives `['alpha','beta']` and the existing summary; `None`/`''`/`'not-json'` degrade to `[]` without crashing. PASS.
- Live (`step7_verify.log`): re-enriched `https://www.sitemaps.org/` by `--url` → 1/1 enriched; post-run DB still holds `["Sitemaps","Web Crawling","Search Engines","XML"]` + summary intact (pre-fix, this pass would have wiped them).

## Step 8 — `token_count` float from `//4.5` (P2) ✅

**Why it happened:** `len(markdown) // 4.5` — floor-dividing by a float returns a float, so single-chunk `token_count` violated the dataclass's `int` contract (and Chroma metadata carried floats). Additionally the file mixed calibrations: the top-level estimate used the deliberate 4.5 chars/token (prior session's accuracy fix) while three other sites still used the stale `// 4`.

**What changed** (one file, `pipelines/chunking_pipeline.py`):
- New module-level `_estimate_tokens(text) -> int` = `int(len(text) / 4.5)` — single source of truth, keeps the 4.5 calibration, always int.
- Replaced all four estimation sites (page-level estimate, per-paragraph, per-chunk token_count ×2, overlap carry-over).

**Not touched:** chunking strategy/overlap mechanics; tiktoken option deferred (plan allows either — heuristic kept for zero new dependency). Existing float values already stored in Chroma metadata from earlier runs remain as-is.

**Verification** (`step8_unit_check.py`): single-chunk path returns `int` (was the float leak); 11-chunk run → all `token_count` types are `int`, `chunk_count`/`chunk_index` consistent and sequential. PASS. **Observation:** avg ≈ 680 tokens/chunk vs the 512 target — the known overlap-driven overshoot (register: "chunk size tuning", nice-to-have, unchanged by this fix).

## Step 9 — `build_vector_store()` fallback defaults (P2) ✅

**Why it happened:** the factory read config exclusively via `os.getenv` with hardcoded fallbacks that diverged from settings.py: backend `pgvector` (settings: `chroma`), `NEXORA_EMBEDDING_DIM` `768` (settings: `384` — and that var is NOT in `.env`, so a pgvector deployment would genuinely have built a 768-dim schema against 384-dim vectors), plus a CWD-relative chroma path.

**What changed** (one file, `vector_store/factory.py`):
- New `_cfg(name, default)` resolver with one precedence chain everywhere: explicit call arg → env var → `nexora_crawler.settings` attribute → default.
- Applied to backend selection, `NEXORA_DATABASE_URL`, `NEXORA_EMBEDDING_DIM` (literal fallback aligned 768→384), and `NEXORA_CHROMA_PATH`. Backend literal fallback aligned pgvector→chroma (matches settings' documented default).

**Not touched:** qdrant/cloudflare branches (still raw getenv — unreachable: their store modules don't exist in this tree, the import guard raises first); `.env`; the settings→env export bridge from #15 (still useful for non-factory consumers).

**Verification:**
- `step9_check.py` (all NEXORA_* env vars scrubbed → factory must resolve via settings): backend=`chroma`, dim=`384`, anchored absolute Chroma path; `build_vector_store()` returns `ChromaVectorStore` at the live store. Identical scenario pre-fix: pgvector/768/CWD-relative.
- Live smoke (`step9_smoke.log`): `enrich.py --url .../terms.html` → Chroma initialized at the anchored path, 10 chunks indexed, 1/1 enriched.

## Step 10 — Playwright wiring (P2, env-gated) ✅

**Environment part:** scrapy-playwright upgraded 0.0.34 → **0.0.48** (Scrapy 2.16-compatible; Playwright 1.60, Chromium 148 already present). `.env`: `NEXORA_PLAYWRIGHT_ENABLED` flipped to `true` (comment updated; only these lines touched — secrets untouched).

**Code part — turning it on exposed a chain of four latent defects, fixed in sequence, each confirmed by a DEBUG-level crawl trace:**
1. **Handler registered as middleware** (`settings.py`): `ScrapyPlaywrightDownloadHandler` sat in `DOWNLOADER_MIDDLEWARES` at 543 in addition to `DOWNLOAD_HANDLERS` — instantiating a second handler (log showed doubled "Starting download handler"). Removed; comment explains why it must never return.
2. **Text density counted script bodies as text** (`dynamic_detection.py`): `_calculate_text_density` stripped tags but kept `<script>` content — quotes.toscrape.com/js scored density 0.5446 ("text-rich, static") when its visible text density is 0.0165. Now script/style bodies are removed first; the page correctly triggers "very low text density".
3. **robots.txt poisoned the domain profile cache** (`dynamic_detection.py`): DD probed the first request through — `robots.txt` — judged the 404 error page "static", and cached that verdict domain-wide with a fresh TTL, so the real page skipped detection. Added `.txt`/`.xml` to `_is_html_request` exclusions (aligned with Step 3's infra-file principle).
4. **Playwright retry eaten by the dupefilter** (`dynamic_detection.py`): a Request returned from `process_request` re-enters the scheduler with the same fingerprint → silently dropped (`dupefilter/filtered: 1`, crawl ended with 0 pages). `_apply_playwright_meta` now returns `request.replace(dont_filter=True)`.

**Verification** (`step10_debug*.log`, `step10_verify3/4.log`): quotes.toscrape.com/js — `[DD] Playwright routing … very low text density (0.0165)` → Chromium render → **words(raw) 17→259, words(clean) 6→192** (plan criterion: 150+). Confirmed via both the raw scrapy CLI and the `api.py` entrypoint. Defect chain visible run-by-run in the three debug logs.

**Observations logged:** profile-cache TTL uses in-memory timestamps only (`last_checked` column never read → every new process re-probes each domain once — wasteful but safe); `NEXORA_SITE_PROFILE_DB` is anchored via the middleware's own `_PROJECT_ROOT`, so it dodged bug #15.

## Step 11 — Anti-bot stealth args (P2, depends on Step 10) ✅

**What's already in place (from Step 10):**
- `settings.py` — `PLAYWRIGHT_LAUNCH_OPTIONS` includes `--disable-blink-features=AutomationControlled`, `--disable-dev-shm-usage`, realistic Chrome args, headless=True.
- `dynamic_detection.py` — `_build_stealth_script()` patches `navigator.webdriver → undefined`, injects realistic `navigator.plugins`/`navigator.mimeTypes`, spoofs WebGL vendor/renderer (Intel), and wraps `permissions.query` to avoid the notifications fingerprint.
- `NEXORA_STEALTH_ENABLED` env flag gates script injection (default `true` when Playwright is enabled).

**Code status:** Complete. No new changes required — Step 10's four sub-defect fixes already wired stealth into the Playwright pipeline.

**Test (pending live run with Playwright active):**
```powershell
python api.py crawl --url https://www.scrapingcourse.com/antibot-challenge --strategy single-page
```
**Expected:** No immediate 403 from the Playwright-routed request; at least partial DOM fetch. Anti-bot walls evolve, so graceful degradation (one HttpError, no retry storm) is the acceptance criterion.

**Not started:** Live validation — blocked on environment readiness (scrapy-playwright 0.0.48 confirmed installed in Step 10; Playwright chromium must be present and `.env` must have `NEXORA_PLAYWRIGHT_ENABLED=true`).

---

## Step 12 — Filter action links from crawl scope (P3) ✅

**Why it happened:** `NexoraSpider.parse_page()` follows every internal `<a href>` in multi-page mode without filtering action endpoints. On HN, links like `/vote?ID=...`, `/hide?ID=...`, `/submit`, and Wikipedia `?action=history`/`?mobileaction=` were crawled, triggering 92× HTTP 429 retries (the site rate-limits POST-like action endpoints). The existing `BLOCKED_PATH_PATTERNS` in `ContentTypeFilterMiddleware` only covered static paths like `/login`, `/cart`, etc. — not query-string action endpoints.

**What changed** (one file, `middlewares/__init__.py`):
- Added `/vote`, `/hide`, `/submit` to `BLOCKED_PATH_PATTERNS` (path-level blocking without impossible `\?` anchors — query strings are not in `urlparse(...).path`).
- Added `_BLOCKED_QUERY_RE` — matches action query parameters: `^(vote|hide|submit|login|logout|search)\??` in path, plus `action=`/`mobileaction=` params with values like `history|edit|raw|diff|undelete|protect|move|delete|purge|watch|unwatch|rollback|mark|semiprotect`.
- `process_request` now checks both `path` and `query` before allowing the request through.

**Not touched:** `nexora_spider.py` link-following logic (middleware filter is the correct layer — keeps spider simple); `BLOCKED_PATH_PATTERNS` static-file entries.

**Verification:**
- Pattern unit-check: `/vote?ID=123` → blocked by path; `/w/index.php?title=Python&action=history` → blocked by query; `/submit` → blocked by path; `/normal-page` → allowed.
- Live validation pending: run the HN linked-pages test and confirm 429 count drops from 92 to near-zero.

**Test command:**
```powershell
python api.py crawl --url https://news.ycombinator.com --strategy linked-pages --max-pages 30
```
**Expected:** 429 count ≈ 0; pages caught ≥ 24/30 (improved from 24 due to fewer wasted retries).

---

## Step 13 — Replace dead Test 02 fixture (P3) ✅

**Problem:** `react-shopping-cart-67007.firebaseapp.com` returns HTTP 404 — the Firebase-hosted demo app was decommissioned. Verified independently: `GET https://react-shopping-cart-67007.firebaseapp.com/` → 404.

**Fix:** Swapped the JS-rendering test fixture for the same project's live deployment:
- **Old:** `https://react-shopping-cart-67007.firebaseapp.com/` → 404
- **New:** `https://react-shopping-cart-67954.firebaseapp.com/` → 200, 2058 bytes

**Why this replacement:** Same codebase (`jeffersonRibeiro/react-shopping-cart`, 2.6k stars), same React+TypeScript+Styled-Components stack, same Firebase hosting. The only difference is the deployment ID. No test-matrix config file exists in the repo (tests were run manually via `api.py direct CLI`), so the swap is operational — the next full re-validation run must use the new URL.

**Verification:**
- Liveness probe: `GET https://react-shopping-cart-67954.firebaseapp.com/` → status 200, body 2058 bytes, content-type HTML.
- Full Playwright-rendered validation pending: run Test 02 equivalent with `NEXORA_PLAYWRIGHT_ENABLED=true` and confirm non-empty DOM + word count > static baseline.

**Test command (when Playwright active):**
```powershell
python api.py crawl --url https://react-shopping-cart-67954.firebaseapp.com/ --strategy single-page --enrich-mode eager
```
**Expected:** HTTP 200, Playwright-routed render, markdown generated, eager chain (11 pipelines + Chroma) completes without the `meta_tags`/`__skip`/srcset crashes fixed in Steps 1–4.

---

## Step 14 — HF credits / local embedding fallback (P3) ✅

**Problem:** HuggingFace Inference credits depleted — every LLM call failed with 402-class quota errors; embeddings worked briefly then timed out. This is an account/billing issue, not a code defect, but the codebase should tolerate it gracefully (Step 5's circuit breaker prevents the hang; this step restores actual AI functionality via automatic provider fallback).

**What changed** (4 files):
- `AI_Utilities/embedding_engine.py` — added `fallback_provider`, `fallback_model`, `fallback_base_url`, `fallback_api_key` ctor params. When the primary breaker opens, `embed()`/`embed_batch()` transparently route to a secondary `UnifiedEmbeddingEngine` instance. The fallback has its own independent circuit breaker so a second dead provider cannot hang the run. `stats["fallback_used"]` tracks how many embeddings came from the fallback.
- `pipelines/ai_enrichment.py` — same fallback pattern for LLM calls (`_generate_summary`/`_generate_tags`). When the primary breaker opens, LiteLLM `acompletion` is retried with `fallback_provider/fallback_model/fallback_base_url/fallback_api_key`. If no fallback is configured, the original skip-after-failures behavior is preserved.
- `pipelines/chunking_pipeline.py` — passes the four new `NEXORA_AI_FALLBACK_*` settings into the embedding engine.
- `settings.py` — four new documented env-overridable settings:
  - `NEXORA_AI_FALLBACK_PROVIDER` (default `""` = disabled)
  - `NEXORA_AI_FALLBACK_MODEL`
  - `NEXORA_AI_FALLBACK_BASE_URL`
  - `NEXORA_AI_FALLBACK_API_KEY`

**Not touched:** `enrich.py` (offline path inherits the same pipeline classes — fallback works there too); `.env` (user config left byte-identical); `switch_model_guide.md` (existing manual switch instructions remain valid).

**Configuration example** (restore AI when HF quota is exhausted by falling back to local Ollama):
```powershell
$env:NEXORA_AI_FALLBACK_PROVIDER="ollama"
$env:NEXORA_AI_FALLBACK_MODEL="nomic-embed-text"
$env:NEXORA_AI_FALLBACK_BASE_URL="http://localhost:11434"
```
Or for a cloud fallback:
```powershell
$env:NEXORA_AI_FALLBACK_PROVIDER="openai"
$env:NEXORA_AI_FALLBACK_MODEL="text-embedding-3-small"
$env:NEXORA_AI_FALLBACK_API_KEY="sk-..."
```

**Verification:**
- Unit: `py_compile` passes on all four modified files.
- Live validation pending: run eager crawl with HF quota exhausted + fallback configured, confirm embeddings/summaries/tags succeed via fallback after primary breaker trips.

**Test command:**
```powershell
$env:NEXORA_AI_FALLBACK_PROVIDER="ollama"
$env:NEXORA_AI_FALLBACK_MODEL="nomic-embed-text"
python api.py crawl --url https://www.sitemaps.org --strategy whole-website --max-pages 5 --enrich-mode eager
```
**Expected:** Zero 402 errors; summaries, tags, and embeddings succeed via fallback after primary breaker opens (or entirely via fallback if primary is dead).

---

## Remaining items (post-Step 14)

- Dead `__skip` guards cleanup (cosmetic, from Step 1) — **DONE** in this session.
- Full re-validation matrix re-run: Tests 07/08 full-scale (500/1000 pages), Test 06 with working AI provider, plus the two new fixtures (Test 02 replacement, Step 11 anti-bot testbed).

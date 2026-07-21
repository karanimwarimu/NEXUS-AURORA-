# 📊 NEXORA SYSTEM PERFORMANCE EVALUATION REPORT

**Run date:** 2026-07-20 · **Env:** conda `nexora` (Python 3.11.15, Scrapy 2.16.0) · **Runner:** `api.py` direct CLI · **Logs:** `outputs/qa_run_20260720/test01–10.log`
**Guardrail compliance:** zero source/config changes. Strategy names mapped to CLI ids (`just-this-page`→`single-page`, `everything-connected`→`everything`).

## Environment caveats (affect every score below)

1. **Playwright is OFF by config** — `.env` sets `NEXORA_PLAYWRIGHT_ENABLED=false` because installed scrapy-playwright 0.0.34 is incompatible with Scrapy 2.16 (`.env` comment says upgrade to ≥0.0.40). All fetches were static HTTP. JS-rendering scores measure the *fallback*, not Playwright.
2. **Hugging Face account has depleted monthly inference credits** — every LLM call failed (`402`-class quota error); embeddings worked briefly, then failed/timed out. Eager-mode AI numbers measure failure behavior, not generation.
3. Tests 06/07/08 were stopped early (06 hung post-cap; 07/08 cut short per operator instruction; 08 was 49/50 = effectively complete).

## 1. System Telemetry Scorecard

| Test | Target | Strategy | Pages Caught | Clean Words | JS Rendered? | AI Latency | Status / Errors |
|---|---|---|---|---|---|---|---|
| 01 | quotes.toscrape.com/js/ | single-page | 1/1 | **6** | **N** (static fallback) | N/A (on-demand) | ✅ Crawl OK · Parquet flush ERROR (`meta_tags` empty struct) · markdown_generated=0 |
| 02 | react-shopping-cart…firebaseapp.com | single-page (eager) | 0 | — | — | N/A (no items) | ⚠️ **Target site dead: HTTP 404** (independently confirmed). Eager chain (11 pipelines + Chroma) loaded correctly |
| 03 | news.ycombinator.com | linked-pages | 24/30 | avg 1,101 (max 10,750) | N | N/A | ⚠️ **92× HTTP 429**; 95 exponential-backoff retries (1s→2s→…); **6 items lost to `__skip` KeyError** (dup-dedup crash) |
| 04 | httpbin.org | linked-pages | 2/5 | 21 / 20 | N (Swagger UI is JS) | N/A | ✅ finished · Parquet `meta_tags` ERROR again |
| 05 | www.sitemaps.org | whole-website | 48/50 | avg 1,244 | N | N/A | ✅ **Sitemap via robots.txt → 84 URLs from XML tree, capped to 50** · 2× `__skip` errors |
| 06 | www.python.org | whole-website (eager) | 44 items / 157 fetches (**terminated**) | avg 2,984 (max 74,573) | N | see §2 | 🔴 **111 LLM failures (HF quota) · 296 embedding failures · 239 chunks → Chroma before quota cutoff · post-cap pipeline-drain HANG (0 items/min ≥9 min) — killed** |
| 07 | en.wikipedia.org/wiki/Web_scraping | everything | 82 items / 181 fetches (partial, 9 min) | avg 1,789 (max 29,154) | N | N/A | 🔴 **114× `__skip` dup crash · 53× MarkdownPipeline crash `int('2x')` (srcset)** · domain lock held |
| 08 | docs.python.org/3/ | everything (capped 50) | 49/50 | avg 9,259 (max 286,634) | N | N/A | ✅ near-clean: only 2 `__skip` errors · dense internal linking resolved by dupefilter |
| 09 | scrapingcourse.com/antibot-challenge | single-page | 0 | — | N (needed) | N/A | ✅ graceful: **403 WAF** → HttpError logged once, no retry storm (403 not in RETRY_HTTP_CODES) |
| 10 | httpbin.org/headers | single-page | 0 | — | N | N/A | ⚠️ JSON response **blocked by ContentTypeFilter → IgnoreRequest** (by design); header mirror unobservable via crawl |

Persistence check: SQLite `pages` grew 64 → **302 rows / 17 domains** across the run; per-page JSON/CSV + master CSV written every run; **Parquet exported 0 rows in every run that hit the `meta_tags` bug**.

## 2. Critical Architectural Takeaways

**Playwright JS Isolation Hook — NOT ACTIVE.** No `DynamicDetectionMiddleware`, Playwright handlers, or asyncio reactor in any run's enabled-middleware list. Word-count signatures confirm raw-HTTP parsing everywhere: quotes JS page = 6 words (150+ expected if JS ran), httpbin Swagger = ~21 words. This is a **dependency/config issue, not a code defect**: `.env` disables it pending a scrapy-playwright ≥0.0.40 upgrade. Every "JS Rendered?" = N must be re-scored after the upgrade.

**Eager vs On-Demand Overhead — eager is hazardous under provider failure.** On-demand throughput is politeness-bound (~2–3 s/page; the AI stack adds zero drag — validating the v4.3.0 decoupling design). In eager mode (Test 06), each page's `process_item` awaits summary+tags (paired failure round-trip ≈ 11 s observed: dispatch 23:04:51 → failure 23:05:02) plus per-chunk embeddings that, once HF quota depleted, **hung to the full 60 s read timeout per call at concurrency 2**. Result: downloads finished at 23:11, then the engine sat at 0 items/min for 9+ minutes with ~57 items queued in the pipeline — projected multi-hour drain before spider close. **There is no fail-fast/circuit-breaker: a dead AI provider converts an eager crawl into an effective hang.** (Resilience positive: crawl-side errors never propagated; pages were still saved to SQLite.)

**Sitemap Discovery & Scope Lock — VALIDATED.** Test 05: `Sitemap(s) found via robots.txt` → `[sitemap-leaf] 84 URLs to crawl from sitemap.xml` → capped to 50 — URLs pulled from the XML tree, not page anchors. Test 06 correctly logged `No sitemap found — falling back to link-following (depth=3)`. Domain lock and offsite filtering held in all multi-page runs (HN: 33 offsite filtered; Wikipedia stayed on-domain). Max-pages cap enforced everywhere.

**Errors Caught (runtime, reproducible, ranked):**
1. 🔴 **`KeyError: 'NexoraPageItem does not support field: __skip'`** — the duplicate-fingerprint path sets `item["__skip"]`, but the field isn't declared in `items.py`. Every duplicate page **crashes item processing instead of dropping** (HN ×6, sitemaps.org ×2, Wikipedia ×114, docs.python ×2 = 124 lost items this run). Worst on alias-heavy sites.
2. 🔴 **MarkdownPipeline: `invalid literal for int() with base 10: '2x'`** — image `srcset` density descriptors (`logo.png 2x`) break the multimodal/markdown path; 53/53 attempted Wikipedia pages produced **no markdown**, which starves chunking/enrichment (RAG-blocking for image-dense sites).
3. 🔴 **Eager pipeline-drain hang** (see above) — provider outage + 60 s timeouts + no short-circuit.
4. 🟠 **`robots.txt` responses blocked by ContentTypeFilterMiddleware** (`[BLOCK-resp] non-HTML [text/plain] -> …/robots.txt`, observed in 8 logs). `ROBOTSTXT_OBEY=True` requests robots.txt, but the filter discards the response before parsing — robots rules are likely **never applied** (compliance risk masked by the "block non-HTML" feature).
5. 🟠 **Parquet flush failure**: `Cannot write struct type 'meta_tags' with no child field` — Parquet export produced **0 rows** in affected runs.
6. 🟠 **Crawl hygiene**: spider follows action links (`vote?`, `hide?`, `submit`, `login`) — this is what triggered HN's 92× 429 storm; URL pattern filter doesn't cover them.
7. 🟢 Graceful handling confirmed for: 404 (Tests 01-robots/02), 403 WAF (Test 09, single error, no retry loop), 429 (backoff with escalating delays + Retry-After), JSON content rejection (Test 10, `IgnoreRequest` by design).

**Environment items (not code):** HF credits depleted (blocks all AI until topped up or provider switched — `switch_model_guide.md` covers the swap); scrapy-playwright needs upgrade to ≥0.0.40 + `playwright install chromium`; Test 02's demo site no longer exists — replace in the matrix.

**Carried-forward static findings (from pre-test code review, unchanged):** `enrich.py --limit` passes `None` → `LIMIT NULL` when no filter flags; `--limit` ignored with `--domain`/`--crawl-id`; `_enrich_row` reads `ai_tags` but the DB column is `ai_tags_json`; float `token_count` from `len(markdown)//4.5`; `build_vector_store()` fallback defaults (pgvector/768) diverge from settings (chroma/384).

## Recommended next actions (deferred, per operator)
1. Fix `__skip` (declare field or use raw `DropItem`) — cheap, recovers ~5–60% of items on dup-heavy sites.
2. Fix srcset `'2x'` int-parse in the markdown/multimodal path.
3. Add fail-fast/circuit-breaker to eager AI calls (skip remaining AI after N consecutive provider failures).
4. Exempt `robots.txt` from ContentTypeFilter response blocking.
5. Fix Parquet empty-struct `meta_tags` serialization.
6. Upgrade scrapy-playwright, re-enable, and re-run Zone A + Test 09 (JS + anti-bot re-score).
7. Re-run full-scale Tests 07/08 (500/1000 pages) and Test 06 with a funded/working AI provider.

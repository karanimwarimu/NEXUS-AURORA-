# Nexora v4.5.0 — Open Items Resolution (crawl_id & Resource Blocking)

**Release Date:** 2026-07-27  
**Build State:** v4.4.0 + two open items from Debug Round 2 resolved and verified  
**Branch:** `phase4b_openitems`

---

## Overview

This release closes the two remaining functional gaps identified in Debug Round 2 (2026-07-25 QA run). Both items were straightforward code changes with no new dependencies, and both have been verified with live test data.

---

## What's New

### Fixed

#### Item 1: `crawl_id` Propagation — ✅ Fixed & Verified

**Problem:** Every row in the SQLite `pages` table had `crawl_id = ""` (empty string). Multi-crawl environments could not distinguish which pages belonged to which crawl run. The `--crawl-id` filter in `enrich.py` returned all rows instead of filtering.

**Root cause chain:**
1. `api.py:_run_crawl_sync` created the spider as `NexoraSpider(urls=seed_url, strategy=strategy, max_pages=max_pages)` — **no `crawl_id` argument was passed**
2. `nexora_spider.py:__init__` accepted `crawl_id: str = ""` with an empty-string default
3. `schema_enricher.py:process_item` read `spider.crawl_id` — got `""` every time
4. SQLite `pages` table received `crawl_id = ""` for every row

**Fix:**
- `nexora_crawler/api.py:28` — Added `import uuid`
- `nexora_crawler/api.py:487` — In `_run_crawl_sync`, generates `crawl_id = uuid.uuid4().hex`
- `nexora_crawler/api.py:489-494` — Passes `crawl_id=crawl_id` to `process.crawl(...)`
- `nexora_crawler/spiders/nexora_spider.py:104` — Signature already had `crawl_id: str = ""` parameter; stores it at `self.crawl_id = crawl_id` (line 114)

**Verification:**

After fix, running:
```powershell
python api.py crawl --url https://books.toscrape.com --strategy single-page
python api.py crawl --url https://quotes.toscrape.com/js/ --strategy single-page
```

SQLite `pages` table shows non-empty `crawl_id` for every row:

| Site | crawl_id |
|------|----------|
| books.toscrape.com | `6559b5c4be5d4471b99a2e6ad521b063` |
| quotes.toscrape.com/js/ | `cff109aa13df4861b06c6d490f2b3dd6` |
| react-shopping-cart-67954.firebaseapp.com | `2609e6c47df14fe9aa9c31011098ebe9` |

#### Item 2: `PLAYWRIGHT_BLOCKED_RESOURCE_TYPES` Wiring — ✅ Fixed & Verified

**Problem:** `settings.py` defined `PLAYWRIGHT_BLOCKED_RESOURCE_TYPES = {'image', 'font', 'media', 'ping'}`, but nothing in the codebase read or acted on it. Playwright still loaded every image, font, media file, and ping request on routed pages, wasting bandwidth and increasing render time on content-heavy sites.

**Root cause:**
- The setting was defined but never referenced anywhere
- The Playwright resource blocking in `playwright_resource_blocker.py` operated at the JS level (fetch/XHR/sendBeacon), not at the Playwright route level
- scrapy-playwright supports `PLAYWRIGHT_ABORT_REQUEST` for per-request route abort, but it was never configured

**Fix (correct mechanism — `PLAYWRIGHT_ABORT_REQUEST`, not `playwright_page_methods`):**

The original open-items document proposed using `playwright_page_methods` with a `route()` handler. However, scrapy-playwright's `_apply_page_methods` is called **after** page navigation (line 382 in the handler), so `PageMethod("route", ...)` was attached too late to intercept subresource requests.

The correct mechanism is `PLAYWRIGHT_ABORT_REQUEST`, which registers a per-request abort callback that runs **before** each request is continued:

**`nexora_crawler/middlewares/dynamic_detection.py`:**
- Added module-level `_blocked_resource_types: set = set()` variable
- Added `_abort_blocked_resources(playwright_request) -> bool` callback that returns `True` to abort requests whose `resource_type` is in the blocked set
- In `DynamicDetectionMiddleware.__init__`, syncs the module-level variable from settings: `_blocked_resource_types = self.settings.get("PLAYWRIGHT_BLOCKED_RESOURCE_TYPES", set())`

**`nexora_crawler/settings.py`:**
- Added: `PLAYWRIGHT_ABORT_REQUEST = "nexora_crawler.middlewares.dynamic_detection._abort_blocked_resources"`
- `PLAYWRIGHT_BLOCKED_RESOURCE_TYPES` was already defined (no change needed)

**Verification — Resource blocking confirmed:**

| Site | Before Fix | After Fix |
|------|------------|-----------|
| react-shopping-cart-67954.firebaseapp.com | 17 image requests, 17 image responses | 17 aborted, 0 image responses |
| en.wikipedia.org/wiki/Web_scraping | 24 image requests, 24 image responses | 26 aborted, 0 image responses |
| quotes.toscrape.com/js/ | 1 font request, 1 font response | 1 aborted, 0 font responses |

Scripts, stylesheets, and XHR requests continue to load normally on all sites.

---

## Files Changed Since v4.4.0

### Modified Files

| File | Change |
|------|--------|
| `Crawler/nexora_crawler/api.py` | Added `import uuid`; `_run_crawl_sync` generates and passes `crawl_id` to spider |
| `Crawler/nexora_crawler/middlewares/dynamic_detection.py` | Added module-level `_blocked_resource_types` variable + `_abort_blocked_resources` callback; `__init__` syncs from settings |
| `Crawler/nexora_crawler/settings.py` | Added `PLAYWRIGHT_ABORT_REQUEST` setting pointing to `_abort_blocked_resources` |

### New Files

- `outputs/qa_run_20260720/NEXORA_OPEN_ITEMS_NEXT_SESSION.md` — Open items document from previous session (resolved in this release)
- `outputs/qa_run_20260720/NEXORA_DEBUG_ROUND2_FIXES_APPLIED.md` — Debug Round 2 fixes applied report

---

## Verification

### crawl_id Verification

```python
from nexora_crawler.storage.local_sqlite import MetadataStore
store = MetadataStore()
rows = store.query_by_domain("books.toscrape.com")
print(rows[0]["crawl_id"])  # e.g. "6559b5c4be5d4471b99a2e6ad521b063"
```

### Resource Blocking Verification

Check Playwright logs for:
- `playwright/request_count/resource_type/image` — should be **0** (all aborted)
- `playwright/request_count/resource_type/font` — should be **0**
- Page still renders correctly (text + scripts loaded)
- Scripts, stylesheets, and XHR resource counts are unchanged

---

## Known Limitations (Post v4.5.0)

- **Full re-validation matrix not yet re-run** — Tests 06/07/08 need full-scale re-runs with working AI provider + Playwright active.
- **Step 11/12/13/14 live validation pending** — unit checks and code changes done; live crawl verification blocked on environment readiness.
- **Chunk size overshoot** — avg ≈ 680 tokens/chunk vs 512 target (overlap-driven; tracked as nice-to-have).

### Resolved in v4.5.0

- ~~`crawl_id` not populated~~ — `api.py` now generates a UUID per crawl and passes it to the spider; every SQLite row has a non-empty `crawl_id`.
- ~~`PLAYWRIGHT_BLOCKED_RESOURCE_TYPES` not wired~~ — Route-level abort callback blocks image/font/media/ping requests before they reach the network.

### Resolved in v4.4.0

All items from the 14-step debug campaign remain resolved.

---

## Upgrade Notes

1. **No database migration needed** — The `crawl_id` fix is forward-only: new crawls will have `crawl_id` populated; existing rows remain as `""`. If you need to backfill, re-run affected crawls.
2. **Resource blocking is automatic** — No configuration changes needed. The `PLAYWRIGHT_BLOCKED_RESOURCE_TYPES` set in `settings.py` controls which resource types are aborted.
3. **Playwright** — Requires `scrapy-playwright>=0.0.48` which supports `PLAYWRIGHT_ABORT_REQUEST`.

---

## Companion Documents

| Document | Location |
|----------|----------|
| Open Items (Original) | `outputs/qa_run_20260720/NEXORA_OPEN_ITEMS_NEXT_SESSION.md` |
| Debug Round 2 Fixes Applied | `outputs/qa_run_20260720/NEXORA_DEBUG_ROUND2_FIXES_APPLIED.md` |
| Session Handoff | `NEXORA_SESSION_HANDOFF.md` |
| Repository Structure | `REPOSITORY_STRUCTURE.md` |
| Model/Provider/Backend Switch Guide | `Project Tools/switch_model_guide.md` |
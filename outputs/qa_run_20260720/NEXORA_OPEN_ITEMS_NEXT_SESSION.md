# Nexora — Open Items for Next Session

**Date:** 2026-07-27  
**Context:** Debug Round 2 live tests complete. Two functional gaps remain before Phase 4C readiness.  
**Estimated effort:** ~30 minutes total.

---

## Item 1: `crawl_id` Propagation

### What's broken
Every row in the SQLite `pages` table has `crawl_id = ""` (empty string). This means:
- `enrich.py --crawl-id <id>` returns **all rows** instead of filtering by crawl
- Multi-crawl environments cannot distinguish which pages belong to which crawl run
- Audit/traceability is broken

### Root cause chain

| Step | File | Line | What happens |
|------|------|------|--------------|
| 1 | `api.py:run_crawl_sync` | ~487 | Spider is created as `NexoraSpider(urls=seed_url, strategy=strategy, max_pages=max_pages)` — **no `crawl_id` argument is passed** |
| 2 | `nexora_spider.py:__init__` | ~95 | `self.crawl_id = crawl_id` gets the kwarg value, which defaults to `""` |
| 3 | `schema_enricher.py:process_item` | ~111 | `crawl_id = spider.crawl_id` reads from the spider — gets `""` every time |
| 4 | SQLite `pages` table | — | Every row gets `crawl_id = ""` |

### What needs to change

**Option A (recommended — API layer):**
1. In `api.py:run_crawl_sync`, generate a UUID before creating the spider:
   ```python
   import uuid
   crawl_id = uuid.uuid4().hex
   ```
2. Pass it to the spider:
   ```python
   spider = NexoraSpider(
       urls=seed_url,
       strategy=strategy,
       max_pages=max_pages,
       crawl_id=crawl_id,  # <-- add this
   )
   ```
3. Optionally include `crawl_id` in the API response so the caller can reference it later.

**Option B (spider self-contained):**
1. In `nexora_spider.py:__init__`, auto-generate if missing:
   ```python
   import uuid
   self.crawl_id = crawl_id or uuid.uuid4().hex
   ```
2. No changes to `api.py`.

**Either option works because** `UnifiedSchemaEnricher.process_item` already reads `spider.crawl_id` correctly — the spider just never gets a real value.

### Verification
After fix, run:
```powershell
python api.py crawl --url https://example.com --strategy single-page
```
Then check SQLite:
```python
from nexora_crawler.storage.local_sqlite import MetadataStore
store = MetadataStore()
rows = store.query_by_domain("example.com")
print(rows[0]["crawl_id"])  # should be non-empty UUID
```

---

## Item 2: `PLAYWRIGHT_BLOCKED_RESOURCE_TYPES` Wiring

### What's broken
`settings.py` defines `PLAYWRIGHT_BLOCKED_RESOURCE_TYPES = {'image', 'font', 'media', 'ping'}`, but nothing in the codebase reads or acts on it. Playwright still loads every image, font, media file, and ping request on routed pages. This wastes bandwidth and increases render time on content-heavy sites.

### Root cause chain

| Step | File | What happens |
|------|------|--------------|
| 1 | `settings.py:199-200` | `PLAYWRIGHT_BLOCKED_RESOURCE_TYPES` is defined as a Python set — **never referenced anywhere** |
| 2 | `dynamic_detection.py:_apply_playwright_meta` | Sets `request.meta["playwright"] = True` but doesn't touch resource blocking |
| 3 | `playwright_resource_blocker.py` | Blocks at the **JS level** (fetch/XHR/sendBeacon via `page.evaluate`), NOT at the **Playwright route level** (image/font/media/ping) |
| 4 | `scrapy-playwright` handler | Supports `playwright_page_methods` for route interception, but we never configure it |

### What needs to change

**In `dynamic_detection.py:_apply_playwright_meta`** (~line 450-490):

Add a `playwright_page_methods` entry that registers Playwright route interception. The method should:
1. Read `PLAYWRIGHT_BLOCKED_RESOURCE_TYPES` from settings
2. Call `page.route("**/*", handler)` to intercept all requests
3. Abort requests whose `resource_type` is in the blocked set
4. Continue all other requests

Pseudocode:
```python
blocked_types = crawler.settings.getlist("PLAYWRIGHT_BLOCKED_RESOURCE_TYPES", [])

def _block_resources(route):
    resource_type = route.request.resource_type
    if resource_type in blocked_types:
        return route.abort()
    return route.continue_()

page_methods.append(_block_resources)
```

Then attach `page_methods` to the request meta:
```python
request.meta["playwright_page_methods"] = page_methods
```

**In `settings.py`:** No changes needed — the setting already exists.

**In `playwright_resource_blocker.py`:** No changes needed — it handles JS-level analytics (fetch/XHR/sendBeacon), which is complementary to route-level image/font/media blocking.

### Verification
After fix, run:
```powershell
python api.py crawl --url https://quotes.toscrape.com/js/ --strategy single-page
```
Check logs for:
- `playwright/request_count/resource_type/image` should be **0** (or significantly reduced)
- `playwright/request_count/resource_type/font` should be **0**
- Page still renders correctly (text + scripts loaded)

---

## Quick Reference

| Item | File to edit | Lines (approx) | Change type |
|------|-------------|-----------------|-------------|
| `crawl_id` propagation | `api.py` | ~487 | Add `crawl_id` generation + pass to spider |
| `PLAYWRIGHT_BLOCKED_RESOURCE_TYPES` wiring | `dynamic_detection.py` | ~450-490 | Add `playwright_page_methods` route interceptor |

---

## Dependencies / Prerequisites

- None — both are standalone code changes
- No new dependencies required
- `scrapy-playwright` 0.0.48 already supports `playwright_page_methods`

---

## Acceptance Criteria

| Item | Pass condition |
|------|----------------|
| `crawl_id` | `SELECT crawl_id FROM pages WHERE url = '...'` returns non-empty UUID for every row |
| Resource blocking | Playwright logs show 0 image/font/media/ping requests on a test page that normally loads them |

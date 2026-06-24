
# Nexora Phase 2.6 — Testing Strategy & Architecture Decisions

## Table of Contents
1. [Vigorous Testing Plan](#1-vigorous-testing-plan)
2. [Why CLI and FastAPI Are Separate](#2-why-cli-and-fastapi-are-separate)
3. [Leveraging for UI, API, and Local Use](#3-leveraging-for-ui-api-and-local-use)

---

## 1. Vigorous Testing Plan

Based on industry testing pyramid principles citeweb_search:26#4 and FastAPI async testing patterns citeweb_search:26#1web_search:26#2web_search:26#7, here is the comprehensive test suite:

### Test Layers

| Layer | Count | Speed | Purpose |
|-------|-------|-------|---------|
| **Unit Tests** | 20+ | <100ms each | Individual functions in isolation |
| **Integration Tests** | 8 | <2s each | Spider + pipeline + API interactions |
| **E2E Tests** | 3 | 5-30s each | Real HTTP calls, full crawl simulation |
| **Performance Tests** | 2 | Variable | Large sitemaps, timeout handling |
| **Security Tests** | 3 | <500ms | XSS, URL validation, bounds checking |
| **Regression Tests** | 4 | <2s | Previously fixed bugs |

### Test Categories (all implemented in `test_nexora_phase26.py`)

#### A. SitemapDetector Unit Tests (8 tests)
- `test_from_robots_txt_parses_sitemap_directives` — Parses `Sitemap:` lines correctly
- `test_from_robots_txt_handles_missing_sitemap` — Empty robots.txt returns []
- `test_from_robots_txt_handles_404` — 404 returns []
- `test_from_common_paths_finds_sitemap` — HEAD request finds `/sitemap.xml`
- `test_from_common_paths_none_found` — All 404s returns None
- `test_parse_single_sitemap_urlset` — Parses `<urlset>` with 3 URLs
- `test_parse_single_sitemap_index` — Parses `<sitemapindex>` with 2 sub-sitemaps
- `test_fetch_urls_recurses_index` — Recursively resolves index → leaf → URLs
- `test_discover_full_flow` — End-to-end: robots.txt → sitemap → URLs

#### B. Strategy Resolution Unit Tests (8 tests)
- `test_explicit_sitemap_wins` — `-a sitemap="..."` overrides everything
- `test_single_page_strategy` — `strategy="single-page"` → depth=0
- `test_linked_pages_strategy` — `strategy="linked-pages"` → depth=1
- `test_whole_website_strategy` — `strategy="whole-website"` → auto mode, depth=3
- `test_everything_strategy` — `strategy="everything"` → depth=5, domain_lock=True
- `test_backwards_compat_depth` — Legacy `-a depth=2` still works
- `test_default_single_page` — No args → single-page
- `test_max_pages_safety_cap` — `-a max_pages=500` enforced
- `test_invalid_strategy_defaults` — Unknown strategy → single-page fallback

#### C. NexoraPageItem Unit Tests (3 tests)
- `test_item_creation_with_all_fields` — All required fields set correctly
- `test_item_fields_exist` — All 30+ fields defined in Item class
- `test_item_rejects_unknown_field` — Scrapy validation prevents KeyError

#### D. FastAPI Integration Tests (5 tests)
- `test_root_endpoint` — GET / returns service info
- `test_list_strategies` — GET /strategies returns 4 strategies with descriptions
- `test_crawl_invalid_url` — POST with "not-a-url" → 422 validation error
- `test_crawl_valid_request` — POST with valid URL → job created, status=running
- `test_get_job_not_found` — GET /crawl/nonexistent → 404

#### E. Spider-Pipeline Integration Tests (5 tests)
- `test_parse_page_yields_item` — parse_page yields NexoraPageItem (not dict)
- `test_parse_page_with_links` — Multi-page mode follows internal links
- `test_domain_lock_blocks_external_links` — "everything" strategy blocks external
- `test_max_pages_cap` — Stops yielding after max_pages reached

#### F. E2E / Real HTTP Tests (2 tests)
- `test_sitemap_detector_real_httpbin` — httpbin.org has no sitemap (returns [])
- `test_sitemap_detector_real_github` — GitHub has sitemap in robots.txt

#### G. Performance Tests (2 tests)
- `test_sitemap_detector_timeout` — Slow site returns [] (doesn't hang)
- `test_large_sitemap_parsing` — 1000 URLs parsed in <1s

#### H. Security Tests (3 tests)
- `test_item_no_xss_injection` — Item stores raw HTML (pipelines sanitize)
- `test_url_validation_in_api` — Pydantic rejects malformed URLs
- `test_max_pages_bounds` — Enforces 1 ≤ max_pages ≤ 50000

#### I. Regression Tests (4 tests)
- `test_styles_field_exists` — KeyError 'styles' never happens again
- `test_spider_yields_item_not_dict` — Always yields NexoraPageItem
- `test_pipeline_async_signatures` — All process_item are async def
- `test_middleware_no_spider_arg` — No spider param in middleware methods

### Running the Tests

```bash
# All tests
pytest tests/test_nexora_phase26.py -v

# Only unit tests (fast)
pytest tests/test_nexora_phase26.py -v -k "unit" --ignore-glob="*e2e*"

# Only integration tests
pytest tests/test_nexora_phase26.py -v -k "integration"

# Only real HTTP tests (slow, requires internet)
pytest tests/test_nexora_phase26.py -v -k "real" -m slow

# With coverage report
pytest tests/test_nexora_phase26.py --cov=nexora_crawler --cov-report=html

# Parallel execution (4 workers)
pytest tests/test_nexora_phase26.py -n 4
```

### CI/CD Pipeline (GitHub Actions example)

```yaml
name: Test Nexora Crawler
on: [push, pull_request]
jobs:
  test:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with: { python-version: '3.11' }
      - run: pip install -r requirements.txt
      - run: pip install pytest pytest-asyncio pytest-cov httpx
      - run: pytest tests/test_nexora_phase26.py -v --cov=nexora_crawler
      - run: pytest tests/test_nexora_phase26.py -v -k "real" -m slow
        env:
          INTERNET_TESTS: "1"
```

---

## 2. Why CLI and FastAPI Are Separate

### The Design Decision

The `api.py` file contains **both** interfaces in one module, but they are **separate entrypoints** by design:

```python
# api.py
if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "--server":
        uvicorn.run("nexora_crawler.api:app", ...)   # FastAPI mode
    else:
        run_cli()                                      # Interactive CLI mode
```

### Why This Separation Matters

| Aspect | CLI Mode | FastAPI Mode |
|--------|----------|--------------|
| **User** | Developer / tester | Frontend / API consumer |
| **Interface** | Terminal prompts | HTTP JSON endpoints |
| **Blocking** | Yes (synchronous user input) | No (async request/response) |
| **State** | In-memory only | In-memory + extensible to Redis/DB |
| **Concurrency** | Single crawl at a time | Multiple crawls simultaneously |
| **Use case** | Local testing, debugging | Production API, UI backend |

### Why Not Combine Them?

1. **Different I/O models**: CLI uses `input()` (blocking), FastAPI uses async HTTP (non-blocking). Mixing them creates event loop conflicts.

2. **Different lifecycles**: CLI runs once and exits. FastAPI stays running as a daemon. Scrapy's `CrawlerProcess` is designed for one-shot execution — running it inside a long-lived server requires careful process management citeweb_search:26#6.

3. **Different error handling**: CLI shows tracebacks directly. API returns JSON error responses with HTTP status codes.

4. **Different scaling**: CLI is single-user. API needs job queues (Celery/RQ) for concurrent crawls citeweb_search:26#6.

### The Shared Core

Both interfaces use the **same underlying logic**:
- `NexoraSpider` — same spider class
- `SitemapDetector` — same discovery logic
- `STRATEGY_MAP` — same strategy definitions
- `ITEM_PIPELINES` — same pipeline chain

Only the **entrypoint and wrapping** differ.

---

## 3. Leveraging for UI, API, and Local Use

### Three Deployment Targets from One Codebase

```
                    ┌─────────────────┐
                    │  Nexora Core    │
                    │  (spider +      │
                    │   pipelines +   │
                    │   detector)     │
                    └────────┬────────┘
                             │
        ┌────────────────────┼────────────────────┐
        │                    │                    │
        ▼                    ▼                    ▼
   ┌─────────┐        ┌──────────┐        ┌──────────┐
   │   CLI   │        │ FastAPI  │        │  Celery  │
   │  Mode   │        │  Server  │        │  Worker  │
   │         │        │          │        │          │
   │ python  │        │ uvicorn  │        │ worker   │
   │ -m api  │        │ api:app  │        │ -A tasks │
   └────┬────┘        └────┬─────┘        └────┬─────┘
        │                  │                   │
        ▼                  ▼                   ▼
   Terminal          Browser/HTTP          Background
   (local dev)       (production)          (queue)
```

### A. Local Use (CLI)

**Target audience**: Developers, testers, power users

```bash
# Run interactively
python -m nexora_crawler.api

# Or pass arguments directly (non-interactive)
python -m nexora_crawler.api --url "https://example.com" --strategy whole-website
```

**Advantages**:
- No dependencies beyond Python + Scrapy
- Immediate feedback in terminal
- Perfect for debugging pipeline issues
- No network ports, no firewall issues

### B. API Use (FastAPI)

**Target audience**: Other services, mobile apps, frontend SPAs

```bash
# Start server
python -m nexora_crawler.api --server
# or
uvicorn nexora_crawler.api:app --host 0.0.0.0 --port 8000
```

**API Consumers**:
```javascript
// React/Vue frontend
const startCrawl = async () => {
  const res = await fetch("http://localhost:8000/crawl", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      url: "https://example.com",
      strategy: "whole-website",
      max_pages: 500
    })
  });
  const job = await res.json();
  return job.job_id;  // Poll /crawl/{job_id} for status
};
```

**Advantages**:
- Language-agnostic (any client can call HTTP)
- Auto-generated docs at `/docs` (Swagger UI)
- Async by default — multiple crawls concurrently
- Easy to add auth, rate limiting, logging middleware

### C. UI Integration (Frontend)

**Architecture**:
```
┌─────────────┐     HTTP/JSON      ┌─────────────┐     subprocess      ┌─────────┐
│  React/Vue  │ ◄────────────────► │  FastAPI    │ ◄─────────────────► │ Scrapy  │
│   Frontend  │   (poll status)    │   Backend   │   (CrawlerProcess)  │ Spider  │
│             │                    │             │                     │         │
│ - URL input │                    │ - Validate  │                     │ - Crawl │
│ - Strategy  │                    │ - Queue job │                     │ - Save  │
│   picker    │                    │ - Return    │                     │   output│
│ - Progress  │                    │   job_id    │                     │         │
│   bar       │                    │ - Poll      │                     │         │
│ - Results   │                    │   status    │                     │         │
│   viewer    │                    │             │                     │         │
└─────────────┘                    └─────────────┘                     └─────────┘
```

**Frontend components needed**:
1. **URL Input** — Text field with URL validation
2. **Strategy Picker** — Radio buttons / dropdown:
   - "Just this page" (single-page)
   - "This page + linked pages" (linked-pages)
   - "The whole website" (whole-website)
   - "Everything connected" (everything)
3. **Advanced Options** — Collapsible: max_pages, custom sitemap URL
4. **Progress Dashboard** — Poll `GET /crawl/{job_id}` every 2s:
   ```json
   {
     "job_id": "job_20240624_155432_7f3a2b",
     "status": "running",
     "pages_crawled": 47,
     "strategy": "whole-website",
     "message": "Crawl in progress..."
   }
   ```
5. **Results Viewer** — Table of crawled pages with export buttons

### D. Scaling to Production (Celery + Redis)

For high-volume production, replace in-memory job store with Celery:

```python
# tasks.py (Celery worker)
from celery import Celery
from scrapy.crawler import CrawlerProcess

app = Celery('nexora', broker='redis://localhost:6379')

@app.task
def crawl_task(url: str, strategy: str, max_pages: int):
    process = CrawlerProcess(get_project_settings())
    process.crawl("nexora", urls=url, strategy=strategy, max_pages=max_pages)
    process.start()
    return {"status": "completed", "output_dir": "output/"}
```

```python
# FastAPI endpoint (updated)
from tasks import crawl_task

@app.post("/crawl")
async def start_crawl(request: CrawlRequest):
    task = crawl_task.delay(
        url=str(request.url),
        strategy=request.strategy,
        max_pages=request.max_pages
    )
    return {
        "job_id": task.id,
        "status": "queued",
        "message": "Crawl queued for execution"
    }
```

**Benefits**:
- Crawls run in background workers (not blocking API)
- Redis queue handles burst traffic
- Multiple workers scale horizontally
- Flower dashboard monitors queue health citeweb_search:26#6

---

## Summary

| Question | Answer |
|----------|--------|
| **How to test vigorously?** | 25+ tests across 6 categories: unit, integration, E2E, performance, security, regression |
| **Why separate CLI and FastAPI?** | Different I/O models, lifecycles, and scaling needs. Same core logic, different wrappers. |
| **How to leverage for UI?** | FastAPI serves JSON → React/Vue polls for status → displays progress + results |
| **How to leverage for API?** | Direct HTTP endpoints with auto-generated docs, Pydantic validation, async by default |
| **How to run locally?** | `python -m nexora_crawler.api` — interactive prompts, no server needed |
| **How to scale?** | Add Celery + Redis for background job queue, multiple workers |

The architecture is designed for **progressive enhancement**: start with CLI for development, add FastAPI for integration, add Celery for production scale — all using the same spider core.

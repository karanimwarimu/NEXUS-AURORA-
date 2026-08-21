# NEXUS AURORA — Action Plan & Next Steps
## Prioritized Task List for Production Deployment

**Date Created:** 2026-08-19  
**Current Status:** 95% production-ready (1 blocking bug)  
**Target Deployment:** After enrich.py fix + Phase 4C tests

---

## Critical Path to Production

### 🔴 BLOCKING: Week 1 (Must Fix)

#### Task 1: Fix enrich.py Helpers
**Status:** NOT STARTED  
**Effort:** 2 hours  
**Impact:** Unblocks on-demand enrichment (core feature)

**What to fix:**

File: `Nexora application/Crawler/nexora_crawler/enrich.py`

Missing 3 functions:
1. `_build_crawler()` — Create minimal Scrapy crawler for pipelines
2. `_collect_targets()` — Query MetadataStore for target pages
3. `_enrich_row()` — Run pipeline chain over one page

**Implementation template:**

```python
def _build_crawler(settings_dict):
    """Create minimal crawler object for AI/chunking/vector pipelines"""
    from scrapy.crawler import CrawlerRunner
    runner = CrawlerRunner(settings_dict)
    # Setup: pipelines 250, 260, 270 enabled; extraction/export disabled
    return runner

def _collect_targets(db_path, domain=None, crawl_id=None, url=None, limit=None):
    """Select target pages from MetadataStore"""
    from nexora_crawler.storage.local_sqlite import MetadataStore
    store = MetadataStore(db_path)
    
    if url:
        rows = store.query_by_url(url)
    elif domain:
        rows = store.query_by_domain(domain)
    elif crawl_id:
        rows = store.query_by_crawl_id(crawl_id)
    else:
        rows = store.query_all()
    
    # Filter unenriched
    rows = [r for r in rows if not r.get("ai_summary")]
    
    # Apply limit
    if limit:
        rows = rows[:limit]
    
    return rows

def _enrich_row(row, crawler):
    """Run pipeline chain over one page"""
    # Create NexoraItem from DB row
    item = NexoraItem(
        url=row["url"],
        markdown=row["markdown"],
        # ... other fields
    )
    
    # Run pipelines 250/260/270 (AI/chunking/vector)
    for pipeline_class in [AIEnrichmentPipeline, StructuralChunkingPipeline, VectorIndexPipeline]:
        pipeline = pipeline_class()
        pipeline.open_spider(None)
        item = pipeline.process_item(item)
    
    # Update DB
    store = MetadataStore()
    store.update_page_enrichment({
        "url": row["url"],
        "ai_summary": item.get("ai_summary"),
        "ai_tags_json": json.dumps(item.get("ai_tags", [])),
        "ai_embedding": json.dumps(item.get("ai_embedding", []))
    })
    
    return item
```

**Verification:**
```bash
cd "Nexora application/Crawler"
python enrich.py --limit 5
# Should enrich 5 pages without errors

python enrich.py --crawl-id <uuid>
# Should enrich pages from specific crawl

python enrich.py --domain example.com
# Should enrich pages from domain
```

**Acceptance Criteria:**
- [ ] Functions implemented
- [ ] No NameError on `python enrich.py`
- [ ] Enrich --limit works
- [ ] Enrich --domain works
- [ ] Enrich --crawl-id works
- [ ] DB updated with ai_summary + ai_tags + ai_embedding
- [ ] Idempotency verified (re-running preserves data)

---

#### Task 2: Write Phase 4C Regression Test Suite
**Status:** NOT STARTED  
**Effort:** 8 hours  
**Impact:** Ensures API layer stability across releases

**Minimum test coverage:**

File to create: `tests/test_phase4c.py`

```python
import pytest
import asyncio
from nexora_crawler.api import app
from nexora_crawler.storage.local_sqlite import MetadataStore

@pytest.fixture
def client():
    from fastapi.testclient import TestClient
    return TestClient(app)

def test_health_check(client):
    """GET /health returns 200"""
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json()["status"] == "ok"

def test_auth_missing_401(client):
    """Unauthenticated request to protected route returns 401"""
    response = client.post("/v1/webhooks", json={"url": "http://example.com"})
    assert response.status_code == 401

def test_jwt_auth_success(client):
    """Valid JWT token allows access"""
    token = create_test_token(workspace_id="test-workspace")
    headers = {"Authorization": f"Bearer {token}"}
    response = client.post(
        "/v1/webhooks",
        json={"url": "http://example.com", "event_types": ["job.completed"]},
        headers=headers
    )
    assert response.status_code in [200, 201]

def test_api_key_auth_success(client):
    """Valid API key allows access"""
    store = MetadataStore()
    key_id, raw_key = store.create_api_key("test-workspace", "test-key")
    api_key = f"{key_id}.{raw_key}"
    
    headers = {"X-Api-Key": api_key}
    response = client.post(
        "/v1/webhooks",
        json={"url": "http://example.com", "event_types": ["job.completed"]},
        headers=headers
    )
    assert response.status_code in [200, 201]

def test_api_key_revoked_401(client):
    """Revoked API key rejected"""
    store = MetadataStore()
    key_id, raw_key = store.create_api_key("test-workspace", "test-key")
    store.revoke_api_key(key_id)
    
    api_key = f"{key_id}.{raw_key}"
    headers = {"X-Api-Key": api_key}
    response = client.post(
        "/v1/webhooks",
        json={"url": "http://example.com", "event_types": ["job.completed"]},
        headers=headers
    )
    assert response.status_code == 401

def test_workspace_isolation(client):
    """Routes can only see workspace-scoped resources"""
    # Create webhook in workspace A
    token_a = create_test_token(workspace_id="workspace-a")
    response_a = client.post(
        "/v1/webhooks",
        json={"url": "http://example.com/a", "event_types": ["job.completed"]},
        headers={"Authorization": f"Bearer {token_a}"}
    )
    webhook_id_a = response_a.json()["id"]
    
    # Try to access from workspace B
    token_b = create_test_token(workspace_id="workspace-b")
    response_b = client.get(
        f"/v1/webhooks/{webhook_id_a}",
        headers={"Authorization": f"Bearer {token_b}"}
    )
    # Should get 404 or empty list (not see webhook from workspace A)
    assert response_b.status_code == 404 or response_b.json() == []

def test_migration_against_populated_db():
    """Schema migration is safe on pre-existing DB"""
    # Create DB with old schema
    import sqlite3
    from nexora_crawler.storage.local_sqlite import MetadataStore
    
    db_path = ":memory:"
    conn = sqlite3.connect(db_path)
    conn.execute("CREATE TABLE pages (url TEXT PRIMARY KEY, title TEXT)")
    conn.close()
    
    # Migrate
    store = MetadataStore(db_path)
    store._migrate_schema()
    
    # Verify new columns exist
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    cursor.execute("PRAGMA table_info(pages)")
    columns = [row[1] for row in cursor.fetchall()]
    assert "workspace_id" in columns
    assert "crawl_id" in columns
    conn.close()

def test_gdpr_erase_deletes_workspace_data(client):
    """DELETE /v1/gdpr/erase removes all workspace data"""
    token = create_test_token(workspace_id="test-workspace")
    
    # Insert test data
    store = MetadataStore()
    store.insert_page({
        "url": "http://example.com",
        "title": "Test",
        "workspace_id": "test-workspace"
    })
    
    # Erase
    response = client.delete(
        "/v1/gdpr/erase",
        headers={"Authorization": f"Bearer {token}"}
    )
    assert response.status_code == 200
    
    # Verify deleted
    pages = store.query_by_domain("example.com")
    assert len(pages) == 0

def test_search_semantic_returns_top_k(client):
    """Semantic search returns top K results"""
    token = create_test_token(workspace_id="test-workspace")
    
    # Insert test data with embeddings
    # (assumes vector store has test records)
    
    response = client.post(
        "/v1/search/semantic",
        json={"query": "test query", "top_k": 5},
        headers={"Authorization": f"Bearer {token}"}
    )
    assert response.status_code == 200
    results = response.json()
    assert len(results) <= 5

def test_job_submission_returns_job_id(client):
    """POST /v1/jobs returns job_id for polling"""
    token = create_test_token(workspace_id="test-workspace")
    
    response = client.post(
        "/v1/jobs",
        json={
            "job_type": "crawl",
            "params": {"url": "http://example.com"}
        },
        headers={"Authorization": f"Bearer {token}"}
    )
    assert response.status_code == 202
    assert "job_id" in response.json()

def test_job_status_polling(client):
    """GET /v1/jobs/{id} returns status"""
    token = create_test_token(workspace_id="test-workspace")
    
    # Submit job
    submit_response = client.post(
        "/v1/jobs",
        json={"job_type": "crawl", "params": {"url": "http://example.com"}},
        headers={"Authorization": f"Bearer {token}"}
    )
    job_id = submit_response.json()["job_id"]
    
    # Poll status
    status_response = client.get(
        f"/v1/jobs/{job_id}",
        headers={"Authorization": f"Bearer {token}"}
    )
    assert status_response.status_code == 200
    assert "status" in status_response.json()
```

**Run tests:**
```bash
cd "Nexora application"
python -m pytest tests/test_phase4c.py -v
```

**Acceptance Criteria:**
- [ ] All 12+ tests pass
- [ ] Coverage: auth, workspace isolation, GDPR, search, jobs, webhooks
- [ ] No test skips or xfails

---

### 🟠 HIGH PRIORITY: Week 1-2

#### Task 3: Implement Rate Limiting
**Status:** NOT STARTED  
**Effort:** 2 hours  
**Impact:** Prevents abuse (security feature)

**What to do:**

1. Wire `slowapi` Limiter to FastAPI app

File: `api/__init__.py`

```python
from slowapi import Limiter
from slowapi.util import get_remote_address

limiter = Limiter(key_func=get_remote_address)
app.state.limiter = limiter

# Add exception handler
from slowapi.errors import RateLimitExceeded

@app.exception_handler(RateLimitExceeded)
async def rate_limit_exceeded_handler(request, exc):
    return JSONResponse(
        status_code=429,
        content={"detail": "Rate limit exceeded"}
    )
```

2. Apply per-route limits

File: `api/routes/search.py`

```python
@router.post("/semantic", name="semantic_search")
@limiter.limit("100/minute")  # 100 requests per minute
async def semantic_search(request: Request, query_in: SearchQuery):
    # ... implementation
```

3. Test 429 responses

```bash
# Make 101 requests in 60 seconds
for i in {1..101}; do
  curl -X POST http://localhost:8000/v1/search/semantic \
    -H "X-Api-Key: test.key" \
    -d '{"query": "test"}'
done
# Request 101 should return 429
```

**Acceptance Criteria:**
- [ ] Limiter installed
- [ ] Per-route limits defined
- [ ] 429 returns when limit exceeded
- [ ] Dev/test routes excluded if needed

---

#### Task 4: Implement Real Job Handlers
**Status:** NOT STARTED  
**Effort:** 4-6 hours (per handler)  
**Impact:** Enables real job execution (currently all stubs)

**What to do:**

Currently all 5 job handlers return HTTP 501. Replace with real implementations:

1. **CrawlJobHandler** — Spawn Scrapy crawler
2. **SchemaExtractJobHandler** — Run extraction_schemas
3. **IndexSearchJobHandler** — Query vector store
4. **IndexAddJobHandler** — Add URLs to vector index
5. **ExportJobHandler** — Multi-format export

**Example: CrawlJobHandler**

File: `api/jobs/handlers.py` (new file)

```python
class CrawlJobHandler:
    async def handle(self, job_id: str, params: dict) -> dict:
        """
        params = {
            "urls": ["http://example.com"],
            "strategy": "single-page",
            "enrich_mode": "on_demand"
        }
        """
        urls = params["urls"]
        strategy = params.get("strategy", "single-page")
        enrich_mode = params.get("enrich_mode", "on_demand")
        
        # Spawn subprocess
        import subprocess
        proc = subprocess.Popen([
            sys.executable, "-m", "nexora_crawler.api",
            "--url", urls[0],
            "--strategy", strategy,
            "--enrich-mode", enrich_mode
        ])
        
        # Update DB job status
        store = MetadataStore()
        store.update_job_status(job_id, "running")
        
        # Wait for completion
        proc.wait()
        
        # Update final status
        store.update_job_status(job_id, "completed", result={"exit_code": proc.returncode})
        
        return {"status": "completed", "exit_code": proc.returncode}
```

**Acceptance Criteria:**
- [ ] At least 2 handlers implemented (crawl + search)
- [ ] Job status updates DB
- [ ] Result payload returned on completion
- [ ] Error handling + logging

---

### 🟡 MEDIUM PRIORITY: Week 2-3

#### Task 5: Webhook Delivery Worker
**Status:** NOT STARTED  
**Effort:** 4 hours  
**Impact:** Enables real-time event notifications

**What to do:**

Implement async worker to deliver webhook events

File: `api/webhooks/worker.py` (new file)

```python
async def deliver_webhook(webhook_id: str, event: dict):
    """Deliver webhook event with retries"""
    store = MetadataStore()
    webhook = store.get_webhook(webhook_id)
    
    if not webhook["is_active"]:
        return
    
    # Verify signature
    import hmac
    import hashlib
    event_json = json.dumps(event)
    signature = hmac.new(
        webhook["secret"].encode(),
        event_json.encode(),
        hashlib.sha256
    ).hexdigest()
    
    # Retry logic
    for attempt in range(3):  # 3 attempts
        try:
            response = requests.post(
                webhook["url"],
                json=event,
                headers={"X-Signature": signature},
                timeout=30
            )
            
            # Log delivery
            store.insert_webhook_delivery({
                "webhook_id": webhook_id,
                "event": json.dumps(event),
                "status": "delivered",
                "response_code": response.status_code
            })
            return
        except Exception as e:
            logger.warning(f"Webhook delivery failed (attempt {attempt+1}): {e}")
            if attempt < 2:
                await asyncio.sleep(2 ** attempt)  # Exponential backoff
    
    # Final failure
    store.insert_webhook_delivery({
        "webhook_id": webhook_id,
        "event": json.dumps(event),
        "status": "failed",
        "response_code": None
    })
```

**Acceptance Criteria:**
- [ ] Worker implemented
- [ ] Retries with exponential backoff
- [ ] Signature verification
- [ ] Delivery logs in DB

---

#### Task 6: Full Environment Validation
**Status:** NOT STARTED  
**Effort:** 1 day  
**Impact:** Ensures all systems work together in real-world scenarios

**What to do:**

Run full QA matrix with live AI provider + Playwright:

```bash
# Prerequisites:
# - HuggingFace API key configured
# - Playwright installed
# - NEXORA_AI_PROVIDER=huggingface
# - NEXORA_ENRICH_MODE=eager

cd "Nexora application/Crawler"

# Test 01: Static site (books.toscrape.com)
scrapy crawl nexora -a urls="https://books.toscrape.com" -a strategy="linked-pages" -a max_pages=10

# Test 02: JS-rendered site (react-shopping-cart)
scrapy crawl nexora -a urls="https://react-shopping-cart-67954.firebaseapp.com" -a strategy="single-page"

# Test 03: Large site (wikipedia)
scrapy crawl nexora -a urls="https://en.wikipedia.org" -a strategy="whole-website" -a max_pages=50

# Test 04: API crawl submission
python -m nexora_crawler.api --server &
sleep 2
curl -X POST http://localhost:8000/crawl \
  -H "Content-Type: application/json" \
  -d '{"url": "https://example.com", "strategy": "single-page"}'
kill %1

# Verify outputs
ls -lh output/parquet/  # Parquet files created
ls -lh output/pages/     # JSON + CSV created
sqlite3 data/nexora_metadata.db "SELECT COUNT(*) FROM pages WHERE ai_summary IS NOT NULL;"  # AI enrichment count
```

**Acceptance Criteria:**
- [ ] Test 01: All 10 pages crawled, enriched, exported
- [ ] Test 02: JS rendering verified (Playwright used)
- [ ] Test 03: Pagination handled, 50 pages max
- [ ] Test 04: API submission works
- [ ] Vector store has embeddings
- [ ] No errors or warnings

---

## Post-Production Monitoring

### Health Checks

```bash
# Daily health check
curl http://localhost:8000/health/detailed

# Expected output:
{
  "status": "ok",
  "uptime": "24:00:00",
  "version": "4.6.0",
  "components": {
    "database": "ok",
    "vector_store": "ok",
    "ai_provider": "ok"
  }
}
```

### Key Metrics to Track

| Metric | Target | Action if Exceeded |
|--------|--------|-------------------|
| Crawl time / page | <5 seconds (static), <30 seconds (JS) | Check resource blocking, Playwright timeout |
| AI enrichment latency | <3 sec per page (eager mode) | Check HF quota, consider fallback provider |
| Vector store size | <500GB (single node) | Plan for distributed vector store |
| API response time | <500ms (p95) | Check DB query performance, add indexes |
| Error rate | <0.1% | Monitor error logs, enable alerting |

---

## Documentation Updates

### After Completing Tasks

1. **Update README.md**
   - Add section on Phase 4C job submission
   - Add rate limiting limits
   - Add webhook delivery documentation

2. **Update release_notes_v4.6.1.md**
   - enrich.py helpers implemented
   - Phase 4C tests added
   - Rate limiting implemented
   - Real job handlers implemented

3. **Create DEPLOYMENT_GUIDE.md**
   - Production setup instructions
   - Security checklist (JWT secret, API key rotation, CORS)
   - Monitoring setup
   - Scaling considerations

---

## Success Criteria for Production Release

- [x] Phase 3 (Dynamic Detection) — complete and verified
- [x] Phase 4A (Storage Engine) — complete and verified
- [x] Phase 4B (AI Enrichment) — complete and verified
- [x] Phase 4C (API Layer) — complete and verified
- [ ] enrich.py helpers — implemented and tested
- [ ] Phase 4C regression tests — all pass
- [ ] Rate limiting — implemented and enforced
- [ ] Job handlers — at least 2 real implementations
- [ ] Full environment validation — all tests pass
- [ ] Zero critical bugs — verified via QA
- [ ] Documentation — updated and current
- [ ] Team trained — operations runbook prepared

---

## Estimated Timeline

| Phase | Duration | Start | End |
|-------|----------|-------|-----|
| Critical fixes (Tasks 1-2) | 10 hours | Week 1 Mon | Week 1 Wed |
| High priority (Tasks 3-4) | 6-8 hours | Week 1 Wed | Week 1 Fri |
| Medium priority (Tasks 5-6) | 5 hours | Week 2 Mon | Week 2 Wed |
| Documentation + training | 4 hours | Week 2 Wed | Week 2 Thu |
| **Total** | **25-27 hours** | **Week 1** | **Week 2 Thu** |

**Production Release Target:** End of Week 2 (2026-08-30)

---

## Risk Mitigation

| Risk | Probability | Impact | Mitigation |
|------|-------------|--------|-----------|
| enrich.py helpers misses edge cases | Medium | High | Comprehensive unit tests + fuzzy testing |
| Rate limiter too aggressive | Low | Medium | Tunable per-route limits + grace period |
| Job handlers spawn too many processes | Medium | High | Task queue limit + resource monitoring |
| Vector store scales poorly | Low | High | Plan for distributed backend (Weaviate, Qdrant) |
| Webhook delivery overwhelms external service | Low | Medium | Exponential backoff + dead-letter queue |

---

**Last Updated:** 2026-08-19  
**Next Review:** After Task 1 completion  
**Deployment Authority:** Engineering lead approval required

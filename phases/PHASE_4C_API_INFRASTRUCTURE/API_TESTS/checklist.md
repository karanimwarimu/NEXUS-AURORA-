TEST MATRIX
Test ID	Scenario	Expected Result
P4C-T01	API health check	GET /health returns 200 with status, version
P4C-T02	JWT login	POST /auth/token returns access + refresh tokens
P4C-T03	JWT validation	Protected endpoint rejects invalid token with 401
P4C-T04	Token refresh	POST /auth/refresh returns new access token
P4C-T05	API key creation	POST /auth/api-keys returns new API key
P4C-T06	Rate limiting	>60 req/min returns 429
P4C-T07	Crawl submission	POST /crawl/start returns 202 with job_id
P4C-T08	Job status polling	GET /crawl/status/{id} returns progress
P4C-T09	Job cancellation	POST /crawl/cancel/{id} stops job
P4C-T10	Batch crawl	POST /crawl/batch returns multiple job_ids
P4C-T11	CLI direct mode	nexora https://example.com runs crawl
P4C-T12	CLI API mode	nexora --api ... crawl ... submits via API
P4C-T13	SDK crawl	client.crawl(url) returns CrawlResult
P4C-T14	SDK wait	client.wait_for_completion(id) polls until done
P4C-T15	OpenAPI docs	/docs and /redoc render correctly
P4C-T16	Non-blocking	API returns immediately, crawl runs in background
P4C-T17	No regression	Phase 3 + 4A + 4B tests still pass
7. DEFINITION OF DONE
[ ] FastAPI server starts and responds to /health
[ ] JWT authentication works (login, refresh, validation)
[ ] Rate limiting enforced per endpoint
[ ] Crawl jobs submitted via POST /crawl/start return 202 with job_id
[ ] Job status polling works via GET /crawl/status/{job_id}
[ ] Background tasks execute crawls without blocking API
[ ] CLI works in direct mode (no API needed)
[ ] CLI works in API mode
[ ] Python SDK installs and works with API
[ ] OpenAPI docs render at /docs and /redoc
[ ] All 17 test cases pass
[ ] Phase 3 + 4A + 4B tests show no regression


Execution Plan & Implementation Order
[Phase 1: Skeleton]   --->   [Phase 2: Database]   --->   [Phase 3: Security]
Package restructuring        Schema migration &           Auth middleware & JWT
and route definitions        unified connection pool      isolation routines

                                                                |
                                                                v

[Phase 6: CLI & SDK]   <---   [Phase 5: Job Engine] <---   [Phase 4: Routes]
Python client updates         Subprocess workers &         Search, GDPR, Webhooks,
and validation suites         task dispatcher              and Extraction


Phase 1: Package Restructuring & Core Skeleton
Migrate nexora_crawler/api.py functions to nexora_crawler/api/__init__.py.
Construct nexora_crawler/api/__main__.py routing flags directly to internal execution routines.
Validate backwards-compatibility with existing runs:
python -m nexora_crawler.api --help
uvicorn nexora_crawler.api:app --reload


Phase 2: Consolidated Persistence Layer
Extend nexora_crawler/storage/local_sqlite.py to auto-apply missing columns (workspace_id) on boot.
Initialize the 6 new Phase 4C tables during startup hooks.
Ensure nexora_crawler/api/database/connection.py references settings.NEXORA_METADATA_DB.
Phase 3: Security & Isolation Layer
Implement nexora_crawler/api/auth.py supporting JWT parsing, signature validation, and dev-bypass headers (X-Workspace-Id).
Attach workspace identity injectables (Depends(get_workspace_id)) to non-legacy routes.
Phase 4: Route Handlers Implementation
Construct api/routes/search.py bridging BaseVectorStore.hybrid_search() to the API.
Construct api/routes/gdpr.py enforcing cascade deletion across pages, metadata stores, and vector indices by workspace_id.
Build extract.py, webhooks.py, and health.py.
Phase 5: Task Management Infrastructure
Implement nexora_crawler/jobs/registry.py and nexora_crawler/tasks/dispatcher.py.
Configure api/tasks/crawl_task.py using asyncio.create_subprocess_exec to execute jobs cleanly without conflicting with active Twisted reactors.
Phase 6: SDK & Verification
Create nexora_crawler/sdk/client.py using httpx.
Execute target integration test suite to verify route stability and data persistence:
pytest tests/ -k "phase_4c"

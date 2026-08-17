# PHASE 4C — IMPLEMENTATION VERIFICATION PROTOCOL
# For: Verification Agent (Opus)
# Target codebase: Nexora Crawler (Scrapy 2.16, FastAPI, Windows Anaconda env)
# Version: 1.0.0

---

## 0. YOUR MISSION

You are verifying that the **Phase 4C implementation** (API layer, task dispatch,
auth, webhooks, GDPR, schema extraction, CLI, SDK) was **actually and correctly
integrated** into the existing Nexora codebase — not just that files exist, but
that the integration decisions, rework items, and breaking-change mitigations
specified during analysis were honored, and that the code actually runs.

You must verify against **three sources of truth**, in this order:

1. **This checklist** — distilled requirements below.
2. **The codebase itself** — the code is the final truth; if code and docs
   disagree, the code wins and you report the divergence.
3. **Your own judgment** — Section 8 requires you to hunt for problems the
   original analysis missed. Do not limit yourself to this checklist.

### Orientation files (READ THESE FIRST)

Use these files to navigate and understand the codebase before checking anything:

- `@repository structure.md` — full file/folder map of the repo
- `nexora handoff.md` — project state, prior phases, conventions, known issues
- `README` (repo root) — setup, run commands, feature overview

If any of these files contradict what you find in the code, note it as a
documentation-drift finding.

### Output required

Produce a verification report with, for every check item:

- **PASS** — implemented as specified, evidence cited (file + line/symbol)
- **PARTIAL** — exists but deviates (describe deviation, assess severity)
- **FAIL** — missing or broken
- **N/A** — intentionally not implemented, with confirmation the omission is safe

End with: a **Verdict** (READY / READY WITH FIXES / NOT READY), a prioritized
list of findings (P0 = blocks runtime, P1 = blocks correctness, P2 = cosmetic/
deferrable), and the full test-run results from Section 9.

---

## 1. PACKAGE STRUCTURE (REWORK 1 — verify migration held)

The pre-4C codebase had a standalone module `nexora_crawler/api.py`. Phase 4C
requires a package. **These two can never coexist** — verify the migration is
real and complete.

- [ ] **1.1** `nexora_crawler/api.py` (the old standalone module) **no longer exists**.
- [ ] **1.2** `nexora_crawler/api/__init__.py` exists and contains the migrated
      FastAPI `app` object plus the original v4.5.0 endpoints (`/crawl`,
      `/crawl/{job_id}`, `/jobs`, strategy maps, `_run_crawl`, CLI functions).
- [ ] **1.3** `nexora_crawler/api/__main__.py` exists so that
      `python -m nexora_crawler.api` still works.
- [ ] **1.4** `nexora_crawler/api/routes/__init__.py` exists (exports or marks
      the routes package).
- [ ] **1.5** Import integrity: `from nexora_crawler.api import app` works;
      `uvicorn nexora_crawler.api:app` resolves.
- [ ] **1.6** Grep the whole `nexora_crawler/` package: **no module imports
      from the old `api.py` path** in a way that would break, and no stale
      references to a file that was deleted.
- [ ] **1.7** CLI modes still work:
      `python -m nexora_crawler.api --help`,
      `python -m nexora_crawler.api --server`,
      `python -m nexora_crawler.api --url <url>`.

**FAIL condition:** both `api.py` and `api/` exist, or `python -m nexora_crawler.api`
raises, or `app` is not importable from `nexora_crawler.api`.

---

## 2. REQUIRED NEW FILES — EXISTENCE + WIRING

Verify each file exists **and is actually imported/registered** (a file that
exists but is never wired into the app is a FAIL).

### From the integration patch (core 4C layer):

| # | File | Purpose |
|---|------|---------|
| 2.1 | `nexora_crawler/api/auth.py` | JWT validation, `get_workspace_id`, `create_access_token`, `require_admin`, `X-Workspace-Id` dev bypass. **Must be at package root, NOT in routes/** (patch supersedes original spec on this) |
| 2.2 | `nexora_crawler/api/database/connection.py` | Async DB via `aiosqlite` / `asyncpg`, `get_db()` singleton, `close_db()` |
| 2.3 | `nexora_crawler/api/routes/search.py` | `POST /v1/search/semantic`, `POST /v1/search/hybrid`, `POST /v1/search/by-source/{source_type}/{source_id}/similar` |
| 2.4 | `nexora_crawler/api/routes/webhooks.py` | `POST/GET/DELETE /v1/webhooks` CRUD |
| 2.5 | `nexora_crawler/api/routes/jobs.py` | `POST /v1/jobs` (202, generic dispatch), `GET /v1/jobs/types` |
| 2.6 | `nexora_crawler/api/routes/gdpr.py` | `DELETE /v1/gdpr/erase` with audit-log write |
| 2.7 | `nexora_crawler/api/routes/extract.py` | `POST /v1/extract/schema` (202, persists schema) |

### From the original spec:

| # | File | Purpose |
|---|------|---------|
| 2.8 | `nexora_crawler/api/routes/health.py` | `GET /health`, `GET /health/detailed` |
| 2.9 | `nexora_crawler/api/routes/crawl.py` | `/crawl/start` (202 + job_id), `/crawl/batch`, `/crawl/status/{id}`, `/crawl/cancel/{id}`, `/crawl/list` |
| 2.10 | `nexora_crawler/api/routes/results.py` | Results retrieval |
| 2.11 | `nexora_crawler/api/routes/admin.py` | Admin endpoints |
| 2.12 | `nexora_crawler/api/tasks/crawl_task.py` | Background crawl worker with injectable job store (`set_jobs_store`) |
| 2.13 | `nexora_crawler/api/middleware/logging.py` | `LoggingMiddleware` structured request logging |
| 2.14 | `nexora_crawler/cli/main.py` | CLI with direct mode + API mode (`crawl`, `status`, `list-jobs` subcommands) |
| 2.15 | `nexora_crawler/sdk/client.py` | `NexoraClient` with `crawl`, `batch_crawl`, `get_job_status`, `cancel_job`, `list_jobs`, `wait_for_completion`, `health_check` |

### Wiring checks:

- [ ] **2.16** All routers are `include_router`ed into the FastAPI app — the
      `/v1/*` routers (search, webhooks, jobs, gdpr, extract) and the crawl/
      health/auth routers. Confirm by inspecting the app **and** by hitting
      `/openapi.json` and confirming the paths appear.
- [ ] **2.17** `LoggingMiddleware` and CORS middleware are added to the app.
- [ ] **2.18** App exposes `/docs`, `/redoc`, `/openapi.json`.

**Doc contradiction note:** the original spec placed auth at
`api/routes/auth.py`; the patch (which supersedes it) places it at
`api/auth.py`. PASS = patch layout. If both exist, check for drift between them.

---

## 3. DATABASE LAYER — THE CRITICAL CHECKS

This is where the implementation was most likely to silently diverge.

### 3A. Single-database unification (REWORK 3 / BREAK 3)

- [ ] **3.1** There is exactly **one** SQLite database file in play. The old
      pipelines write to `./data/nexora_metadata.db`; the patch's default was
      `./data/nexora.db`. Verify `api/database/connection.py` resolves to the
      **same file** the rest of the system uses (ideally sourced from
      `NEXORA_METADATA_DB` in settings), or that a documented migration merged
      them. Two live DB files = **FAIL (P0)**.
- [ ] **3.2** Data written by a crawl triggered through the new API is visible
      to existing readers (`enrich.py`, `MetadataIndexerPipeline`) and vice
      versa. Trace the actual file paths in code — do not trust defaults.

### 3B. Schema — new tables (must exist in the schema init)

- [ ] **3.3** `webhooks` (workspace_id, url, event_types JSON, secret, is_active, created_at)
- [ ] **3.4** `webhook_deliveries` (webhook_id FK, job_id, event_type, status_code, attempt, delivered_at, error)
- [ ] **3.5** `workspace_quotas` (workspace_id PK, pages_per_month, storage_gb, vector_records, api_rpm, schema_extracts_per_day)
- [ ] **3.6** `usage_records` (workspace_id, period YYYY-MM, pages_crawled, storage_bytes, vector_records, api_calls, UNIQUE(workspace_id, period))
- [ ] **3.7** `audit_logs` (workspace_id, actor, action, target_id, details JSON, ip_address, timestamp)
- [ ] **3.8** `extraction_schemas` (job_id PK, workspace_id, schema_json, created_at)
- [ ] **3.9** Spec-side tables if implemented: `workspaces`, `users`, `api_keys`
      (needed by `/auth/api-keys`).

Verify by opening the actual DB file (or schema-init code) — not by reading
the route SQL.

### 3C. workspace_id on existing tables (REWORK 4 / BREAK 4)

- [ ] **3.10** `pages` table has a `workspace_id` column
      (`TEXT DEFAULT 'default'`), added via `ALTER TABLE` or schema update.
- [ ] **3.11** `crawl_jobs` table has a `workspace_id` column, same treatment.
- [ ] **3.12** Pre-existing rows were backfilled to `'default'`.
- [ ] **3.13** `MetadataStore.insert_page()` (or equivalent) accepts and
      persists `workspace_id`.
- [ ] **3.14** Confirm no migration framework is *required* for this to work
      (analysis found none existed — acceptable if the ALTER/backfill is done
      manually/idempotently in schema init).

### 3D. workspace_id population pipeline (REWORK 9)

Everything historically defaulted to `"default"`. Verify the chain is real:

- [ ] **3.15** `nexora_spider.py` accepts a `workspace_id` parameter and sets
      it as a spider attribute.
- [ ] **3.16** `schema_enricher.py` populates `workspace_id` from the spider
      (fallback to `'default'` only when genuinely unset).
- [ ] **3.17** `vector_index_pipeline.py` reads `crawler.workspace_id` — and
      the spider now actually provides it (previously it never did).
- [ ] **3.18** API crawl endpoints generate or accept a `workspace_id` and pass
      it through to the spider.

---

## 4. RUNTIME SAFETY — THE HARD BLOCKERS

### 4A. Reactor isolation (BREAK 2 / REWORK 2) — **highest-severity runtime risk**

The original spec's `crawl_task.py` runs `CrawlerProcess` inside
`loop.run_in_executor`. Twisted's reactor can only start once per process —
under uvicorn this crashes or hangs on the **second** crawl.

- [ ] **4.1** Background crawls are executed via **subprocess**
      (`asyncio.create_subprocess_exec` spawning `python -m nexora_crawler.api
      --url ...`), preserving the v4.5.0 `_run_crawl` model — **NOT**
      `CrawlerProcess` in a thread executor inside the API process.
- [ ] **4.2** If an in-process approach was used anyway, verify (by running, not
      reading) that **two consecutive crawls** through the API both complete.
      Failure on crawl #2 = **FAIL (P0)**.

### 4B. Auth backward compatibility (BREAK 5 / REWORK 5)

- [ ] **4.3** Existing unauthenticated endpoints (`/crawl`, `/crawl/{job_id}`,
      `/jobs`) still work **without** a JWT — no global auth middleware.
- [ ] **4.4** Auth is applied **per-router/per-endpoint** via
      `Depends(get_workspace_id)`, only on the new `/v1/*` surface.
- [ ] **4.5** `X-Workspace-Id` header dev bypass works for local testing, and
      returns 401 without it when no token is supplied (on protected routes).
- [ ] **4.6** Invalid/expired JWT → 401 with a clear detail message.

### 4C. Job dispatch (BREAK 6, BREAK 7 / REWORK 6, REWORK 7)

- [ ] **4.7** `nexora_crawler/jobs/registry.py` exists with `JobTypeRegistry`
      (register/get/list) — `jobs.py` imports it at startup; missing module =
      server won't boot.
- [ ] **4.8** `nexora_crawler/tasks/dispatcher.py` exists and works. If the
      implementation chose the documented simplification (in-process dispatch /
      FastAPI `BackgroundTasks` instead of Celery), confirm the choice is real
      and consistent everywhere — **no leftover `dispatcher_task.delay(...)`
      Celery calls pointing at a nonexistent Celery app** in `jobs.py` or
      `extract.py`. That mismatch = import/runtime failure = **FAIL (P0)**.
- [ ] **4.9** If Celery *was* installed: a broker (Redis/RabbitMQ) is
      configured and a worker startup path exists. Celery with no broker =
      **FAIL**.
- [ ] **4.10** Registered built-in job types exist: `crawl`, `schema_extract`,
      `index_search`, `index_add`, `export` (or a documented reduced set).
- [ ] **4.11** `POST /v1/jobs` with `async_run=false` runs lightweight jobs
      inline and returns the result.

### 4D. Non-blocking guarantee (core 4C principle)

- [ ] **4.12** Crawl submission returns immediately (`202` / job_id) — the API
      never blocks on crawl execution. Verify with a live request, timing it.

---

## 5. SETTINGS & DEPENDENCIES

### 5A. Settings (REWORK — settings collision)

- [ ] **5.1** These settings exist in `settings.py` (or equivalent config):
      `NEXORA_API_HOST`, `NEXORA_API_PORT`, `NEXORA_API_WORKERS`,
      `NEXORA_JWT_SECRET_KEY`, `NEXORA_JWT_ALGORITHM`,
      `NEXORA_JWT_ACCESS_TOKEN_EXPIRE_MINUTES`,
      `NEXORA_JWT_REFRESH_TOKEN_EXPIRE_DAYS`, `NEXORA_API_KEY_LENGTH`,
      `NEXORA_RATE_LIMIT_DEFAULT`, `NEXORA_RATE_LIMIT_BURST`,
      `NEXORA_CORS_ORIGINS`, `NEXORA_LOG_FORMAT`, `NEXORA_LOG_LEVEL`,
      `NEXORA_STRUCTURED_LOGS`.
- [ ] **5.2** No collision with the pre-existing `LOG_LEVEL = "INFO"` — both
      coexist coherently or were reconciled.
- [ ] **5.3** `NEXORA_DATABASE_URL` usage is consistent — it must not silently
      point the API at a different DB than the pipelines (see 3.1).
- [ ] **5.4** JWT secret is not hardcoded to `change-me-in-production` without
      an env override path, and env-var naming is consistent between `auth.py`
      and settings (patch used bare `JWT_SECRET_KEY`; spec used
      `NEXORA_JWT_SECRET_KEY` — confirm whichever was chosen is used
      **consistently**).

### 5B. Dependencies

- [ ] **5.5** Present in requirements/installed: `fastapi`, `uvicorn[standard]`,
      `pydantic v2`, `PyJWT`, `bcrypt`, `python-multipart`, `slowapi`,
      `httpx`, `aiosqlite` (and/or `asyncpg`), `python-dotenv`.
- [ ] **5.6** Rate limiting: `slowapi` limiter wired to app state +
      `RateLimitExceeded` handler. If in-memory mode is used, that limitation
      (process-local) is acknowledged in docs/comments.
- [ ] **5.7** API-key hashing exists (bcrypt or documented sha256 choice) and
      plaintext keys are never stored.

---

## 6. ENDPOINT BEHAVIOR — FUNCTIONAL CHECKS

For each, verify by **running against a live server** (preferred) or by
FastAPI `TestClient` where live crawling is impractical.

- [ ] **6.1** `GET /health` → 200, `{status, service, version, timestamp}`.
- [ ] **6.2** `GET /health/detailed` → uptime + system info.
- [ ] **6.3** `POST /auth/token` → access + refresh tokens (demo creds
      admin/admin123 if kept, or whatever was implemented — flag demo creds as
      a P2 security note).
- [ ] **6.4** `POST /auth/refresh` → new access token from a refresh token.
- [ ] **6.5** `POST /auth/api-keys` (authed) → returns a new API key **once**.
- [ ] **6.6** Rate limit: exceeding `NEXORA_RATE_LIMIT_DEFAULT` → 429.
- [ ] **6.7** `POST /crawl/start` → 202 + `job_id`; job actually executes in
      background.
- [ ] **6.8** `GET /crawl/status/{job_id}` → status/progress; 404 for unknown.
- [ ] **6.9** `POST /crawl/cancel/{job_id}` → cancelled state.
- [ ] **6.10** `POST /crawl/batch` → one job_id per URL.
- [ ] **6.11** `GET /crawl/list` → filtered by workspace; other workspaces'
      jobs invisible.
- [ ] **6.12** `POST /v1/search/semantic` → SearchResponse with backend +
      took_ms; results scoped to workspace.
- [ ] **6.13** `POST /v1/search/hybrid` → vector + BM25 path works
      (`hybrid_search` on the store, `bm25_weight` honored).
- [ ] **6.14** `POST /v1/search/by-source/{t}/{id}/similar` → 404 on unknown
      source, **403 on cross-workspace source**, seed record excluded from
      results.
- [ ] **6.15** Webhooks: create (201, secret shown once), list, delete (204);
      all scoped to workspace.
- [ ] **6.16** `DELETE /v1/gdpr/erase` → deletes pages + crawl_jobs rows for
      the workspace **in the real DB**, calls `delete_by_workspace` on the
      vector store, writes an `audit_logs` row, returns counts + scheduled
      hard-delete date. **Confirm it deletes from the same DB the pipelines
      write to** (ties back to 3.1).
- [ ] **6.17** `POST /v1/extract/schema` → 202, schema persisted to
      `extraction_schemas`, job dispatched.
- [ ] **6.18** Vector store compatibility intact: `BaseVectorStore`
      `delete_by_workspace()` and `hybrid_search()` still abstract and still
      implemented by both `ChromaVectorStore` and `PgVectorStore` (this was
      compatible pre-4C — confirm nobody broke it).
- [ ] **6.19** Response-format divergence is as designed: existing `/crawl`
      returns the rich v4.5.0 `CrawlResponse` (pages_crawled, output_dir, mode,
      enrich_mode); `/v1/jobs` returns the simpler 4C models. Both documented.

---

## 7. CLI & SDK

- [ ] **7.1** CLI direct mode runs a crawl without the API server.
- [ ] **7.2** CLI API mode (`--api`) can submit `crawl`, poll `status`, and
      `list-jobs` against a running server.
- [ ] **7.3** `NexoraClient` can: submit crawl, poll via
      `wait_for_completion` (with timeout raising `TimeoutError`), cancel,
      list, health-check. Confirm the SDK's endpoint paths match the server's
      actual routes (the spec SDK calls `/crawl/...` — if routes moved under
      `/v1`, the SDK must have been updated too; a mismatch here is a classic
      silent break — check it).

---

## 8. YOUR OWN AUDIT — FIND WHAT THE ANALYSIS MISSED

The pre-implementation analysis (breakages, rework items) is incorporated
above. Now go beyond it. At minimum, actively hunt for:

1. **Import-time failures** — import every new module in isolation; circular
   imports between `api/__init__.py`, `api/auth.py`, routes, and tasks are the
   prime suspect.
2. **Async correctness** — blocking calls inside async handlers, sync DB
   drivers mixed with `aiosqlite`, missing `await`s, event-loop misuse in
   background tasks.
3. **SQLite concurrency** — the singleton aiosqlite connection shared across
   concurrent requests + background tasks: check for lock errors, missing
   commits, uncommitted writes that tests wouldn't catch.
4. **Tenant isolation gaps** — any endpoint that reads/writes by id without a
   `workspace_id` predicate (the spec's `cancel_job`/`get_job_status` used a
   shared in-memory dict — check workspace scoping was actually enforced).
5. **In-memory state volatility** — `_jobs` dict lost on restart: acceptable
   per REWORK 7, but confirm it's documented and job status survives at least
   as well as documented.
6. **Secrets handling** — webhook secrets, API keys, JWT secret: returned
   once, hashed at rest, never logged.
7. **SQL injection / parameterization** — especially the dual aiosqlite (`?`)
   vs asyncpg (`$1`) paths; confirm no string-interpolated SQL.
8. **Settings/env consistency** — names used in code vs names documented vs
   names in settings.py (see 5.4).
9. **Dead code / contradiction residue** — two auth implementations, an
   unused Celery import, a route registered twice, both `api.py` and
   `api/` remnants.
10. **Windows compatibility** — the project runs on Windows Anaconda: check
    subprocess calls, path handling, and uvicorn worker flags for
    Windows-safe behavior.

Add every finding to the report with a severity (P0/P1/P2) — including
findings not covered by any checklist item above.

---

## 9. POST-VERIFICATION TEST EXECUTION — MANDATORY

**Only after** Sections 1–8 are complete, execute the test set from the main
implementation specification (Phase 4C §6 Test Matrix) plus the regression
suite. Report each test as PASS / FAIL / SKIP (with reason) and include
actual command output for failures.

### 9.1 Phase 4C Test Matrix (from the spec)

| Test ID | Scenario | Expected Result |
|---------|----------|-----------------|
| P4C-T01 | API health check | `GET /health` returns 200 with status, version |
| P4C-T02 | JWT login | `POST /auth/token` returns access + refresh tokens |
| P4C-T03 | JWT validation | Protected endpoint rejects invalid token with 401 |
| P4C-T04 | Token refresh | `POST /auth/refresh` returns new access token |
| P4C-T05 | API key creation | `POST /auth/api-keys` returns new API key |
| P4C-T06 | Rate limiting | >60 req/min returns 429 |
| P4C-T07 | Crawl submission | `POST /crawl/start` returns 202 with job_id |
| P4C-T08 | Job status polling | `GET /crawl/status/{id}` returns progress |
| P4C-T09 | Job cancellation | `POST /crawl/cancel/{id}` stops job |
| P4C-T10 | Batch crawl | `POST /crawl/batch` returns multiple job_ids |
| P4C-T11 | CLI direct mode | `nexora https://example.com` runs crawl |
| P4C-T12 | CLI API mode | `nexora --api ... crawl ...` submits via API |
| P4C-T13 | SDK crawl | `client.crawl(url)` returns CrawlResult |
| P4C-T14 | SDK wait | `client.wait_for_completion(id)` polls until done |
| P4C-T15 | OpenAPI docs | `/docs` and `/redoc` render correctly |
| P4C-T16 | Non-blocking | API returns immediately, crawl runs in background |
| P4C-T17 | **No regression** | Phase 3 + 4A + 4B tests still pass |

Execution guidance:

- Use a local test server or FastAPI `TestClient`; use a stable, simple
  target URL (e.g. example.com or a local fixture page) for crawl tests.
- For T06, fire requests in a burst rather than waiting a full minute.
- For T16, time the submission response — it must return in well under the
  crawl's total duration.
- Where a test cannot run in your environment (e.g. no network), mark SKIP
  with the exact reason — never mark PASS without execution evidence.

### 9.2 Regression suite (P4C-T17 expanded)

- [ ] Run the **full pre-existing v4.5.0 test suite** (Phase 3 + 4A + 4B
      tests). Zero new failures permitted.
- [ ] Specifically re-verify the REWORK 1 acceptance checks:
      `from nexora_crawler.api import app`,
      `python -m nexora_crawler.api --help`,
      `uvicorn nexora_crawler.api:app` resolution.
- [ ] Confirm a crawl executed **outside** the API (direct Scrapy path) still
      works end-to-end: spider → pipelines → `nexora_metadata.db` → vector
      store.

---

## 10. REPORT FORMAT

```
# Phase 4C Verification Report
Date: <date> | Verifier: Opus | Codebase: <commit/version if available>

## Verdict: READY | READY WITH FIXES | NOT READY

## Summary
<3-6 sentences: what state the implementation is in>

## Checklist Results
<Section-by-section PASS/PARTIAL/FAIL/N/A with evidence: file, line, symbol>

## Findings (prioritized)
| # | Severity | Area | Finding | Evidence | Recommended fix |
|---|----------|------|---------|----------|-----------------|

## Self-Audit Findings (Section 8)
<problems found beyond the checklist>

## Test Execution Results
| Test ID | Result | Evidence/Output |
<including full regression suite summary>

## Sign-off Criteria (from spec §7 Definition of Done)
<each DoD item checked off or flagged>
```

**Definition of Done to confirm against (spec §7):** server starts and answers
`/health`; JWT login/refresh/validation work; rate limiting enforced; crawl
submission returns 202 + job_id; status polling works; background crawls don't
block the API; CLI works in both modes; SDK works against the API; `/docs` +
`/redoc` render; all 17 tests pass; no Phase 3/4A/4B regression.

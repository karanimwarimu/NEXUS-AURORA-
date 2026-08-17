# Phase 4C System Integration Specification & Execution Plan

**System:** `nexora_crawler`

**Phase:** 4C Integration & Architecture Migration

**Target:** LLM Autonomous Implementation Agents

---

## 1. System Overview & Scope

Phase 4C expands `nexora_crawler` from a single-tenant crawl utility into a multi-tenant, schema-driven crawling and vector search platform with webhooks, fine-grained access control (JWT/API Keys), and enterprise GDPR endpoints.

### Key Metrics

* **Total New Files:** 13
* **New Database Tables:** 6 (`webhooks`, `webhook_deliveries`, `workspace_quotas`, `usage_records`, `audit_logs`, `extraction_schemas`)
* **Modified Tables:** 2 (`pages`, `crawl_jobs` — adding `workspace_id`)
* **New Dependencies:** 8 (`celery`, `slowapi`, `bcrypt`, `aiosqlite`, `asyncpg`, `python-multipart`, `PyJWT`, `httpx`)

---

## 2. Source Specification Sync & Conflict Resolution

The implementation unifies **`Phase_4C.md` (Original Spec)** and **`phase_4c_additional_integration.md` (Patch Spec)**.

| Component / Item | Spec Source | Resolution & Architecture Standard |
| --- | --- | --- |
| **Auth File Location** | Spec: `api/routes/auth.py`<br>

<br>Patch: `api/auth.py` | Standardize on **`nexora_crawler/api/auth.py`** (package-level auth module). |
| **Worker Engine** | Spec: Celery + Redis<br>

<br>Patch: `FastAPI.BackgroundTasks` | Use **`FastAPI.BackgroundTasks`** for lightweight async execution to prevent requiring external brokers (Redis/RabbitMQ). |
| **Subprocess vs. Reactor** | Patch: In-process `CrawlerProcess` | **REJECT In-process `CrawlerProcess`.** Retain subprocess isolation (`asyncio.create_subprocess_exec`) to prevent Twisted reactor collision crashes under `uvicorn`. |
| **Database Connection** | Spec: Dual DBs (`nexora.db` / `nexora_metadata.db`) | **UNIFY DB PATHS.** All API routes and Scrapy pipelines must share `NEXORA_METADATA_DB`. |

---

## 3. Structural Breakages & Technical Risks

```
                   +---------------------------------------+
                   |  CRITICAL ARCHITECTURAL CONSTRAINTS   |
                   +---------------------------------------+
                                       |
    +----------------------------------+----------------------------------+
    |                                  |                                  |
    v                                  v                                  v
[BREAK 1: Import Collapse]   [BREAK 2: Reactor Collision]   [BREAK 3: Data Divergence]
`api.py` replaced by         In-process `CrawlerProcess`    Route operations write
`api/` directory package.     crashes long-running Async     to `nexora.db` while Scrapy
Requires `__init__.py` and    uvicorn reactor. Retain        writes to `nexora_metadata.db`.
`__main__.py` entry points.  subprocess isolation.         Must consolidate on single DB.

```

### 1. Package Structure Breakdown

Replacing `nexora_crawler/api.py` with `nexora_crawler/api/` breaks legacy module imports.

* **Fix:** Convert `api.py` contents into `nexora_crawler/api/__init__.py` and expose the CLI entry point via `nexora_crawler/api/__main__.py`.

### 2. Reactor Collision

`CrawlerProcess` installs a Twisted reactor. Running this inside an active `uvicorn` loop triggers a unrecoverable runtime crash.

* **Fix:** Execute crawlers exclusively using `asyncio.create_subprocess_exec("python", "-m", "nexora_crawler.api", ...)` to enforce process boundary safety.

### 3. Dual Database Split

Phase 4C defaults to `./data/nexora.db`, while legacy pipelines write to `./data/nexora_metadata.db`.

* **Fix:** Re-route `nexora_crawler/api/database/connection.py` to target `NEXORA_METADATA_DB` directly.

### 4. Schema Missing `workspace_id`

`pages` and `crawl_jobs` lack a `workspace_id` column, breaking search and GDPR requests.

* **Fix:** Apply non-destructive migrations (`ALTER TABLE ... ADD COLUMN workspace_id TEXT DEFAULT 'default'`).

---

## 4. Architectural Target State

### Required Directory Structure

```
nexora_crawler/
├── api/
│   ├── __init__.py            # Main FastAPI instance, legacy route definitions
│   ├── __main__.py            # Entrypoint for python -m nexora_crawler.api
│   ├── auth.py                # JWT verification, API key auth, workspace isolation
│   ├── database/
│   │   ├── __init__.py
│   │   └── connection.py      # Async connection engine (aiosqlite/asyncpg)
│   ├── middleware/
│   │   ├── __init__.py
│   │   └── logging.py         # Structured JSON logging middleware
│   ├── routes/
│   │   ├── __init__.py        # Exposes router aggregates
│   │   ├── search.py          # Vector + hybrid search HTTP interface
│   │   ├── webhooks.py        # Webhook registration & management
│   │   ├── jobs.py            # Async job orchestration
│   │   ├── gdpr.py            # Erasure / right-to-be-forgotten router
│   │   ├── extract.py         # Schema-driven structured extraction
│   │   └── health.py          # Liveness and readiness endpoints
│   └── tasks/
│       ├── __init__.py
│       └── crawl_task.py      # Subprocess execution worker wrapper
├── jobs/
│   ├── __init__.py
│   └── registry.py            # Execution registry for generic job processing
├── tasks/
│   ├── __init__.py
│   └── dispatcher.py         # Background task dispatch logic
├── cli/
│   └── main.py                # Updated CLI client
└── sdk/
    └── client.py              # Native Python client library

```

---

## 5. Schema Modifications & Additions

### DDL Updates (SQLite / PostgreSQL Compatible)

```sql
-- 1. Schema Patch for Existing Core Tables
ALTER TABLE pages ADD COLUMN workspace_id TEXT DEFAULT 'default';
ALTER TABLE crawl_jobs ADD COLUMN workspace_id TEXT DEFAULT 'default';

CREATE INDEX IF NOT EXISTS idx_pages_workspace ON pages(workspace_id);
CREATE INDEX IF NOT EXISTS idx_crawl_jobs_workspace ON crawl_jobs(workspace_id);

-- 2. New Infrastructure Tables
CREATE TABLE IF NOT EXISTS webhooks (
    id TEXT PRIMARY KEY,
    workspace_id TEXT NOT NULL,
    url TEXT NOT NULL,
    secret TEXT NOT NULL,
    events TEXT NOT NULL, -- JSON-encoded array
    is_active INTEGER DEFAULT 1,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS webhook_deliveries (
    id TEXT PRIMARY KEY,
    webhook_id TEXT NOT NULL,
    event_type TEXT NOT NULL,
    payload TEXT NOT NULL, -- JSON-encoded object
    response_code INTEGER,
    status TEXT NOT NULL, -- SUCCESS, FAILED
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY(webhook_id) REFERENCES webhooks(id)
);

CREATE TABLE IF NOT EXISTS workspace_quotas (
    workspace_id TEXT PRIMARY KEY,
    max_crawls_per_month INTEGER DEFAULT 1000,
    max_pages_per_crawl INTEGER DEFAULT 500,
    max_vector_searches_per_min INTEGER DEFAULT 60,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS usage_records (
    id TEXT PRIMARY KEY,
    workspace_id TEXT NOT NULL,
    resource_type TEXT NOT NULL, -- CRAWL, VECTOR_SEARCH, EXTRACTION
    quantity INTEGER NOT NULL,
    timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS audit_logs (
    id TEXT PRIMARY KEY,
    workspace_id TEXT NOT NULL,
    actor_id TEXT NOT NULL,
    action TEXT NOT NULL,
    target_resource TEXT NOT NULL,
    metadata TEXT, -- JSON-encoded metadata
    timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS extraction_schemas (
    id TEXT PRIMARY KEY,
    workspace_id TEXT NOT NULL,
    name TEXT NOT NULL,
    json_schema TEXT NOT NULL, -- Valid JSON Schema string
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

```

---

## 6. Execution Plan & Implementation Order

```
[Phase 1: Skeleton]   --->   [Phase 2: Database]   --->   [Phase 3: Security]
Package restructuring        Schema migration &           Auth middleware & JWT
and route definitions        unified connection pool      isolation routines

                                                                |
                                                                v

[Phase 6: CLI & SDK]   <---   [Phase 5: Job Engine] <---   [Phase 4: Routes]
Python client updates         Subprocess workers &         Search, GDPR, Webhooks,
and validation suites         task dispatcher              and Extraction

```

### Phase 1: Package Restructuring & Core Skeleton

1. Migrate `nexora_crawler/api.py` functions to `nexora_crawler/api/__init__.py`.
2. Construct `nexora_crawler/api/__main__.py` routing flags directly to internal execution routines.
3. Validate backwards-compatibility with existing runs:
```bash
python -m nexora_crawler.api --help
uvicorn nexora_crawler.api:app --reload

```



### Phase 2: Consolidated Persistence Layer

1. Extend `nexora_crawler/storage/local_sqlite.py` to auto-apply missing columns (`workspace_id`) on boot.
2. Initialize the 6 new Phase 4C tables during startup hooks.
3. Ensure `nexora_crawler/api/database/connection.py` references `settings.NEXORA_METADATA_DB`.

### Phase 3: Security & Isolation Layer

1. Implement `nexora_crawler/api/auth.py` supporting JWT parsing, signature validation, and dev-bypass headers (`X-Workspace-Id`).
2. Attach workspace identity injectables (`Depends(get_workspace_id)`) to non-legacy routes.

### Phase 4: Route Handlers Implementation

1. Construct `api/routes/search.py` bridging `BaseVectorStore.hybrid_search()` to the API.
2. Construct `api/routes/gdpr.py` enforcing cascade deletion across `pages`, metadata stores, and vector indices by `workspace_id`.
3. Build `extract.py`, `webhooks.py`, and `health.py`.

### Phase 5: Task Management Infrastructure

1. Implement `nexora_crawler/jobs/registry.py` and `nexora_crawler/tasks/dispatcher.py`.
2. Configure `api/tasks/crawl_task.py` using `asyncio.create_subprocess_exec` to execute jobs cleanly without conflicting with active Twisted reactors.

### Phase 6: SDK & Verification

1. Create `nexora_crawler/sdk/client.py` using `httpx`.
2. Execute target integration test suite to verify route stability and data persistence:
```bash
pytest tests/ -k "phase_4c"

```
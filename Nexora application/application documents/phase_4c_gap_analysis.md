# Phase 4C — Independent Gap Analysis

**Reviewed document:** `phase_4c_integration_progress.md` (309 lines, authored by the implementing agent)
**Review date:** 2026-08-17
**Reviewer:** independent verification pass against the working tree
**Method:** every claim in the progress report was treated as an assertion to be checked against source,
against the on-disk databases, and — where possible — by execution. Nothing below is inferred from the
progress report itself.

---

## 1. Headline verdict

The structural work is real. The functional work is not.

Phase 4C's *skeleton* landed correctly: the package migration, the six new tables, the `workspace_id`
column definitions, the unified database path, the auth module, six routers, and the registry/dispatcher
pair all exist and all byte-compile. That is genuine progress and the report is right to claim it.

But **no Phase 4C write operation can currently succeed, no Phase 4C job can currently execute, and the
schema has never actually been applied to the live database.** On top of that, the schema-init code as
written **crashes on any pre-existing database**, which breaks the v4.5.0 crawl path that was previously
working. That last item is a regression, and it directly contradicts the report's closing line, "No
regressions introduced by Phase 4C integration."

| Dimension | Report says | Actually |
|---|---|---|
| Phases 1–10 | ✅ Complete | Files exist and compile; ~60% functionally complete |
| Phase 11 (tests) | 🔄 6/6 regression PASS | Cannot execute — required packages absent |
| Phase 12 (CLI/SDK) | ⏳ Deferred | Correct, genuinely absent |
| Live DB schema | Implied applied | **Not applied.** 429 rows, no `workspace_id`, zero new tables |
| Crawl path | Unaffected | **Broken** — `MetadataStore()` raises on existing DBs |
| New endpoints | 11 | 12 |
| New settings | 14 | 15, none of which are read by any consumer |
| Declared dependencies | not mentioned | 8 new imports, 0 added to `requirements.txt` |

---

## 2. BLOCKER — `MetadataStore` now raises on every pre-existing database

**Severity: S1. This is a v4.5.0 regression introduced by Phase 4C.**

`local_sqlite.py::_init_schema` executes one `executescript` block (lines 30–157) and *then* calls
`_migrate_schema()` (line 162). The script block contains, at line 64:

```sql
CREATE INDEX IF NOT EXISTS idx_pages_workspace_id ON pages(workspace_id);
```

On a **new** database this is fine — `CREATE TABLE IF NOT EXISTS pages (... workspace_id ...)` created the
column two statements earlier. On an **existing** database `CREATE TABLE IF NOT EXISTS` is a no-op, the
column does not exist yet, and the index creation fails. `_migrate_schema()` — the code that would have
added the column — never gets the chance to run, because it sits *after* the script that just raised.

Reproduced against a copy of the live 429-row store:

```
BEFORE tables: ['crawl_jobs', 'pages', 'sqlite_sequence']
Traceback (most recent call last):
  File "...local_sqlite.py", line 26, in __init__     self._init_schema()
  File "...local_sqlite.py", line 30, in _init_schema conn.executescript("""
sqlite3.OperationalError: no such column: workspace_id
```

Blast radius: `MetadataStore.__init__` calls `_init_schema()` unconditionally, so **every** consumer fails
at construction — `MetadataIndexerPipeline` (pipeline slot 165), `enrich.py`, and any diagnostic that opens
the store. The crawl pipeline cannot reach persistence at all against the real database.

The migration logic itself (lines 165–202) is correct. Once the column is pre-added by hand, the same
construction succeeds and does exactly what the report describes:

```
AFTER tables: audit_logs, crawl_jobs, extraction_schemas, pages, sqlite_sequence,
              usage_records, webhook_deliveries, webhooks, workspace_quotas
pages backfill: [('default', 429)]
crawl_jobs.workspace_id: True
```

**Fix:** hoist `_migrate_schema()` to run *before* the `executescript` block, or move the four
`workspace_id` index statements out of the script and into `_migrate_schema()` after the `ALTER TABLE`.
The former is the smaller change and keeps all DDL ordering in one place.

**Why the report missed it:** its Phase 3 evidence line reads "Custom schema test: **new DB** gets
`workspace_id` columns; existing rows backfilled with `'default'`". A fresh database was tested (that path
does work — 9 tables created), an existing one was not. The backfill half of that sentence was never
exercised, because a fresh DB has no rows to backfill.

---

## 3. The schema was never applied to the live database

Direct inspection of every `.db` in the tree:

| Database | Size | Rows | `workspace_id`? | Phase 4C tables? |
|---|---|---|---|---|
| `Crawler/nexora_crawler/data/nexora_metadata.db` (**live**) | 10.1 MB | 429 pages | ❌ absent | ❌ none of the 6 |
| `Crawler/data/nexora_metadata.db` (stale) | 60 KB | 3 pages | ❌ absent | ❌ none of the 6 |
| `Crawler/data/site_profiles.db` | 12 KB | — | n/a | n/a |

Both metadata stores contain exactly `pages`, `crawl_jobs`, `sqlite_sequence`. Phase 3 and Phase 5 are
therefore **code-complete but unapplied**. The report's ✅ on both is defensible as a statement about the
source, but it reads as a statement about the system, and the system does not have this schema.

Consequence, independent of §2: even with FastAPI installed, `POST /v1/webhooks` returns
`no such table: webhooks` against the live database, and `DELETE /v1/gdpr/erase` fails on
`WHERE workspace_id = ?`. There is no startup migration hook — the `lifespan` handler at
`api/__init__.py:133-138` only logs two lines; it never touches the database.

**Fix:** after correcting §2, call the migration from `lifespan` on API startup (and keep the existing
call from `MetadataStore.__init__` for the crawl path), then run it once against the live store.

---

## 4. No Phase 4C write ever commits

**Severity: S1.**

`api/database/connection.py:42` opens `aiosqlite.connect(db_path)` with the default `isolation_level`,
which means implicit transactions and **no autocommit**. A repo-wide grep for `commit(` across
`nexora_crawler/api/` returns **zero matches**. `close_db()` exists at line 49 and is never called from
anywhere, so the connection is not even closed cleanly on shutdown.

Every mutation in the new surface is therefore lost:

| Route | Statement | Outcome |
|---|---|---|
| `POST /v1/webhooks` | `INSERT INTO webhooks` | rolled back |
| `DELETE /v1/webhooks/{id}` | `DELETE FROM webhooks` | rolled back |
| `POST /v1/extract/schema` | `INSERT INTO extraction_schemas` | rolled back |
| `DELETE /v1/gdpr/erase` | `DELETE FROM pages`, `DELETE FROM crawl_jobs`, `INSERT INTO audit_logs` | rolled back |

The GDPR case is the serious one: the endpoint returns `status: "purged"` with a page count while nothing
was actually erased. That is a false compliance signal, not merely a bug.

**Fix:** either pass `isolation_level=None` at connect time for autocommit, or add `await db.commit()`
after each write. Given the GDPR route performs three related statements, an explicit commit per route is
the better choice — it keeps the erase atomic.

---

## 5. Tenant isolation can be bypassed by one header

**Severity: S1. Highest-impact security finding.**

`api/auth.py::get_workspace_id` checks the dev bypass *before* it checks credentials:

```python
async def get_workspace_id(
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(security),
    request: Request = None,
) -> str:
    # Development bypass
    if request and request.headers.get("X-Workspace-Id"):
        return request.headers.get("X-Workspace-Id")
    if not credentials:
        raise HTTPException(status_code=401, detail="Authentication required")
```

Any unauthenticated caller who sets `X-Workspace-Id: <anything>` is admitted as that tenant, on every
`/v1/*` route, with no token. The bypass is unconditional — there is no `NEXORA_ENV`/debug guard around it.

The exposure is not theoretical once §3 and §4 are fixed: `DELETE /v1/gdpr/erase` takes no body and no
parameters, deriving its entire target from this dependency. A single header value is sufficient to purge
an arbitrary workspace's pages, crawl jobs, and vector records.

Related, from the same file: `JWT_SECRET` defaults to the literal `"change-me-in-production"`, and
`require_admin` is a pass-through placeholder that authorises everyone.

**Fix:** gate the bypass behind an explicit opt-in env flag that defaults to off, evaluate it only after
the credential check fails, and refuse to start when `JWT_SECRET` is still the default. Replace
`require_admin` with a real role claim check before any admin surface is added.

---

## 6. Phase 10's settings are dead code

All 15 settings landed in `settings.py:331-353` — the report says 14; the actual list is
`NEXORA_API_HOST/PORT/WORKERS/LOG_LEVEL`, `NEXORA_JWT_SECRET_KEY/ALGORITHM/ACCESS_TOKEN_EXPIRE_MINUTES/REFRESH_TOKEN_EXPIRE_DAYS`,
`NEXORA_API_KEY_LENGTH`, `NEXORA_RATE_LIMIT_DEFAULT/BURST`, `NEXORA_CORS_ORIGINS`,
`NEXORA_LOG_FORMAT/LEVEL`, `NEXORA_STRUCTURED_LOGS`.

None of them is read by any consumer:

- `auth.py` reads `os.getenv("JWT_SECRET_KEY")` and `os.getenv("JWT_ALGORITHM")` — **not** the
  `NEXORA_`-prefixed settings. Setting `NEXORA_JWT_SECRET_KEY` has no effect on token validation.
- CORS origins are hard-coded at `api/__init__.py:150-155`; `NEXORA_CORS_ORIGINS` is ignored.
- `NEXORA_RATE_LIMIT_*` has no consumer because no rate limiter exists (§9).
- `NEXORA_LOG_*` / `NEXORA_STRUCTURED_LOGS` have no consumer because `api/middleware/` does not exist (§9).
- `NEXORA_API_HOST/PORT/WORKERS/LOG_LEVEL` are not referenced by the uvicorn launch path.

Phase 10 is best described as ⚠️ declared-not-wired rather than ✅.

---

## 7. Every job is a stub — Phases 7, 8 and 12 are hollow

`jobs/registry.py::_register_builtins()` registers all five job types with `handler_cls` left at its
`None` default. `tasks/dispatcher.py` then short-circuits:

```python
if handler.handler_cls is None:
    logger.warning("[Dispatcher] No handler class for job type '%s'", handler.job_type)
    return {"job_id": ctx["job_id"], "status": "completed",
            "message": f"Job type '{handler.job_type}' has no handler (stub)",
            "workspace_id": ctx["workspace_id"]}
```

So `POST /v1/jobs` and `POST /v1/extract/schema` both return success while doing nothing. Note the stub
reports `status: "completed"` — a caller cannot distinguish a real result from a no-op. The report's
Phase 8 verification, "`JobTypeRegistry.list()` returns 5 built-in types", is accurate and also the only
thing that was checked.

The verification command in the plan document, `curl -X POST .../v1/jobs -d '{"type":"index_search",...}'`,
returns HTTP 200 for exactly this reason. It is not evidence the job engine works.

Four further defects in this path:

1. **Reactor isolation ruling not implemented.** The version-1 plan mandates
   `asyncio.create_subprocess_exec` for crawl execution and explicitly rejects in-process `CrawlerProcess`.
   The dispatcher uses `loop.run_in_executor` instead, and `api/tasks/crawl_task.py` does not exist. This
   is currently harmless only because no handler runs; the moment a `crawl` handler is attached to a thread
   pool inside uvicorn, this becomes the reactor collision the plan was written to prevent. Legacy `/crawl`
   keeps the subprocess *model* but its spawn target is now a deleted file — see §16.1.
2. **Fire-and-forget task is GC-eligible.** `jobs.py:83` calls `asyncio.create_task(...)` and discards the
   handle. Python may collect the task before it completes, and exceptions inside it are swallowed. Keep a
   module-level set of live tasks with a done-callback, or use `BackgroundTasks`.
3. **No job status endpoint anywhere.** `POST /v1/jobs` returns `status: "queued"` and there is no
   `GET /v1/jobs/{id}` on the new surface to poll. The legacy `GET /crawl/{job_id}` reads the separate
   in-memory `_jobs` dict at `api/__init__.py:128` and knows nothing about dispatcher jobs. Async
   submission is currently a dead end for the caller.
4. **`extract.py` claims 202 for synchronous work.** It `await`s `dispatch_job(...)` inline, then returns
   HTTP 202 with `status: "queued"`. Both the status code and the field are wrong for what happened.

`jobs.py` also dropped the patch spec's `handler.is_external` condition on the inline path, so
`async_run: false` now runs *any* job type inline, including ones intended for external execution.

---

## 8. Route-level defects the report does not record

### 8.1 Vector store is never initialized — all search and GDPR calls fail

`ChromaVectorStore.__init__` sets `self._collection = None` (`chroma_store.py:44`); the collection is only
bound inside `await initialize()`. Three call sites build a store and use it immediately without
initializing:

- `search.py:106` (`find_similar` → `store.get(...)`)
- `search.py:135` (`_do_search` → `store.search(...)` / `hybrid_search(...)`)
- `gdpr.py:61` (`store.delete_by_workspace(...)`)

Each raises `AttributeError: 'NoneType' object has no attribute ...`, surfacing as HTTP 500. All three
`/v1/search/*` endpoints and the vector half of the GDPR erase are non-functional.

**Fix:** a module-level cached accessor that builds once and awaits `initialize()` once, shared by both
route modules — building a fresh `PersistentClient` per request is also wasteful.

### 8.2 asyncpg detection is dead code

`webhooks.py:54` branches on `hasattr(db, 'fetch_one')` and `:84` on `hasattr(db, 'fetch_all')`. asyncpg
pools expose `fetchrow`, `fetch`, `fetchval` and `execute` — **neither `fetch_one` nor `fetch_all` exists**,
so the Postgres branch is unreachable. Inside it, `db.fetchone(...)` is also not an asyncpg method. The
`gdpr.py:45` guard uses `hasattr(db, 'fetchval')`, which is correct, so the two files disagree on how to
detect the backend.

Worse, the fall-through consequence: `delete_webhook` (`webhooks.py:112`), both `gdpr.py` deletes, the
`audit_logs` insert, and `extract.py`'s insert all use `?` placeholders with **no dialect branch at all**.
Under Postgres every one of them raises a syntax error. The "SQLite (dev) / Postgres (prod)" promise in
`connection.py`'s own docstring does not hold.

### 8.3 The webhook secret is silently discarded

```python
out["_secret_display_once"] = secret
return WebhookOut(**out)
```

`WebhookOut` does not declare `_secret_display_once`, and Pydantic v2 defaults to `extra="ignore"`, so the
field is dropped without error. The secret is generated, stored, and never shown — the caller has no way to
sign or verify a payload. Pydantic also strips leading-underscore names from models regardless, so the
chosen field name could not have worked even with `extra="allow"`.

**Fix:** add an explicit `secret: Optional[str]` to a dedicated create-response model.

### 8.4 Hybrid search silently degrades on the default backend

`chroma_store.py:125` logs a warning and calls `search()` instead. `POST /v1/search/hybrid` accepts and
ignores `bm25_weight`, returning vector-only results with `backend: "chroma"` and no indication in the
response that the requested mode was not honoured. True hybrid requires the pgvector backend.

### 8.5 GDPR erase is immediate, not the 30-day soft delete it advertises

`gdpr.py` accepts a `BackgroundTasks` parameter and never uses it. The docstring says "Hard-delete
scheduled in 30 days", the response returns a `scheduled_hard_delete` timestamp 30 days out, and the actual
`DELETE` statements are unconditional and immediate. There is no soft-delete column, no scheduler, and no
retention job. The response contract describes a system that does not exist.

---

## 9. Genuinely missing deliverables

Confirmed absent by directory glob — these four directories do not exist:
`nexora_crawler/cli/`, `nexora_crawler/sdk/`, `nexora_crawler/api/middleware/`, `nexora_crawler/api/tasks/`.

| Deliverable | Source | Report status | Actual |
|---|---|---|---|
| `api/tasks/crawl_task.py` | version-1 §4, §6 Phase 5 | ✅ "Simplified in dispatcher" | Absent; subprocess-isolation ruling unimplemented (§7.1) |
| `api/middleware/logging.py` | version-1 §4 | ⏳ Deferred | Absent; `NEXORA_LOG_*` settings orphaned |
| `cli/main.py` | version-1 §4, §6 Phase 6 | ⏳ Phase 12 | Absent |
| `sdk/client.py` | version-1 §4, §6 Phase 6 | ⏳ Phase 12 | Absent (`httpx` **is** installed, so this is cheap to do) |
| `routes/results.py` | original spec | ⏳ Deferred | Absent |
| `routes/admin.py` | original spec | ⏳ Deferred | Absent |
| slowapi rate limiting | version-1 §1 deps | ⚠️ noted as not active | No `slowapi`/`Limiter` reference anywhere in `api/` |
| Auth issuance surface | original spec §3.2 | ⏳ "Adjusted" | No login/refresh/API-key endpoints, no `api_keys` table, `bcrypt` unused. `create_access_token` exists but nothing calls it — there is no way to obtain a token, which is why the header bypass in §5 is the *only* usable path |
| Webhook delivery | version-1 §1 (`webhook_deliveries`) | not claimed | Table created, **never written to**. No signing, no retry, no delivery worker |
| Quotas & metering | version-1 §1 (`workspace_quotas`, `usage_records`) | not claimed | Both tables created, **neither read nor written** by any code |
| Phase 4C tests | version-1 §6 Phase 6 | 🔄 In progress | No `test_phase4c*.py` exists. `pytest tests/ -k "phase_4c"` collects 0 items |
| Dependency declaration | version-1 §1 (8 new deps) | not mentioned | `requirements.txt` untouched (still `scrapy==2.11.1`, `scrapy-playwright>=0.0.40`). None of fastapi, uvicorn, pydantic, PyJWT, aiosqlite, asyncpg, slowapi, bcrypt, python-multipart declared. No `pyproject.toml`/`setup.py` anywhere |

Three of these tables — `webhook_deliveries`, `workspace_quotas`, `usage_records` — are pure schema with no
consumer. Half of Phase 5's ✅ is inventory, not capability.

---

## 10. Phase 11 test results cannot be reproduced

The report asserts a 6/6 regression pass plus `test_vector_store.py` PASS. Probing the only interpreter in
the repository (`nexora venv\Scripts\python.exe`, CPython 3.13.9 — `**/Scripts/python.exe` matches nothing
else, and there is no system Python on PATH):

```
MISSING  scrapy      MISSING  fastapi     MISSING  uvicorn    MISSING  pydantic
MISSING  jwt         MISSING  aiosqlite   MISSING  chromadb   MISSING  litellm
MISSING  slowapi     MISSING  bcrypt      MISSING  pandas     MISSING  bs4
MISSING  trafilatura
```

All five named regression files exist, but each imports `nexora_crawler.middlewares.dynamic_detection`,
`nexora_crawler.items`, `nexora_crawler.spiders.nexora_spider` or `nexora_crawler.pipelines`, every one of
which reaches `scrapy` transitively. They cannot collect, let alone pass, in this environment. The same
applies to "PyJWT installed" (Phase 6), "`from nexora_crawler.api import app` — imports FastAPI app
correctly" and "`python -m nexora_crawler.api --help` — CLI help renders" (Phase 1), and "All 11 Phase 4C
routes registered in FastAPI app" (Phases 7/9).

Two claims do hold up:

- **`py_compile` passes.** Verified independently — all 19 new and modified files byte-compile cleanly.
- **"1501 records" is real.** `Crawler/nexora_crawler/data/chroma/chroma.sqlite3` (35.6 MB) contains exactly
  1501 rows in `embeddings`, collection `nexora_chunks`. The figure is corroborated on disk even though the
  test cannot run now — the dependencies were evidently present when the 429 pages and 1501 chunks were
  produced, and are not present now.

The reasonable reading is not that results were invented, but that the report records outcomes from an
environment state that no longer exists, without saying so. Treat the whole Phase 11 table as unverified
until the stack is reinstalled.

**Route count correction:** the six new routers expose **12** endpoints, not 11 — search 3, webhooks 3,
jobs 2, health 2, gdpr 1, extract 1 (17 including the 5 legacy `app`-level routes).

---

## 11. What the report gets right

Stated plainly, because it is a substantial amount of correct work:

- **Phase 1/2 package migration.** `api.py` → `api/` with `__init__.py` carrying the FastAPI app and all
  legacy routes, `__main__.py` as the `python -m` entry point. Version-1 BREAK 1 resolved.
- **Phase 3 `workspace_id` propagation, at code level.** Column on both tables, index, `_migrate_schema`
  with backfill (correct once §2 is fixed — verified to backfill all 429 rows), spider parameter,
  `insert_page` persisting `item.get("workspace_id", "default")`. Version-1 BREAK 4 resolved in source.
- **Phase 4 DB unification.** `connection.py:21` imports `NEXORA_METADATA_DB` from settings and derives
  `DATABASE_URL` from it. Version-1 BREAK 3 resolved at code level — this was the highest-risk item in the
  plan and it was handled correctly.
- **Phase 5 tables.** All six created with sensible indexes, and the shapes are internally consistent:
  `gdpr.py`'s `audit_logs` insert matches the real column list, `extract.py`'s insert matches
  `extraction_schemas`, `webhooks.py`'s insert matches `webhooks`.
- **Phase 9 wiring.** Six routers included; legacy `/`, `/strategies`, `/crawl`, `/crawl/{job_id}`, `/jobs`
  untouched. The report's "existing endpoints unaffected" is accurate as to routing, though not as to
  execution (§16.1).
- **Correct judgement calls the report under-sells:** `search.py` fixed the patch spec's wrong import path
  (`nexora_crawler.ai.embedding_engine` → `AI_Utilities.embedding_engine`); `find_similar` enforces
  `record.workspace_id != workspace_id` → 403, which is the one place cross-tenant access *is* checked;
  and rejecting in-process `CrawlerProcess` for the legacy crawl path preserved subprocess isolation.

---

## 12. Correction to the plan document, not the code

`phase 4c version 1 .md` §5 publishes DDL that does not match what shipped, and the **code is the better
version**. Anyone reconciling the two should not "fix" the code to match:

| Table | version-1 §5 says | Built (and used by routes) |
|---|---|---|
| `webhooks` | `id TEXT PRIMARY KEY`, `events`, `secret` | `id INTEGER PRIMARY KEY AUTOINCREMENT`, `event_types`, `secret` |
| `audit_logs` | `actor_id`, `target_resource`, `metadata` | `actor`, `target_id`, `details`, `ip_address` |
| `extraction_schemas` | `id`, `name`, `json_schema` | `job_id` (key), `schema_json` — no `id`, no `name` |
| `workspace_quotas` | `max_crawls_per_month`, `max_pages_per_crawl`, `max_vector_searches_per_min` | `pages_per_month`, `storage_gb`, `vector_records`, `api_rpm`, `schema_extracts_per_day` |
| `usage_records` | `resource_type`, `quantity`, `timestamp` | `period`, `pages_crawled`, `storage_bytes`, `vector_records`, `api_calls`, `recorded_at`, `UNIQUE(workspace_id, period)` |
| `webhook_deliveries` | `payload`, `response_code`, `status` | `job_id`, `status_code`, `attempt`, `delivered_at`, `error` |

The implementation followed the patch spec's shapes. Also worth noting: version-1 §1 lists `celery` among
the new dependencies, which the same document then rules out in §2 — Celery is correctly absent.

Minor, unresolved: `health.py` reports `"version": "2.5.0"` (matching the app) where the original spec said
`2.0.0`. The app's own version string is `2.5.0` while the codebase is described elsewhere as v4.5.0; that
pre-dates Phase 4C and is out of scope here, but it means `/health` reports a version that matches no
release note.

---

## 13. Recommended order of work

Ordered by dependency, not by severity — several S1s cannot be *tested* until the environment is restored.

**Step 0 — restore the environment.** Nothing below can be verified without it. Add the eight new
dependencies to `requirements.txt` and install, along with the packages the crawl path already needed:

```
# Phase 4C additions
fastapi, uvicorn[standard], pydantic, PyJWT, aiosqlite, asyncpg, python-multipart, bcrypt, slowapi
# already-imported but undeclared
scrapy==2.11.1, scrapy-playwright>=0.0.48, litellm, chromadb, pandas, beautifulsoup4,
trafilatura, extruct, simhash, fasttext
```

Note `scrapy-playwright>=0.0.48` — the pinned `>=0.0.40` silently no-ops `PLAYWRIGHT_ABORT_REQUEST`.

**Step 1 — unbreak the crawl path (§2).** Reorder `_migrate_schema()` before the DDL script. This is the
only item that is a regression against previously working behaviour, so it goes first.

**Step 2 — apply the schema to the live database (§3).** Run the migration once against
`Crawler/nexora_crawler/data/nexora_metadata.db`, back it up first, and confirm 429 rows backfill to
`'default'` and all six tables appear. Add the migration call to `lifespan`.

**Step 3 — close the auth bypass (§5).** Env-gated, default-off, evaluated after the credential check.
Refuse startup on the default `JWT_SECRET`. Do this before Step 4 makes the destructive routes real.

**Step 4 — make writes durable (§4).** Commit per route, or autocommit at connect.

**Step 5 — initialize the vector store once (§8.1).** Unblocks all three search endpoints and the vector
half of GDPR erase in one change.

**Step 6 — pick a stance on jobs (§7).** Either attach real `handler_cls` implementations plus a
`GET /v1/jobs/{id}` status endpoint, or make the stub path return HTTP 501 with
`status: "not_implemented"`. The current "completed" response for a no-op is the worst of both.

**Step 7 — repair the dialect handling (§8.2).** Fix the `hasattr` probes to real asyncpg method names and
add the missing `$n` branches, or drop the Postgres pretence from the docstring until it is implemented.

**Step 8 — smaller correctness items.** Webhook secret in the response model (§8.3); `extract.py`'s
202/"queued" mismatch (§7.4); either implement the GDPR 30-day soft delete or stop advertising it (§8.5);
surface the hybrid-search degradation in the response rather than only in a log line (§8.4).

**Step 9 — write the Phase 4C tests.** None exist. Minimum useful set: migration against a populated
database (would have caught §2), a write-then-read round trip per mutating route (would have caught §4),
an unauthenticated `X-Workspace-Id` request expecting 401 (would have caught §5), and a job submission
asserting real work occurred (would have caught §7).

**Deferrable without risk:** `cli/main.py`, `sdk/client.py`, `routes/results.py`, `routes/admin.py`,
structured logging middleware, quotas/metering, webhook delivery, slowapi. The report's judgement to defer
these is sound — but they should be tracked as unbuilt features rather than left implied by the presence of
their tables.

---

## 14. Verification commands used

Run from the repository root. All are read-only except the migration test, which operates on a temp copy.

```powershell
$py = ".\nexora venv\Scripts\python.exe"

# Dependency presence
foreach ($m in @('scrapy','fastapi','uvicorn','pydantic','jwt','aiosqlite','chromadb')) {
  & $py -c "import importlib,sys; sys.exit(0 if importlib.util.find_spec('$m') else 1)"
  if ($LASTEXITCODE -eq 0) { "PRESENT $m" } else { "MISSING $m" }
}

# Byte-compile the Phase 4C surface
& $py -m py_compile "Nexora application\Crawler\nexora_crawler\api\routes\search.py"

# On-disk schema state (stdlib sqlite3 — works without the stack installed)
& $py -c @"
import sqlite3
c = sqlite3.connect(r'Nexora application/Crawler/nexora_crawler/data/nexora_metadata.db')
print(sorted(r[0] for r in c.execute(\"SELECT name FROM sqlite_master WHERE type='table'\")))
print([r[1] for r in c.execute('PRAGMA table_info(pages)')])
"@

# Reproduce the §2 blocker: copy the live DB to a temp path, then construct MetadataStore against it
```

**Report scope:** this document analyses only. No source file, no database, and no other document was
modified in producing it — including `phase_4c_integration_progress.md`, which is left as authored.

---
---

# Part II — Verification against `Phase_4C_Verification_Checklist.md`

**Added:** 2026-08-17, second pass. Sections 1–14 above were written against the implementing agent's
progress report. This part re-walks the same tree against the **verification checklist**, which asks for
things the progress report never claimed and therefore never covered. It found **one further P0 that breaks
crawl execution outright**, plus five defects not recorded anywhere.

Checklist Sections 1–8 are mapped below (§15), the new defects are written up in §16, the mandatory
Section 9 test matrix is in §17, and the checklist's required Verdict / prioritised findings / Definition-of-
Done sign-off are in §18–§20.

---

## 15. Checklist coverage map

### Section 1 — Package structure

| # | Item | Result | Evidence |
|---|---|---|---|
| 1.1 | old `api.py` gone | ✅ PASS | glob `nexora_crawler/api.py` → no files |
| 1.2 | `api/__init__.py` has app + legacy endpoints | ✅ PASS | `app` at `:141`; `/`, `/strategies`, `/crawl`, `/crawl/{job_id}`, `/jobs` at `:167`–`:241`; `_run_crawl` at `:246`; CLI fns at `:441`–`:525` |
| 1.3 | `api/__main__.py` exists | ✅ PASS | 4 lines, `from . import main; main()` |
| 1.4 | `api/routes/__init__.py` exists | ⚠️ PARTIAL | exists but is docstring-only — "Routers will be added here as they are implemented". Aggregation happens in `api/__init__.py:158` instead. Acceptable as a marker; the checklist's "exports **or** marks" is satisfied |
| 1.5 | `from nexora_crawler.api import app` / uvicorn resolves | ⏭️ SKIP | fastapi absent (§10) — unverifiable, not assumable |
| 1.6 | **no stale references to the deleted `api.py`** | ❌ **FAIL (P0)** | **two live references** at `:265` and `:408`, both spawning it as a subprocess. See §16.1 |
| 1.7 | CLI modes work | ❌ FAIL | `--url` (direct, in-process) is sound; interactive mode routes through the broken spawn at `:464` → `:408`. `--help`/`--server` unverifiable (fastapi absent) |

### Section 2 — Required files + wiring

Patch-layer files 2.1–2.7 all ✅ **exist and are wired**; original-spec files are mostly absent:

| # | File | Result |
|---|---|---|
| 2.1–2.7 | `auth.py`, `database/connection.py`, `routes/{search,webhooks,jobs,gdpr,extract}.py` | ✅ PASS (exist + `include_router`ed) — functional defects in §4, §5, §7, §8 |
| 2.8 | `routes/health.py` | ✅ PASS |
| 2.9 | `routes/crawl.py` | ❌ FAIL — absent. `/crawl/start`, `/crawl/batch`, `/crawl/status/{id}`, `/crawl/cancel/{id}`, `/crawl/list` **do not exist**. Only the legacy `POST /crawl` + `GET /crawl/{job_id}` + `GET /jobs` do (§16.4) |
| 2.10 | `routes/results.py` | ❌ FAIL — absent |
| 2.11 | `routes/admin.py` | ❌ FAIL — absent |
| 2.12 | `api/tasks/crawl_task.py` (+ `set_jobs_store`) | ❌ FAIL — directory absent |
| 2.13 | `api/middleware/logging.py` | ❌ FAIL — directory absent |
| 2.14 | `cli/main.py` | ❌ FAIL — directory absent |
| 2.15 | `sdk/client.py` | ❌ FAIL — directory absent |
| 2.16 | all routers included | ⚠️ PARTIAL — six `/v1/*` + health included; **no auth router and no crawl router exist to include**. `/openapi.json` unverifiable (fastapi absent) |
| 2.17 | `LoggingMiddleware` **and** CORS added | ⚠️ PARTIAL — CORS at `:149`; `LoggingMiddleware` does not exist |
| 2.18 | `/docs`, `/redoc`, `/openapi.json` | ✅ PASS by default — `FastAPI(...)` at `:141` does not disable `docs_url`/`redoc_url` |

**Doc-contradiction check:** auth exists **only** at `api/auth.py`. No `api/routes/auth.py`, so there is no
drift between two implementations. The patch layout won, as the checklist requires.

<!-- PART2-S3 -->


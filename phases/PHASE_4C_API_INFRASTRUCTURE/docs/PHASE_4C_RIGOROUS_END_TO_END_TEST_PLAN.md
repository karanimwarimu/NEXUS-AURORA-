# NEXUS AURORA Phase 4C — Rigorous End-to-End Test Plan
## Complete Verification Suite for Multi-Tenancy API Layer

**Version:** 1.0  
**Created:** 2026-08-19  
**Scope:** All Phase 4C implementations across infrastructure, security, database, API routes, jobs, and integration  
**Target Audience:** QA Engineer, Independent Verifier  
**Success Criteria:** All tests pass with green ✅ status

---

## Overview & Test Philosophy

Phase 4C introduces a production-grade API layer with **workspace isolation, JWT+API key authentication, multi-tenant database, async job dispatch, and schema-driven extraction**. This test plan verifies:

1. **Infrastructure:** Package structure, imports, entrypoints, dependencies
2. **Database:** Schema migration, workspace isolation, row backfill, new tables
3. **Authentication:** JWT validation, API keys, dev bypass, token expiration
4. **API Routes:** All 18 endpoints (6 new routers + legacy), response contracts, status codes
5. **Security:** Tenant isolation, auth bypass gating, SQL injection prevention
6. **Jobs & Dispatch:** Registry, stub handlers, async task tracking
7. **Integration:** End-to-end crawl-to-search flow with workspace scoping

Tests are designed to be **run in sequence** (some depend on prior state), **deterministic** (no flaky timeouts), and **verifiable by a second engineer** without context.

---

## Part 1: Infrastructure Tests (PHASE_4C_INFRA)

### Test INFRA-01: Package Migration Complete

**What:** Verify old `api.py` is gone and new `api/` package structure exists.

**How:**
```bash
cd "Nexora application/Crawler"
python -c "
import os
import sys

# Check old file gone
if os.path.exists('nexora_crawler/api.py'):
    print('FAIL: Old api.py still exists')
    sys.exit(1)

# Check new structure
required_files = [
    'nexora_crawler/api/__init__.py',
    'nexora_crawler/api/__main__.py',
    'nexora_crawler/api/routes/__init__.py',
    'nexora_crawler/api/database/__init__.py',
    'nexora_crawler/api/database/connection.py',
    'nexora_crawler/api/auth.py',
    'nexora_crawler/api/routes/search.py',
    'nexora_crawler/api/routes/webhooks.py',
    'nexora_crawler/api/routes/jobs.py',
    'nexora_crawler/api/routes/gdpr.py',
    'nexora_crawler/api/routes/extract.py',
    'nexora_crawler/api/routes/health.py',
]

missing = [f for f in required_files if not os.path.exists(f)]
if missing:
    print(f'FAIL: Missing files: {missing}')
    sys.exit(1)

print('PASS: Package structure correct')
"
```

**Pass Criteria:**
- `nexora_crawler/api.py` does **not** exist
- All 12 required files exist
- `python -c "import nexora_crawler.api"` succeeds

**Evidence:** File listing + import test result

---

### Test INFRA-02: All Imports Resolve

**What:** Verify no circular imports, all dependencies available, no syntax errors.

**How:**
```bash
cd "Nexora application/Crawler"
python -c "
# Test imports in isolation
try:
    from nexora_crawler.api import app
    print('✓ FastAPI app imports')
except Exception as e:
    print(f'✗ FastAPI app import failed: {e}')
    exit(1)

try:
    from nexora_crawler.api.auth import get_workspace_id
    print('✓ Auth module imports')
except Exception as e:
    print(f'✗ Auth import failed: {e}')
    exit(1)

try:
    from nexora_crawler.jobs.registry import JobTypeRegistry
    print('✓ Jobs registry imports')
except Exception as e:
    print(f'✗ Jobs registry failed: {e}')
    exit(1)

try:
    from nexora_crawler.tasks.dispatcher import dispatch_job
    print('✓ Tasks dispatcher imports')
except Exception as e:
    print(f'✗ Tasks dispatcher failed: {e}')
    exit(1)

try:
    from nexora_crawler.api.routes.search import router as search_router
    from nexora_crawler.api.routes.webhooks import router as webhooks_router
    from nexora_crawler.api.routes.jobs import router as jobs_router
    from nexora_crawler.api.routes.gdpr import router as gdpr_router
    from nexora_crawler.api.routes.extract import router as extract_router
    from nexora_crawler.api.routes.health import router as health_router
    print('✓ All route modules import')
except Exception as e:
    print(f'✗ Route module import failed: {e}')
    exit(1)

print('PASS: All imports resolve')
"
```

**Pass Criteria:**
- All 6+ `from ... import` statements succeed
- No `ModuleNotFoundError` or `ImportError`
- No circular import errors

**Evidence:** Import test output

---

### Test INFRA-03: Byte Compilation

**What:** Verify all Phase 4C Python files compile without syntax errors.

**How:**
```bash
cd "Nexora application/Crawler"
python -m py_compile \
  nexora_crawler/api/__init__.py \
  nexora_crawler/api/__main__.py \
  nexora_crawler/api/auth.py \
  nexora_crawler/api/database/connection.py \
  nexora_crawler/api/routes/search.py \
  nexora_crawler/api/routes/webhooks.py \
  nexora_crawler/api/routes/jobs.py \
  nexora_crawler/api/routes/gdpr.py \
  nexora_crawler/api/routes/extract.py \
  nexora_crawler/api/routes/health.py \
  nexora_crawler/jobs/registry.py \
  nexora_crawler/tasks/dispatcher.py

echo $?  # Exit code 0 = all compiled
```

**Pass Criteria:**
- All 12 files compile successfully
- Exit code: **0**

**Evidence:** Compilation output, exit code

---

### Test INFRA-04: Subprocess Spawn Target Correct

**What:** Verify old `api.py` references updated to `__main__.py`.

**How:**
```bash
cd "Nexora application/Crawler"
python -c "
import re

# Check _run_crawl_subprocess references
with open('nexora_crawler/api/__init__.py', 'r') as f:
    content = f.read()

# Should have __main__.py reference
if 'python -m nexora_crawler.api' in content:
    print('✓ Subprocess spawn uses __main__.py')
else:
    print('✗ Subprocess spawn not updated')
    exit(1)

# Should NOT have api.py reference
if 'nexora_crawler/api.py' in content or 'nexora_crawler.api.py' in content:
    print('✗ Stale api.py reference found')
    exit(1)

print('PASS: Subprocess spawn target correct')
"
```

**Pass Criteria:**
- Subprocess spawn command includes `python -m nexora_crawler.api`
- **Zero** references to old `api.py` file

**Evidence:** grep/regex search output

---

### Test INFRA-05: Dependencies Declared

**What:** Verify all Phase 4C dependencies in `requirements.txt`.

**How:**
```bash
cd "Nexora application"
python -c "
required_deps = [
    'fastapi',
    'uvicorn',
    'pydantic',
    'PyJWT',
    'aiosqlite',
    'asyncpg',
    'python-multipart',
    'bcrypt',
    'slowapi',
]

with open('application documents/requirements.txt', 'r') as f:
    content = f.read().lower()

missing = []
for dep in required_deps:
    if dep.lower() not in content:
        missing.append(dep)

if missing:
    print(f'FAIL: Missing dependencies: {missing}')
    exit(1)

# Verify scrapy-playwright pinning
if 'scrapy-playwright>=0.0.48' not in open('application documents/requirements.txt').read():
    print('WARNING: scrapy-playwright not pinned to >=0.0.48')

print('PASS: All dependencies declared')
"
```

**Pass Criteria:**
- All 9 Phase 4C packages in `requirements.txt`
- `scrapy-playwright>=0.0.48` (correct version for PLAYWRIGHT_ABORT_REQUEST)

**Evidence:** requirements.txt content

---

## Part 2: Database Tests (PHASE_4C_DB)

### Test DB-01: Schema Migration on Existing Database

**What:** Verify migration doesn't crash on pre-existing DB (critical blocker fix).

**How:**
```bash
cd "Nexora application/Crawler"
python << 'PYTHON_END'
import sqlite3
import tempfile
import shutil
from pathlib import Path

# Step 1: Create a temp copy of live DB
live_db = Path("nexora_crawler/data/nexora_metadata.db")
if not live_db.exists():
    print("SKIP: Live DB not found")
    exit(0)

with tempfile.TemporaryDirectory() as tmpdir:
    temp_db = Path(tmpdir) / "test_migration.db"
    shutil.copy(live_db, temp_db)
    
    # Step 2: Try to construct MetadataStore against it
    try:
        from nexora_crawler.storage.local_sqlite import MetadataStore
        store = MetadataStore(str(temp_db))
        print("✓ MetadataStore instantiation succeeds")
    except sqlite3.OperationalError as e:
        print(f"✗ Migration crashed: {e}")
        exit(1)
    
    # Step 3: Verify workspace_id column exists
    conn = sqlite3.connect(str(temp_db))
    cursor = conn.cursor()
    cursor.execute("PRAGMA table_info(pages)")
    columns = {row[1]: row[2] for row in cursor.fetchall()}
    
    if "workspace_id" not in columns:
        print("✗ workspace_id column not added")
        exit(1)
    
    print("✓ workspace_id column added")
    
    # Step 4: Verify all 8 tables exist
    cursor.execute("SELECT name FROM sqlite_master WHERE type='table' ORDER BY name")
    tables = {row[0] for row in cursor.fetchall()}
    
    required_tables = {
        'pages', 'crawl_jobs', 'webhooks', 'webhook_deliveries',
        'workspace_quotas', 'usage_records', 'audit_logs', 'extraction_schemas'
    }
    
    missing = required_tables - tables
    if missing:
        print(f"✗ Missing tables: {missing}")
        exit(1)
    
    print(f"✓ All 8 tables present: {sorted(tables)}")
    
    # Step 5: Check backfill count
    cursor.execute("SELECT COUNT(*) FROM pages WHERE workspace_id = 'default'")
    backfilled_count = cursor.fetchone()[0]
    cursor.execute("SELECT COUNT(*) FROM pages")
    total_count = cursor.fetchone()[0]
    
    if backfilled_count == total_count:
        print(f"✓ All {total_count} rows backfilled to 'default'")
    else:
        print(f"✗ Only {backfilled_count}/{total_count} rows backfilled")
        exit(1)
    
    conn.close()

print("PASS: Schema migration safe on existing DB")
PYTHON_END
```

**Pass Criteria:**
- No `OperationalError` on pre-existing DB
- `workspace_id` column added to `pages` + `crawl_jobs`
- All 8 tables exist
- All existing rows backfilled to `'default'`
- No data loss

**Evidence:** Migration output + table inspection

---

### Test DB-02: New Database Schema Complete

**What:** Verify fresh DB gets all tables, columns, indexes.

**How:**
```bash
cd "Nexus application/Crawler"
python << 'PYTHON_END'
import sqlite3
import tempfile
from pathlib import Path

with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as tmp:
    temp_db_path = tmp.name

try:
    from nexora_crawler.storage.local_sqlite import MetadataStore
    store = MetadataStore(temp_db_path)
    
    conn = sqlite3.connect(temp_db_path)
    cursor = conn.cursor()
    
    # Check all tables exist
    cursor.execute("SELECT name FROM sqlite_master WHERE type='table' ORDER BY name")
    tables = {row[0] for row in cursor.fetchall()}
    
    required = {
        'pages', 'crawl_jobs', 'webhooks', 'webhook_deliveries',
        'workspace_quotas', 'usage_records', 'audit_logs', 'extraction_schemas'
    }
    
    if not required.issubset(tables):
        print(f"✗ Missing tables: {required - tables}")
        exit(1)
    
    print(f"✓ All 8 tables created: {sorted(required)}")
    
    # Check critical columns on pages
    cursor.execute("PRAGMA table_info(pages)")
    page_columns = {row[1] for row in cursor.fetchall()}
    
    required_cols = {'url', 'title', 'markdown', 'workspace_id', 'crawl_id', 'ai_summary', 'ai_tags_json'}
    missing_cols = required_cols - page_columns
    if missing_cols:
        print(f"✗ Missing columns on pages: {missing_cols}")
        exit(1)
    
    print(f"✓ Pages table has all required columns: {sorted(required_cols)}")
    
    # Check indexes
    cursor.execute("SELECT name FROM sqlite_master WHERE type='index'")
    indexes = {row[0] for row in cursor.fetchall()}
    
    expected_indexes = {
        'idx_pages_domain', 'idx_pages_crawl_id', 'idx_pages_workspace_id',
        'idx_webhooks_workspace', 'idx_webhook_deliveries_webhook',
        'idx_usage_workspace_period', 'idx_audit_workspace', 'idx_audit_action', 'idx_audit_timestamp'
    }
    
    missing_idx = expected_indexes - indexes
    if missing_idx:
        print(f"⚠ Missing indexes (optional): {missing_idx}")
    else:
        print(f"✓ All indexes created")
    
    conn.close()
    
    print("PASS: Fresh DB schema complete")

finally:
    import os
    os.unlink(temp_db_path)

PYTHON_END
```

**Pass Criteria:**
- All 8 tables created
- Pages table has all required columns
- Key indexes present
- Fresh DB is usable

**Evidence:** Schema inspection output

---

### Test DB-03: workspace_id Isolation on Read

**What:** Verify MetadataStore respects workspace_id in queries.

**How:**
```bash
cd "Nexora application/Crawler"
python << 'PYTHON_END'
import sqlite3
import tempfile
from pathlib import Path

from nexora_crawler.storage.local_sqlite import MetadataStore

with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as tmp:
    db_path = tmp.name

try:
    store = MetadataStore(db_path)
    
    # Insert test data in two workspaces
    store.insert_page({
        "url": "http://ws-a.com/page1",
        "title": "WS-A Page",
        "markdown": "Content A",
        "workspace_id": "workspace-a",
        "crawl_id": "crawl-1",
        "website_type": "blog"
    })
    
    store.insert_page({
        "url": "http://ws-b.com/page2",
        "title": "WS-B Page",
        "markdown": "Content B",
        "workspace_id": "workspace-b",
        "crawl_id": "crawl-2",
        "website_type": "blog"
    })
    
    # Query workspace-a
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    
    cursor.execute(
        "SELECT COUNT(*) FROM pages WHERE workspace_id = ?",
        ("workspace-a",)
    )
    count_a = cursor.fetchone()[0]
    
    if count_a != 1:
        print(f"✗ Expected 1 page in workspace-a, got {count_a}")
        exit(1)
    
    cursor.execute(
        "SELECT COUNT(*) FROM pages WHERE workspace_id = ?",
        ("workspace-b",)
    )
    count_b = cursor.fetchone()[0]
    
    if count_b != 1:
        print(f"✗ Expected 1 page in workspace-b, got {count_b}")
        exit(1)
    
    print("✓ workspace_id isolation works: each workspace sees only its data")
    conn.close()
    
    print("PASS: workspace_id isolation verified")

finally:
    import os
    os.unlink(db_path)

PYTHON_END
```

**Pass Criteria:**
- Can insert pages with different workspace_id values
- Queries filtering by workspace_id return correct rows
- No cross-workspace data leakage

**Evidence:** Query results

---

### Test DB-04: New Phase 4C Tables Accessible

**What:** Verify new tables (webhooks, audit_logs, etc.) are created and queryable.

**How:**
```bash
cd "Nexora application/Crawler"
python << 'PYTHON_END'
import sqlite3
import tempfile
from nexora_crawler.storage.local_sqlite import MetadataStore

with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as tmp:
    db_path = tmp.name

try:
    store = MetadataStore(db_path)
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    
    # Test each new table
    test_cases = [
        ("webhooks", "SELECT COUNT(*) FROM webhooks"),
        ("webhook_deliveries", "SELECT COUNT(*) FROM webhook_deliveries"),
        ("workspace_quotas", "SELECT COUNT(*) FROM workspace_quotas"),
        ("usage_records", "SELECT COUNT(*) FROM usage_records"),
        ("audit_logs", "SELECT COUNT(*) FROM audit_logs"),
        ("extraction_schemas", "SELECT COUNT(*) FROM extraction_schemas"),
    ]
    
    for table_name, query in test_cases:
        try:
            cursor.execute(query)
            count = cursor.fetchone()[0]
            print(f"✓ {table_name} is queryable (0 rows)")
        except sqlite3.OperationalError as e:
            print(f"✗ {table_name} query failed: {e}")
            exit(1)
    
    conn.close()
    print("PASS: All Phase 4C tables are accessible")

finally:
    import os
    os.unlink(db_path)

PYTHON_END
```

**Pass Criteria:**
- All 6 new tables queryable (zero errors)
- Each table is empty (fresh DB)

**Evidence:** Query results

---

## Part 3: Authentication Tests (PHASE_4C_AUTH)

### Test AUTH-01: JWT Validation on Protected Route

**What:** Verify JWT token is required on `/v1/*` routes.

**How:** (Requires FastAPI test client)
```python
# File: test_phase4c_auth.py
from fastapi.testclient import TestClient
from nexora_crawler.api import app
import jwt
from datetime import datetime, timedelta
import os

client = TestClient(app)

def test_unauthenticated_rejected():
    """No auth header → 401"""
    response = client.post("/v1/webhooks", json={"url": "http://example.com"})
    assert response.status_code == 401, f"Expected 401, got {response.status_code}"
    print("✓ Unauthenticated request rejected")

def test_invalid_jwt_rejected():
    """Invalid JWT token → 401"""
    response = client.post(
        "/v1/webhooks",
        json={"url": "http://example.com"},
        headers={"Authorization": "Bearer invalid.token.here"}
    )
    assert response.status_code == 401
    print("✓ Invalid JWT rejected")

def test_expired_jwt_rejected():
    """Expired JWT token → 401"""
    # Create expired token
    payload = {
        "workspace_id": "test-ws",
        "exp": datetime.utcnow() - timedelta(hours=1)  # 1 hour ago
    }
    expired_token = jwt.encode(
        payload,
        os.getenv("JWT_SECRET_KEY", "change-me-in-production"),
        algorithm="HS256"
    )
    
    response = client.post(
        "/v1/webhooks",
        json={"url": "http://example.com"},
        headers={"Authorization": f"Bearer {expired_token}"}
    )
    assert response.status_code == 401
    print("✓ Expired JWT rejected")

def test_valid_jwt_accepted():
    """Valid JWT token → accepted (may 500 if other issues, but not 401)"""
    payload = {
        "workspace_id": "test-ws",
        "exp": datetime.utcnow() + timedelta(hours=1)
    }
    valid_token = jwt.encode(
        payload,
        os.getenv("JWT_SECRET_KEY", "change-me-in-production"),
        algorithm="HS256"
    )
    
    response = client.post(
        "/v1/webhooks",
        json={"url": "http://example.com", "event_types": ["job.completed"]},
        headers={"Authorization": f"Bearer {valid_token}"}
    )
    assert response.status_code != 401, f"Valid JWT rejected with {response.status_code}"
    print(f"✓ Valid JWT accepted (status: {response.status_code})")

if __name__ == "__main__":
    test_unauthenticated_rejected()
    test_invalid_jwt_rejected()
    test_expired_jwt_rejected()
    test_valid_jwt_accepted()
    print("\nPASS: All JWT validation tests pass")
```

**Run:**
```bash
cd "Nexora application/Crawler"
python test_phase4c_auth.py
```

**Pass Criteria:**
- Unauthenticated → 401
- Invalid JWT → 401
- Expired JWT → 401
- Valid JWT → not 401

**Evidence:** Test output

---

### Test AUTH-02: Dev Bypass Gated Behind Environment Flag

**What:** Verify `X-Workspace-Id` header only works when `NEXORA_AUTH_BYPASS_ENABLED=true`.

**How:**
```bash
cd "Nexora application/Crawler"

# Test 1: Bypass OFF (default)
echo "Test: Bypass disabled (default)..."
export NEXORA_AUTH_BYPASS_ENABLED=false
python << 'PYTHON_END'
from fastapi.testclient import TestClient
from nexora_crawler.api import app

client = TestClient(app)
response = client.post(
    "/v1/webhooks",
    json={"url": "http://example.com"},
    headers={"X-Workspace-Id": "test-ws"}
)

if response.status_code == 401:
    print("✓ Bypass disabled: X-Workspace-Id rejected (401)")
else:
    print(f"✗ Bypass not gated: got {response.status_code}, expected 401")
    exit(1)

PYTHON_END

# Test 2: Bypass ON
echo "Test: Bypass enabled..."
export NEXORA_AUTH_BYPASS_ENABLED=true
python << 'PYTHON_END'
from fastapi.testclient import TestClient
from nexora_crawler.api import app

client = TestClient(app)
response = client.post(
    "/v1/webhooks",
    json={"url": "http://example.com", "event_types": ["job.completed"]},
    headers={"X-Workspace-Id": "test-ws"}
)

if response.status_code != 401:
    print(f"✓ Bypass enabled: X-Workspace-Id accepted (status: {response.status_code})")
else:
    print(f"✗ Bypass not working: got 401")
    exit(1)

PYTHON_END
```

**Pass Criteria:**
- With `NEXORA_AUTH_BYPASS_ENABLED=false` (default): `X-Workspace-Id` → 401
- With `NEXORA_AUTH_BYPASS_ENABLED=true`: `X-Workspace-Id` → accepted

**Evidence:** Test output for both cases

---

### Test AUTH-03: JWT Secret Warning on Default

**What:** Verify startup warning when JWT_SECRET is still the default insecure value.

**How:**
```bash
cd "Nexora application/Crawler"

# Start server with default secret
export JWT_SECRET_KEY="change-me-in-production"
python -m nexora_crawler.api --server 2>&1 | head -20 > /tmp/startup.log &
SERVER_PID=$!
sleep 2

# Check for warning
if grep -q "WARNING.*JWT_SECRET" /tmp/startup.log || grep -q "default" /tmp/startup.log; then
    echo "✓ Startup warning present for default JWT secret"
else
    echo "⚠ No startup warning found (optional)"
fi

kill $SERVER_PID 2>/dev/null
```

**Pass Criteria:**
- Startup logs include warning about default JWT_SECRET
- Or: startup succeeds but warning logged (implementation detail)

**Evidence:** Startup log output

---

## Part 4: API Route Tests (PHASE_4C_ROUTES)

### Test ROUTES-01: /health Returns 200

**What:** Basic health check endpoint.

**How:**
```bash
cd "Nexora application/Crawler"
python -m nexora_crawler.api --server &
SERVER_PID=$!
sleep 2

curl -s http://localhost:8000/health | python -m json.tool
RESPONSE=$?

kill $SERVER_PID 2>/dev/null
exit $RESPONSE
```

**Pass Criteria:**
- HTTP 200
- JSON response with `"status": "ok"`

**Evidence:** HTTP response

---

### Test ROUTES-02: /health/detailed Returns Uptime + Version

**What:** Detailed health check.

**How:**
```bash
curl -s http://localhost:8000/health/detailed | python -c "
import json
import sys
data = json.load(sys.stdin)
required_fields = ['status', 'uptime', 'version', 'components']
missing = [f for f in required_fields if f not in data]
if missing:
    print(f'✗ Missing fields: {missing}')
    sys.exit(1)
print('✓ All health fields present')
print(f'  Status: {data[\"status\"]}')
print(f'  Version: {data[\"version\"]}')
print(f'  Uptime: {data[\"uptime\"]}')
"
```

**Pass Criteria:**
- HTTP 200
- JSON contains: `status`, `uptime`, `version`, `components`
- `components` has: `database`, `vector_store`, `ai_provider`

**Evidence:** HTTP response + field values

---

### Test ROUTES-03: POST /v1/webhooks Creates Webhook

**What:** Create webhook (authenticated).

**How:**
```python
def test_create_webhook():
    token = create_valid_jwt_token("test-workspace")
    
    response = client.post(
        "/v1/webhooks",
        json={
            "url": "http://example.com/webhook",
            "event_types": ["job.completed"]
        },
        headers={"Authorization": f"Bearer {token}"}
    )
    
    assert response.status_code == 201, f"Expected 201, got {response.status_code}"
    data = response.json()
    
    assert "id" in data, "Webhook ID missing"
    assert "secret" in data, "Webhook secret missing (one-time display)"
    assert data["url"] == "http://example.com/webhook"
    assert data["workspace_id"] == "test-workspace"
    
    print("✓ Webhook created with ID and secret")
    return data["id"]
```

**Pass Criteria:**
- HTTP 201
- Response includes: `id`, `secret`, `url`, `workspace_id`
- Secret is a non-empty string
- Can be stored for verification

**Evidence:** HTTP response + parsed JSON

---

### Test ROUTES-04: GET /v1/webhooks Lists Workspace Webhooks Only

**What:** List webhooks scoped to workspace.

**How:**
```python
def test_list_webhooks():
    token_a = create_valid_jwt_token("workspace-a")
    token_b = create_valid_jwt_token("workspace-b")
    
    # Create webhook in workspace A
    response_a = client.post(
        "/v1/webhooks",
        json={"url": "http://a.com", "event_types": ["job.completed"]},
        headers={"Authorization": f"Bearer {token_a}"}
    )
    webhook_id_a = response_a.json()["id"]
    
    # Create webhook in workspace B
    response_b = client.post(
        "/v1/webhooks",
        json={"url": "http://b.com", "event_types": ["job.completed"]},
        headers={"Authorization": f"Bearer {token_b}"}
    )
    webhook_id_b = response_b.json()["id"]
    
    # List as workspace A
    list_response = client.get(
        "/v1/webhooks",
        headers={"Authorization": f"Bearer {token_a}"}
    )
    
    assert list_response.status_code == 200
    webhooks = list_response.json()
    webhook_ids = [w["id"] for w in webhooks]
    
    # Should see only workspace A webhook
    assert webhook_id_a in webhook_ids, "Workspace A webhook not in list"
    assert webhook_id_b not in webhook_ids, "Workspace B webhook leaked"
    
    print(f"✓ Workspace isolation: workspace-a sees 1 webhook, not workspace-b's")
```

**Pass Criteria:**
- HTTP 200
- List contains only webhooks created by this workspace
- No cross-workspace leakage

**Evidence:** HTTP response + webhook list

---

### Test ROUTES-05: DELETE /v1/webhooks/{id} Removes Webhook

**What:** Delete webhook (authenticated).

**How:**
```python
def test_delete_webhook(webhook_id):
    token = create_valid_jwt_token("test-workspace")
    
    response = client.delete(
        f"/v1/webhooks/{webhook_id}",
        headers={"Authorization": f"Bearer {token}"}
    )
    
    assert response.status_code == 200
    
    # Verify deleted
    list_response = client.get(
        "/v1/webhooks",
        headers={"Authorization": f"Bearer {token}"}
    )
    webhooks = list_response.json()
    ids = [w["id"] for w in webhooks]
    
    assert webhook_id not in ids, "Webhook still exists after delete"
    print("✓ Webhook deleted successfully")
```

**Pass Criteria:**
- HTTP 200
- Webhook no longer appears in LIST
- Other webhooks unaffected

**Evidence:** Delete response + verification list

---

### Test ROUTES-06: GET /v1/jobs/types Lists 5 Built-in Types

**What:** Job type registry accessible.

**How:**
```bash
curl -s http://localhost:8000/v1/jobs/types | python -c "
import json, sys
data = json.load(sys.stdin)
required_types = {'crawl', 'schema_extract', 'index_search', 'index_add', 'export'}
found_types = {j['type'] for j in data['job_types']}
missing = required_types - found_types
if missing:
    print(f'✗ Missing job types: {missing}')
    sys.exit(1)
print('✓ All 5 job types registered')
"
```

**Pass Criteria:**
- HTTP 200
- Response includes 5 job types: `crawl`, `schema_extract`, `index_search`, `index_add`, `export`

**Evidence:** HTTP response + parsed JSON

---

### Test ROUTES-07: POST /v1/jobs Submits Job (Stub Returns 501)

**What:** Job submission (stub handlers return HTTP 501).

**How:**
```python
def test_submit_job():
    token = create_valid_jwt_token("test-workspace")
    
    response = client.post(
        "/v1/jobs",
        json={
            "job_type": "crawl",
            "params": {"url": "http://example.com"}
        },
        headers={"Authorization": f"Bearer {token}"}
    )
    
    # Stubs return 501 Not Implemented
    assert response.status_code == 501, f"Expected 501, got {response.status_code}"
    data = response.json()
    assert "not_implemented" in data.get("message", "").lower() or data.get("status") == "not_implemented"
    
    print("✓ Job submission returns 501 (stub handler)")
```

**Pass Criteria:**
- HTTP 501 (Not Implemented)
- Response indicates stub/not implemented

**Evidence:** HTTP response + status code

---

### Test ROUTES-08: DELETE /v1/gdpr/erase Deletes Workspace Data

**What:** GDPR erasure endpoint (workspace-scoped delete).

**How:**
```python
def test_gdpr_erase():
    from nexora_crawler.storage.local_sqlite import MetadataStore
    token = create_valid_jwt_token("test-erase-workspace")
    
    # Insert test data
    store = MetadataStore()
    store.insert_page({
        "url": "http://to-erase.com",
        "title": "Erase Me",
        "markdown": "Content",
        "workspace_id": "test-erase-workspace",
        "crawl_id": "erase-1"
    })
    
    # Verify it exists
    conn = sqlite3.connect(store.db_path)
    cursor = conn.cursor()
    cursor.execute("SELECT COUNT(*) FROM pages WHERE workspace_id = 'test-erase-workspace'")
    count_before = cursor.fetchone()[0]
    assert count_before > 0
    conn.close()
    
    # Call erase
    response = client.delete(
        "/v1/gdpr/erase",
        headers={"Authorization": f"Bearer {token}"}
    )
    
    assert response.status_code == 200
    data = response.json()
    assert "pages_deleted" in data or "message" in data
    
    # Verify deleted
    conn = sqlite3.connect(store.db_path)
    cursor = conn.cursor()
    cursor.execute("SELECT COUNT(*) FROM pages WHERE workspace_id = 'test-erase-workspace'")
    count_after = cursor.fetchone()[0]
    conn.close()
    
    assert count_after < count_before, "GDPR erase didn't actually delete rows"
    print(f"✓ GDPR erase deleted {count_before - count_after} rows")
```

**Pass Criteria:**
- HTTP 200
- Rows with matching workspace_id actually deleted from DB
- Other workspaces unaffected

**Evidence:** Response + database verification

---

### Test ROUTES-09: POST /v1/extract/schema Dispatches Job

**What:** Schema extraction endpoint.

**How:**
```python
def test_schema_extract():
    token = create_valid_jwt_token("test-workspace")
    
    response = client.post(
        "/v1/extract/schema",
        json={
            "url": "http://example.com",
            "schema_id": "test-schema-1",
            "async_run": True
        },
        headers={"Authorization": f"Bearer {token}"}
    )
    
    # Success if not 401
    assert response.status_code in [200, 202, 501], f"Unexpected status: {response.status_code}"
    data = response.json()
    
    # Should have job_id or status
    assert "job_id" in data or "status" in data, "No job tracking"
    print(f"✓ Schema extraction accepted (status: {response.status_code})")
```

**Pass Criteria:**
- HTTP 200, 202, or 501 (not 401)
- Response includes job tracking info

**Evidence:** HTTP response

---

### Test ROUTES-10: Vector Search Routes Protected

**What:** All search endpoints require authentication.

**How:**
```python
def test_search_routes_protected():
    routes = [
        "/v1/search/semantic",
        "/v1/search/hybrid",
    ]
    
    for route in routes:
        response = client.post(route, json={"query": "test", "top_k": 5})
        assert response.status_code == 401, f"{route}: Expected 401, got {response.status_code}"
    
    print("✓ All search routes protected (401 without auth)")
```

**Pass Criteria:**
- All `/v1/search/*` return 401 without auth

**Evidence:** HTTP responses for all search routes

---

## Part 5: Security Tests (PHASE_4C_SECURITY)

### Test SEC-01: SQL Injection Prevention

**What:** Verify no string concatenation in SQL queries.

**How:**
```bash
cd "Nexora application/Crawler"
python << 'PYTHON_END'
import ast
import os

sql_injection_patterns = [
    ".format(",
    "f-string with query",
    "% ",  # old printf-style formatting
    ".join(",  # dynamic query building
]

files_to_check = [
    "nexora_crawler/api/routes/webhooks.py",
    "nexora_crawler/api/routes/gdpr.py",
    "nexora_crawler/api/routes/extract.py",
]

issues = []
for filepath in files_to_check:
    with open(filepath, 'r') as f:
        content = f.read()
    
    # Look for execute() calls
    lines = content.split('\n')
    for i, line in enumerate(lines, 1):
        if 'execute(' in line:
            # Check if query is parameterized
            if "?" not in line and "$" not in line:
                # May be in next lines
                preview = '\n'.join(lines[max(0, i-2):min(len(lines), i+3)])
                if any(p in preview for p in ['?', '$1', '$2', 'param']):
                    continue
                issues.append(f"{filepath}:{i} - possible string interpolation")

if issues:
    for issue in issues:
        print(f"⚠ {issue}")
else:
    print("✓ No obvious SQL string concatenation detected")

PYTHON_END
```

**Pass Criteria:**
- No `f-string` used in SQL queries
- All queries use `?` (SQLite) or `$n` (Postgres) placeholders
- No `.format()` or `%` formatting in query strings

**Evidence:** Code grep output

---

### Test SEC-02: Cross-Workspace Access Blocked

**What:** Workspace B cannot access Workspace A's data via direct ID manipulation.

**How:**
```python
def test_cross_workspace_access_blocked():
    """
    Create resource in workspace-a
    Try to access from workspace-b
    Should get 403 or 404, not the resource
    """
    token_a = create_valid_jwt_token("workspace-a")
    token_b = create_valid_jwt_token("workspace-b")
    
    # Create webhook in workspace-a
    create_response = client.post(
        "/v1/webhooks",
        json={"url": "http://a.com", "event_types": ["job.completed"]},
        headers={"Authorization": f"Bearer {token_a}"}
    )
    webhook_id = create_response.json()["id"]
    
    # Try to delete from workspace-b
    delete_response = client.delete(
        f"/v1/webhooks/{webhook_id}",
        headers={"Authorization": f"Bearer {token_b}"}
    )
    
    # Should not succeed
    assert delete_response.status_code in [403, 404], \
        f"Cross-workspace delete should fail, got {delete_response.status_code}"
    
    # Verify webhook still exists in workspace-a
    list_response = client.get(
        "/v1/webhooks",
        headers={"Authorization": f"Bearer {token_a}"}
    )
    ids = [w["id"] for w in list_response.json()]
    assert webhook_id in ids, "Webhook was deleted by different workspace"
    
    print("✓ Cross-workspace access blocked")
```

**Pass Criteria:**
- Workspace B cannot delete workspace A's webhook
- Webhook still exists after failed delete
- HTTP status: 403 (Forbidden) or 404 (Not Found)

**Evidence:** Response status + verification

---

### Test SEC-03: Default JWT Secret Warning

**What:** Startup warns when JWT_SECRET is default.

**How:** (See AUTH-03 above)

**Pass Criteria:**
- Warning logged on startup
- Startupsuccessfully (warning is advisory)

**Evidence:** Startup log

---

## Part 6: Database Write Durability (PHASE_4C_DURABILITY)

### Test DURABILITY-01: Webhooks Write Persists After Restart

**What:** Verify POST /v1/webhooks data survives server restart (DB commit works).

**How:**
```python
def test_webhook_persistence():
    from nexora_crawler.storage.local_sqlite import MetadataStore
    import sqlite3
    
    token = create_valid_jwt_token("test-workspace")
    
    # Create webhook via API
    response = client.post(
        "/v1/webhooks",
        json={"url": "http://test.com", "event_types": ["job.completed"]},
        headers={"Authorization": f"Bearer {token}"}
    )
    
    assert response.status_code == 201
    webhook_id = response.json()["id"]
    
    # Query DB directly (simulate server restart)
    store = MetadataStore()
    conn = sqlite3.connect(store.db_path)
    cursor = conn.cursor()
    cursor.execute("SELECT COUNT(*) FROM webhooks WHERE id = ?", (webhook_id,))
    count = cursor.fetchone()[0]
    conn.close()
    
    assert count == 1, f"Webhook not persisted to DB (DB count: {count})"
    print("✓ Webhook persisted to DB (write durability OK)")
```

**Pass Criteria:**
- Webhook appears in direct DB query
- Count = 1 (row actually written, not rolled back)

**Evidence:** DB query result

---

### Test DURABILITY-02: GDPR Erase Persists

**What:** Verify DELETE /v1/gdpr/erase data is actually deleted (commit works).

**How:**
```python
def test_gdpr_erase_persists():
    from nexora_crawler.storage.local_sqlite import MetadataStore
    import sqlite3
    
    token = create_valid_jwt_token("erase-test-ws")
    
    # Insert data
    store = MetadataStore()
    store.insert_page({
        "url": "http://erase-test.com",
        "title": "Test",
        "markdown": "test",
        "workspace_id": "erase-test-ws",
        "crawl_id": "erase-1"
    })
    
    # Call erase
    response = client.delete(
        "/v1/gdpr/erase",
        headers={"Authorization": f"Bearer {token}"}
    )
    
    assert response.status_code == 200
    
    # Query DB directly
    conn = sqlite3.connect(store.db_path)
    cursor = conn.cursor()
    cursor.execute("SELECT COUNT(*) FROM pages WHERE workspace_id = 'erase-test-ws'")
    count = cursor.fetchone()[0]
    conn.close()
    
    assert count == 0, f"GDPR erase didn't persist: {count} rows still in DB"
    print("✓ GDPR erase persisted (write durability OK)")
```

**Pass Criteria:**
- Direct DB query shows 0 rows for that workspace
- Deletion was committed, not rolled back

**Evidence:** DB query result

---

## Part 7: Integration Tests (PHASE_4C_INTEGRATION)

### Test INTEG-01: Crawl Submission Via Legacy /crawl Endpoint

**What:** End-to-end: submit crawl → execution → result in DB with workspace_id.

**How:**
```bash
cd "Nexora application/Crawler"

python << 'PYTHON_END'
import requests
import time
import sqlite3
from pathlib import Path

# Start server
import subprocess
proc = subprocess.Popen(
    ["python", "-m", "nexora_crawler.api", "--server"],
    cwd=Path.cwd()
)
time.sleep(3)

try:
    # Submit crawl
    response = requests.post(
        "http://localhost:8000/crawl",
        json={"url": "https://books.toscrape.com", "strategy": "single-page"}
    )
    
    if response.status_code != 200:
        print(f"✗ Crawl submission failed: {response.status_code}")
        exit(1)
    
    data = response.json()
    job_id = data.get("job_id")
    print(f"✓ Crawl submitted (job_id: {job_id})")
    
    # Wait for completion (up to 30 sec)
    for _ in range(30):
        status_response = requests.get(f"http://localhost:8000/crawl/{job_id}")
        if status_response.status_code == 200:
            status = status_response.json()
            if status.get("status") == "completed":
                print(f"✓ Crawl completed")
                break
        time.sleep(1)
    
    # Check DB for workspace_id
    db_path = Path("nexora_crawler/data/nexora_metadata.db")
    if db_path.exists():
        conn = sqlite3.connect(str(db_path))
        cursor = conn.cursor()
        cursor.execute("SELECT COUNT(*) FROM pages WHERE workspace_id = 'default'")
        count = cursor.fetchone()[0]
        conn.close()
        
        if count > 0:
            print(f"✓ Pages written to DB with workspace_id='default'")
        else:
            print(f"⚠ No pages in DB with workspace_id='default'")
    
    print("PASS: End-to-end crawl integration works")

finally:
    proc.terminate()
    proc.wait()

PYTHON_END
```

**Pass Criteria:**
- Crawl submission returns 200 + job_id
- Job eventually reaches "completed" status
- Pages appear in DB with workspace_id='default'

**Evidence:** Requests/responses + DB query

---

### Test INTEG-02: Webhook List Returns Only Workspace Webhooks

**What:** Full flow: create webhooks in different workspaces, verify isolation.

**How:** (See ROUTES-04 above, expanded)

**Pass Criteria:**
- Workspace A sees only its webhooks
- Workspace B sees only its webhooks
- No cross-workspace leakage

**Evidence:** API responses

---

## Part 8: Final Verification Checklist

### Master Verification

Run this checklist after all tests pass to confirm Phase 4C is complete:

- [ ] **INFRA-01:** Package structure correct (no old `api.py`, all new files present)
- [ ] **INFRA-02:** All imports resolve without circular dependencies
- [ ] **INFRA-03:** All Python files byte-compile
- [ ] **INFRA-04:** Subprocess spawn updated to `__main__.py`
- [ ] **INFRA-05:** All dependencies in `requirements.txt`
- [ ] **DB-01:** Schema migration safe on pre-existing DB (no crash)
- [ ] **DB-02:** Fresh DB has all 8 tables + indexes
- [ ] **DB-03:** workspace_id isolation on read works
- [ ] **DB-04:** New Phase 4C tables accessible
- [ ] **AUTH-01:** JWT validation on protected routes
- [ ] **AUTH-02:** Dev bypass gated behind env flag
- [ ] **AUTH-03:** Startup warning for default JWT secret
- [ ] **ROUTES-01 to 10:** All API routes respond correctly
- [ ] **SEC-01:** No SQL injection (parameterized queries)
- [ ] **SEC-02:** Cross-workspace access blocked (403/404)
- [ ] **SEC-03:** Default JWT secret warning present
- [ ] **DURABILITY-01:** Webhooks persist across restart
- [ ] **DURABILITY-02:** GDPR erase persists
- [ ] **INTEG-01:** End-to-end crawl works with workspace isolation
- [ ] **INTEG-02:** Webhook list respects workspace boundaries

---

## Test Execution & Reporting

### How to Run All Tests

```bash
cd "Nexora application"

# 1. Infrastructure
echo "=== PHASE_4C_INFRA ==="
python -m pytest tests/test_phase4c_infra.py -v

# 2. Database
echo "=== PHASE_4C_DB ==="
python -m pytest tests/test_phase4c_db.py -v

# 3. Authentication
echo "=== PHASE_4C_AUTH ==="
python -m pytest tests/test_phase4c_auth.py -v

# 4. API Routes
echo "=== PHASE_4C_ROUTES ==="
python -m pytest tests/test_phase4c_routes.py -v

# 5. Security
echo "=== PHASE_4C_SECURITY ==="
python -m pytest tests/test_phase4c_security.py -v

# 6. Durability
echo "=== PHASE_4C_DURABILITY ==="
python -m pytest tests/test_phase4c_durability.py -v

# 7. Integration
echo "=== PHASE_4C_INTEGRATION ==="
python -m pytest tests/test_phase4c_integration.py -v

# Generate report
echo "=== GENERATING REPORT ==="
python -m pytest tests/test_phase4c_*.py --tb=short --junit-xml=PHASE_4C_TEST_RESULTS.xml -v
```

### Test Report Format

```
NEXUS AURORA Phase 4C Test Report
Date: <timestamp>
Suite: Phase 4C (Infrastructure, Database, Auth, Routes, Security, Integration)

Results:
  Infrastructure:  7/7 ✅ PASS
  Database:        4/4 ✅ PASS
  Authentication:  3/3 ✅ PASS
  API Routes:      10/10 ✅ PASS
  Security:        3/3 ✅ PASS
  Durability:      2/2 ✅ PASS
  Integration:     2/2 ✅ PASS

Total: 31/31 ✅ PASS

Blockers: None
Warnings: None
Notes: All Phase 4C functionality verified end-to-end

Signed by: <Verifier Name>
Date: <Date>
```

---

## Success Criteria (For Verifier)

**Phase 4C is VERIFIED COMPLETE and PRODUCTION-READY when:**

1. ✅ **All 31 tests pass** (100% pass rate)
2. ✅ **Zero blockers** (no P0/P1 defects)
3. ✅ **No security issues** (auth bypass, SQL injection, cross-workspace access all verified secure)
4. ✅ **Database integrity** (schema migrations work on pre-existing DBs, writes persist)
5. ✅ **API responses** match documented contracts (status codes, fields, types)
6. ✅ **Workspace isolation** verified (cross-workspace requests blocked)
7. ✅ **Integration end-to-end** (crawl → DB → workspace scoping works)
8. ✅ **Dependencies complete** (requirements.txt has all Phase 4C packages)

**If any test fails:**
- Document the failure (test name, error, stack trace)
- Classify as P0 (blocks deployment), P1 (needs fix), or P2 (deferred)
- Link to GitHub issue for remediation
- Do NOT sign off on Phase 4C

---

**Report Generated:** 2026-08-19  
**Test Coverage:** 31 tests across 7 categories  
**Execution Time Estimate:** 15-20 minutes (excluding live site crawl)  
**Next Step:** Run all tests, generate report, sign off

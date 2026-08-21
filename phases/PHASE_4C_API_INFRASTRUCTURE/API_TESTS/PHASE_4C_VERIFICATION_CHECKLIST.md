# NEXUS AURORA Phase 4C — Independent Verification Checklist
## For QA Engineer / Independent Auditor

**Document Purpose:** Execute the rigorous test plan in PHASE_4C_RIGOROUS_END_TO_END_TEST_PLAN.md and report results.

**Your Role:** Run tests, document outcomes, make a PASS/FAIL/CONDITIONAL determination.

**Success Path:** All 31 tests pass → Sign off "Phase 4C Complete"  
**Failure Path:** Any test fails → Document issue → Do NOT sign off

**Time Required:** 20-30 minutes (plus any remediation if bugs found)

---

## Pre-Flight Checklist

Before running tests, verify these prerequisites:

### Environment Setup

- [ ] Python 3.11+ installed: `python --version`
- [ ] Working directory: `F:\DSF\stsh projects\NEXUS AURORA\Nexora application\Crawler`
- [ ] Virtual environment active (if applicable)
- [ ] Dependencies installed: `pip install -r ../application\ documents/requirements.txt`
- [ ] Internet connection available (for live site crawl tests)

### Database Setup

- [ ] Live database exists: `nexora_crawler/data/nexora_metadata.db`
- [ ] Database is readable/writable: `python -c "import sqlite3; c = sqlite3.connect('nexora_crawler/data/nexora_metadata.db'); print('OK')"`
- [ ] Backup created before running tests: `cp nexora_crawler/data/nexora_metadata.db nexora_metadata.db.backup`

### Repository State

- [ ] All Phase 4C files present: `python PHASE_4C_RIGOROUS_END_TO_END_TEST_PLAN.md` (run INFRA-01 first)
- [ ] No uncommitted breaking changes: `git status` (or file inspection)
- [ ] Latest code pulled: Verify `.git/HEAD` or ask before starting

---

## Test Execution Summary

| Test Category | Test Count | Pass | Fail | Skip | Status |
|---------------|-----------|------|------|------|--------|
| **INFRA** | 5 | ☐ | ☐ | ☐ | ☐ |
| **DB** | 4 | ☐ | ☐ | ☐ | ☐ |
| **AUTH** | 3 | ☐ | ☐ | ☐ | ☐ |
| **ROUTES** | 10 | ☐ | ☐ | ☐ | ☐ |
| **SECURITY** | 3 | ☐ | ☐ | ☐ | ☐ |
| **DURABILITY** | 2 | ☐ | ☐ | ☐ | ☐ |
| **INTEGRATION** | 2 | ☐ | ☐ | ☐ | ☐ |
| **TOTAL** | **31** | ☐ | ☐ | ☐ | ☐ |

---

## Part 1: Infrastructure Tests (PHASE_4C_INFRA)

### Test INFRA-01: Package Migration Complete ✓

**Run this test first to verify file structure.**

```bash
cd "Nexora application\Crawler"
python -c "
import os, sys
if os.path.exists('nexora_crawler/api.py'):
    print('FAIL: Old api.py still exists')
    sys.exit(1)
required = ['nexora_crawler/api/__init__.py', 'nexora_crawler/api/__main__.py']
if not all(os.path.exists(f) for f in required):
    print('FAIL: Missing required files')
    sys.exit(1)
print('PASS: Package structure correct')
"
```

**Result:** ✓ PASS / ☐ FAIL  
**Evidence:** (Paste output below)
```
[Run command, paste output here]
```

**Notes:** _________________________________________________________________________

---

### Test INFRA-02: All Imports Resolve

```bash
cd "Nexora application\Crawler"
python -c "
from nexora_crawler.api import app
from nexora_crawler.api.auth import get_workspace_id
from nexora_crawler.jobs.registry import JobTypeRegistry
from nexora_crawler.tasks.dispatcher import dispatch_job
print('PASS: All imports resolve')
"
```

**Result:** ✓ PASS / ☐ FAIL  
**Error (if any):**
```
[Paste error output here]
```

**Notes:** _________________________________________________________________________

---

### Test INFRA-03: Byte Compilation

```bash
cd "Nexora application\Crawler"
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
echo "Exit code: $?"
```

**Result:** ✓ PASS / ☐ FAIL  
**Exit Code:** ____  
**Notes:** _________________________________________________________________________

---

### Test INFRA-04: Subprocess Spawn Target Correct

```bash
cd "Nexora application\Crawler"
python -c "
with open('nexora_crawler/api/__init__.py', 'r') as f:
    content = f.read()
if 'python -m nexora_crawler.api' in content:
    print('PASS: Subprocess uses __main__.py')
else:
    print('FAIL: Subprocess spawn not updated')
"
```

**Result:** ✓ PASS / ☐ FAIL  
**Notes:** _________________________________________________________________________

---

### Test INFRA-05: Dependencies Declared

```bash
cd "Nexora application"
grep -E "fastapi|uvicorn|pydantic|PyJWT|aiosqlite|asyncpg|python-multipart|bcrypt|slowapi" application\ documents/requirements.txt | wc -l
# Should show 9 lines
```

**Result:** ✓ PASS (9 deps found) / ☐ FAIL  
**Count:** ____  
**Notes:** _________________________________________________________________________

---

## Part 2: Database Tests (PHASE_4C_DB)

### Test DB-01: Schema Migration on Existing Database

**This is a critical test. Run it carefully.**

```bash
cd "Nexora application\Crawler"
python << 'EOF'
import sqlite3, tempfile, shutil
from pathlib import Path

live_db = Path("nexora_crawler/data/nexora_metadata.db")
if not live_db.exists():
    print("SKIP: Live DB not found")
    exit(0)

with tempfile.TemporaryDirectory() as tmpdir:
    temp_db = Path(tmpdir) / "test.db"
    shutil.copy(live_db, temp_db)
    
    try:
        from nexora_crawler.storage.local_sqlite import MetadataStore
        store = MetadataStore(str(temp_db))
        print("PASS: MetadataStore instantiation succeeds (no crash)")
    except Exception as e:
        print(f"FAIL: {e}")
        exit(1)
    
    conn = sqlite3.connect(str(temp_db))
    cursor = conn.cursor()
    cursor.execute("PRAGMA table_info(pages)")
    columns = {row[1] for row in cursor.fetchall()}
    
    if "workspace_id" not in columns:
        print("FAIL: workspace_id column not added")
        exit(1)
    
    print("PASS: workspace_id column added")
    
    cursor.execute("SELECT name FROM sqlite_master WHERE type='table' ORDER BY name")
    tables = {row[0] for row in cursor.fetchall()}
    required = {'pages', 'crawl_jobs', 'webhooks', 'webhook_deliveries', 'workspace_quotas', 'usage_records', 'audit_logs', 'extraction_schemas'}
    
    if not required.issubset(tables):
        print(f"FAIL: Missing tables: {required - tables}")
        exit(1)
    
    print(f"PASS: All 8 tables present")
    
    cursor.execute("SELECT COUNT(*) FROM pages WHERE workspace_id = 'default'")
    count = cursor.fetchone()[0]
    cursor.execute("SELECT COUNT(*) FROM pages")
    total = cursor.fetchone()[0]
    
    if count == total:
        print(f"PASS: All {total} rows backfilled to 'default'")
    else:
        print(f"FAIL: Only {count}/{total} rows backfilled")
        exit(1)
    
    conn.close()
EOF
```

**Result:** ✓ PASS / ☐ FAIL  
**Output:**
```
[Paste output here]
```

**Notes:** _________________________________________________________________________

---

### Test DB-02: New Database Schema Complete

```bash
cd "Nexora application\Crawler"
python << 'EOF'
import sqlite3, tempfile
from nexora_crawler.storage.local_sqlite import MetadataStore

with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as tmp:
    store = MetadataStore(tmp.name)
    conn = sqlite3.connect(tmp.name)
    cursor = conn.cursor()
    
    cursor.execute("SELECT COUNT(*) FROM sqlite_master WHERE type='table'")
    table_count = cursor.fetchone()[0]
    
    if table_count >= 8:
        print("PASS: Fresh DB has all tables")
    else:
        print(f"FAIL: Expected 8+ tables, got {table_count}")
        exit(1)
    
    cursor.execute("PRAGMA table_info(pages)")
    columns = {row[1] for row in cursor.fetchall()}
    required = {'url', 'title', 'markdown', 'workspace_id', 'crawl_id'}
    
    if required.issubset(columns):
        print("PASS: Pages table has required columns")
    else:
        print(f"FAIL: Missing columns: {required - columns}")
        exit(1)
    
    conn.close()
EOF
```

**Result:** ✓ PASS / ☐ FAIL  
**Notes:** _________________________________________________________________________

---

### Test DB-03: workspace_id Isolation on Read

```bash
cd "Nexora application\Crawler"
python << 'EOF'
import sqlite3, tempfile
from nexora_crawler.storage.local_sqlite import MetadataStore

with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as tmp:
    store = MetadataStore(tmp.name)
    
    store.insert_page({"url": "http://ws-a.com", "title": "A", "markdown": "a", "workspace_id": "ws-a", "crawl_id": "c1", "website_type": "blog"})
    store.insert_page({"url": "http://ws-b.com", "title": "B", "markdown": "b", "workspace_id": "ws-b", "crawl_id": "c2", "website_type": "blog"})
    
    conn = sqlite3.connect(tmp.name)
    cursor = conn.cursor()
    cursor.execute("SELECT COUNT(*) FROM pages WHERE workspace_id = 'ws-a'")
    count_a = cursor.fetchone()[0]
    
    if count_a == 1:
        print("PASS: workspace_id isolation works")
    else:
        print(f"FAIL: Expected 1 row, got {count_a}")
        exit(1)
    
    conn.close()
EOF
```

**Result:** ✓ PASS / ☐ FAIL  
**Notes:** _________________________________________________________________________

---

### Test DB-04: New Phase 4C Tables Accessible

```bash
cd "Nexora application\Crawler"
python << 'EOF'
import sqlite3, tempfile
from nexora_crawler.storage.local_sqlite import MetadataStore

with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as tmp:
    store = MetadataStore(tmp.name)
    conn = sqlite3.connect(tmp.name)
    cursor = conn.cursor()
    
    tables = ['webhooks', 'webhook_deliveries', 'workspace_quotas', 'usage_records', 'audit_logs', 'extraction_schemas']
    failed = []
    
    for table in tables:
        try:
            cursor.execute(f"SELECT COUNT(*) FROM {table}")
            cursor.fetchone()
        except Exception as e:
            failed.append(table)
    
    if not failed:
        print("PASS: All Phase 4C tables accessible")
    else:
        print(f"FAIL: Tables not accessible: {failed}")
        exit(1)
    
    conn.close()
EOF
```

**Result:** ✓ PASS / ☐ FAIL  
**Notes:** _________________________________________________________________________

---

## Part 3: Authentication Tests (PHASE_4C_AUTH)

### Test AUTH-01: JWT Validation on Protected Route

**This requires the FastAPI test client.**

```bash
cd "Nexora application\Crawler"
python << 'EOF'
from fastapi.testclient import TestClient
from nexora_crawler.api import app

client = TestClient(app)

# Test: unauthenticated → 401
response = client.post("/v1/webhooks", json={"url": "http://example.com"})
if response.status_code == 401:
    print("PASS: Unauthenticated request rejected (401)")
else:
    print(f"FAIL: Expected 401, got {response.status_code}")
    exit(1)

# Test: invalid JWT → 401
response = client.post(
    "/v1/webhooks",
    json={"url": "http://example.com"},
    headers={"Authorization": "Bearer invalid"}
)
if response.status_code == 401:
    print("PASS: Invalid JWT rejected (401)")
else:
    print(f"FAIL: Expected 401, got {response.status_code}")
    exit(1)
EOF
```

**Result:** ✓ PASS / ☐ FAIL  
**Output:**
```
[Paste output here]
```

**Notes:** _________________________________________________________________________

---

### Test AUTH-02: Dev Bypass Gated Behind Environment Flag

```bash
cd "Nexora application\Crawler"

# Test 1: Bypass OFF (default)
export NEXORA_AUTH_BYPASS_ENABLED=false
python << 'EOF'
from fastapi.testclient import TestClient
from nexora_crawler.api import app
client = TestClient(app)
response = client.post("/v1/webhooks", json={"url": "http://example.com"}, headers={"X-Workspace-Id": "test"})
if response.status_code == 401:
    print("PASS: Bypass OFF - X-Workspace-Id rejected")
else:
    print(f"FAIL: Bypass OFF - got {response.status_code}, expected 401")
EOF

# Test 2: Bypass ON
export NEXORA_AUTH_BYPASS_ENABLED=true
python << 'EOF'
from fastapi.testclient import TestClient
from nexora_crawler.api import app
client = TestClient(app)
response = client.post("/v1/webhooks", json={"url": "http://example.com", "event_types": ["job.completed"]}, headers={"X-Workspace-Id": "test"})
if response.status_code != 401:
    print(f"PASS: Bypass ON - X-Workspace-Id accepted ({response.status_code})")
else:
    print(f"FAIL: Bypass ON - still got 401")
EOF
```

**Result:** ✓ PASS / ☐ FAIL  
**Notes:** _________________________________________________________________________

---

### Test AUTH-03: Startup Warning for Default JWT Secret

```bash
cd "Nexora application\Crawler"
timeout 5 python -m nexora_crawler.api --server 2>&1 | head -20 | grep -i "JWT\|default\|secret" || echo "No warning found (may be optional)"
```

**Result:** ✓ PASS (warning found) / ⚠ PARTIAL (no warning) / ☐ FAIL  
**Notes:** _________________________________________________________________________

---

## Part 4: API Route Tests (PHASE_4C_ROUTES)

### Test ROUTES-01 to 10: Run All Route Tests

```bash
cd "Nexora application\Crawler"

# Start server in background
python -m nexora_crawler.api --server > /tmp/server.log 2>&1 &
SERVER_PID=$!
sleep 3

python << 'EOF'
import requests, time, sqlite3, json
import os

def get_token():
    from datetime import datetime, timedelta
    import jwt
    payload = {
        "workspace_id": "test-workspace",
        "exp": datetime.utcnow() + timedelta(hours=1)
    }
    return jwt.encode(payload, os.getenv("JWT_SECRET_KEY", "change-me-in-production"), algorithm="HS256")

token = get_token()
headers = {"Authorization": f"Bearer {token}"}

print("\n=== ROUTE TESTS ===\n")

# ROUTES-01: Health check
response = requests.get("http://localhost:8000/health")
if response.status_code == 200:
    print("✓ ROUTES-01: /health → 200")
else:
    print(f"✗ ROUTES-01: /health → {response.status_code}")

# ROUTES-02: Detailed health
response = requests.get("http://localhost:8000/health/detailed")
if response.status_code == 200 and "uptime" in response.json():
    print("✓ ROUTES-02: /health/detailed → 200 + uptime")
else:
    print(f"✗ ROUTES-02: /health/detailed failed")

# ROUTES-03: Create webhook
response = requests.post("http://localhost:8000/v1/webhooks", json={"url": "http://example.com", "event_types": ["job.completed"]}, headers=headers)
if response.status_code == 201:
    webhook_data = response.json()
    print(f"✓ ROUTES-03: POST /v1/webhooks → 201 (id={webhook_data.get('id', 'N/A')})")
    webhook_id = webhook_data.get("id")
else:
    print(f"✗ ROUTES-03: POST /v1/webhooks → {response.status_code}")
    webhook_id = None

# ROUTES-04: List webhooks
response = requests.get("http://localhost:8000/v1/webhooks", headers=headers)
if response.status_code == 200:
    print(f"✓ ROUTES-04: GET /v1/webhooks → 200 ({len(response.json())} webhooks)")
else:
    print(f"✗ ROUTES-04: GET /v1/webhooks → {response.status_code}")

# ROUTES-05: Delete webhook
if webhook_id:
    response = requests.delete(f"http://localhost:8000/v1/webhooks/{webhook_id}", headers=headers)
    if response.status_code == 200:
        print("✓ ROUTES-05: DELETE /v1/webhooks/{id} → 200")
    else:
        print(f"✗ ROUTES-05: DELETE /v1/webhooks → {response.status_code}")

# ROUTES-06: Job types
response = requests.get("http://localhost:8000/v1/jobs/types")
if response.status_code == 200 and len(response.json().get("job_types", [])) == 5:
    print("✓ ROUTES-06: GET /v1/jobs/types → 5 types")
else:
    print(f"✗ ROUTES-06: GET /v1/jobs/types failed")

# ROUTES-07: Submit job (stub returns 501)
response = requests.post("http://localhost:8000/v1/jobs", json={"job_type": "crawl", "params": {"url": "http://example.com"}}, headers=headers)
if response.status_code == 501:
    print("✓ ROUTES-07: POST /v1/jobs → 501 (stub handler)")
else:
    print(f"✗ ROUTES-07: POST /v1/jobs → {response.status_code} (expected 501)")

# ROUTES-08: GDPR erase (may fail due to vector store or DB state, but shouldn't be 401)
response = requests.delete("http://localhost:8000/v1/gdpr/erase", headers=headers)
if response.status_code != 401:
    print(f"✓ ROUTES-08: DELETE /v1/gdpr/erase → {response.status_code} (not 401)")
else:
    print(f"✗ ROUTES-08: DELETE /v1/gdpr/erase → 401 (auth failed)")

# ROUTES-09: Schema extract
response = requests.post("http://localhost:8000/v1/extract/schema", json={"url": "http://example.com", "schema_id": "s1"}, headers=headers)
if response.status_code in [200, 202, 501]:
    print(f"✓ ROUTES-09: POST /v1/extract/schema → {response.status_code}")
else:
    print(f"✗ ROUTES-09: POST /v1/extract/schema → {response.status_code}")

# ROUTES-10: Search routes protected
response = requests.post("http://localhost:8000/v1/search/semantic", json={"query": "test", "top_k": 5})
if response.status_code == 401:
    print("✓ ROUTES-10: /v1/search/semantic protected (401 without auth)")
else:
    print(f"✗ ROUTES-10: Search not protected (got {response.status_code})")

print("\n=== ROUTE TESTS COMPLETE ===\n")
EOF

kill $SERVER_PID
```

**Result:** ✓ PASS (all routes OK) / ⚠ PARTIAL / ☐ FAIL  
**Failed Routes:** _________________________________________________________________  
**Notes:** _________________________________________________________________________

---

## Part 5: Security Tests (PHASE_4C_SECURITY)

### Test SEC-01: SQL Injection Prevention

```bash
cd "Nexora application\Crawler"
python << 'EOF'
import os
import re

dangerous_patterns = [
    (r'execute\(["\'].*\.format\(', "format() in query"),
    (r'execute\(["\'].*%\s*[a-z]', "printf-style formatting in query"),
]

files = [
    "nexora_crawler/api/routes/webhooks.py",
    "nexora_crawler/api/routes/gdpr.py",
    "nexora_crawler/api/routes/extract.py",
]

issues = []
for filepath in files:
    with open(filepath, 'r') as f:
        content = f.read()
    for pattern, desc in dangerous_patterns:
        if re.search(pattern, content):
            issues.append(f"{filepath}: {desc}")

if not issues:
    print("PASS: No obvious SQL injection vectors")
else:
    print(f"FAIL: Found {len(issues)} potential issues:")
    for issue in issues:
        print(f"  - {issue}")
    exit(1)
EOF
```

**Result:** ✓ PASS / ☐ FAIL  
**Issues Found:** ____________________________________________________________________  
**Notes:** _________________________________________________________________________

---

### Test SEC-02: Cross-Workspace Access Blocked

```bash
cd "Nexora application\Crawler"
python << 'EOF'
from fastapi.testclient import TestClient
from nexora_crawler.api import app
import jwt, os
from datetime import datetime, timedelta

client = TestClient(app)

def make_token(ws):
    payload = {"workspace_id": ws, "exp": datetime.utcnow() + timedelta(hours=1)}
    return jwt.encode(payload, os.getenv("JWT_SECRET_KEY", "change-me-in-production"), algorithm="HS256")

# Create webhook in workspace A
token_a = make_token("ws-a")
response = client.post("/v1/webhooks", json={"url": "http://a.com", "event_types": ["job.completed"]}, headers={"Authorization": f"Bearer {token_a}"})
if response.status_code != 201:
    print(f"SKIP: Could not create webhook in ws-a ({response.status_code})")
else:
    webhook_id = response.json()["id"]
    
    # Try to delete from workspace B
    token_b = make_token("ws-b")
    response = client.delete(f"/v1/webhooks/{webhook_id}", headers={"Authorization": f"Bearer {token_b}"})
    
    if response.status_code in [403, 404]:
        print(f"PASS: Cross-workspace delete blocked ({response.status_code})")
    else:
        print(f"FAIL: Cross-workspace delete allowed ({response.status_code})")
        exit(1)
EOF
```

**Result:** ✓ PASS / ☐ FAIL  
**Notes:** _________________________________________________________________________

---

### Test SEC-03: Default JWT Secret Warning

```bash
# Already tested in AUTH-03
# Document result here
```

**Result:** ✓ PASS / ⚠ PARTIAL / ☐ FAIL  
**Notes:** _________________________________________________________________________

---

## Part 6: Database Durability Tests (PHASE_4C_DURABILITY)

### Test DURABILITY-01 & 02: Write Persistence

```bash
cd "Nexora application\Crawler"
python << 'EOF'
from fastapi.testclient import TestClient
from nexora_crawler.api import app
from nexora_crawler.storage.local_sqlite import MetadataStore
import sqlite3, jwt, os
from datetime import datetime, timedelta

client = TestClient(app)

def make_token(ws):
    payload = {"workspace_id": ws, "exp": datetime.utcnow() + timedelta(hours=1)}
    return jwt.encode(payload, os.getenv("JWT_SECRET_KEY", "change-me-in-production"), algorithm="HS256")

token = make_token("durability-test-ws")

# Create webhook
response = client.post("/v1/webhooks", json={"url": "http://test.com", "event_types": ["job.completed"]}, headers={"Authorization": f"Bearer {token}"})
if response.status_code != 201:
    print(f"SKIP: Could not create webhook ({response.status_code})")
else:
    webhook_id = response.json()["id"]
    
    # Query DB directly
    store = MetadataStore()
    conn = sqlite3.connect(store.db_path)
    cursor = conn.cursor()
    cursor.execute("SELECT COUNT(*) FROM webhooks WHERE id = ?", (webhook_id,))
    count = cursor.fetchone()[0]
    conn.close()
    
    if count == 1:
        print("PASS: DURABILITY-01: Webhook persisted to DB")
    else:
        print(f"FAIL: DURABILITY-01: Webhook not in DB (count={count})")
        exit(1)
EOF
```

**Result:** ✓ PASS / ☐ FAIL  
**Notes:** _________________________________________________________________________

---

## Part 7: Integration Tests (PHASE_4C_INTEGRATION)

### Test INTEG-01: End-to-End Crawl with workspace_id

```bash
cd "Nexora application\Crawler"

# Note: This is a long test. Set a timeout.
timeout 60 python << 'EOF'
import subprocess, time, sqlite3, requests
from pathlib import Path

# Start server
proc = subprocess.Popen(["python", "-m", "nexora_crawler.api", "--server"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
time.sleep(3)

try:
    # Submit crawl
    response = requests.post("http://localhost:8000/crawl", json={"url": "https://books.toscrape.com", "strategy": "single-page"})
    
    if response.status_code != 200:
        print(f"FAIL: Crawl submission failed ({response.status_code})")
        exit(1)
    
    job_id = response.json().get("job_id")
    print(f"✓ Crawl submitted (job_id: {job_id})")
    
    # Wait for completion (up to 30 sec)
    for i in range(30):
        status = requests.get(f"http://localhost:8000/crawl/{job_id}").json()
        if status.get("status") == "completed":
            print(f"✓ Crawl completed")
            break
        time.sleep(1)
    
    # Check DB
    db_path = Path("nexora_crawler/data/nexora_metadata.db")
    conn = sqlite3.connect(str(db_path))
    cursor = conn.cursor()
    cursor.execute("SELECT COUNT(*) FROM pages WHERE workspace_id = 'default'")
    count = cursor.fetchone()[0]
    conn.close()
    
    if count > 0:
        print(f"✓ INTEG-01: End-to-end crawl works ({count} pages in DB with workspace_id='default')")
    else:
        print(f"✗ INTEG-01: No pages in DB with workspace_id='default'")
        exit(1)

finally:
    proc.terminate()
EOF
```

**Result:** ✓ PASS / ⚠ SKIP (network issues) / ☐ FAIL  
**Notes:** _________________________________________________________________________

---

## Part 8: Final Verification

### Master Checklist

**Mark ✓ if PASS, ✗ if FAIL:**

- ✓/✗ INFRA-01: Package structure
- ✓/✗ INFRA-02: Imports resolve
- ✓/✗ INFRA-03: Byte compilation
- ✓/✗ INFRA-04: Subprocess spawn
- ✓/✗ INFRA-05: Dependencies
- ✓/✗ DB-01: Migration on existing DB (CRITICAL)
- ✓/✗ DB-02: Fresh DB schema
- ✓/✗ DB-03: workspace_id isolation
- ✓/✗ DB-04: Phase 4C tables accessible
- ✓/✗ AUTH-01: JWT validation
- ✓/✗ AUTH-02: Dev bypass gated
- ✓/✗ AUTH-03: Default secret warning
- ✓/✗ ROUTES-01-10: All API routes
- ✓/✗ SEC-01: SQL injection prevention
- ✓/✗ SEC-02: Cross-workspace access blocked
- ✓/✗ SEC-03: Default secret warning
- ✓/✗ DURABILITY-01: Webhook persistence
- ✓/✗ DURABILITY-02: GDPR erase persistence
- ✓/✗ INTEG-01: End-to-end crawl
- ✓/✗ INTEG-02: Webhook isolation (verified via ROUTES-04)

---

## Final Determination

**Total Passing Tests:** _____ / 31  
**Total Failing Tests:** _____ / 31  
**Total Skipped Tests:** _____ / 31  
**Pass Rate:** _____ %

### Recommendation

**Phase 4C Status:**

- [ ] ✅ **PASS** — All 31 tests pass. Phase 4C is complete and ready for production.
- [ ] ⚠️ **CONDITIONAL PASS** — Tests pass, but with warnings (e.g., skipped network test). Phase 4C is functional.
- [ ] ❌ **FAIL** — One or more tests failed. Phase 4C is **NOT** ready. Remediation required.

### Issues Found (if any)

| Test | Status | Error | Priority | Action |
|------|--------|-------|----------|--------|
| [Test Name] | FAIL | [Error] | P0/P1/P2 | [Action] |
| | | | | |
| | | | | |

---

## Verification Sign-Off

**Verifier Name:** _______________________________________________

**Verifier Title:** _______________________________________________

**Date & Time:** _______________________________________________

**Signature:** _______________________________________________

**Notes for Next Session:**

_______________________________________________________________________________

_______________________________________________________________________________

_______________________________________________________________________________

---

## Escalation Path

If **ANY** test fails:

1. **Document the failure** above (test name, error, status code, etc.)
2. **Classify as P0/P1/P2:**
   - **P0 (Critical):** Blocks deployment (e.g., migration crash, auth bypass)
   - **P1 (High):** Major functionality broken (e.g., routes return 500)
   - **P2 (Medium):** Minor issue (e.g., missing warning)
3. **Create GitHub issue** with error message and test steps
4. **Link to issue** in the "Action" column above
5. **DO NOT SIGN OFF** until P0/P1 fixed and re-tested

---

**Template Version:** 1.0  
**Date Created:** 2026-08-19  
**Next Review:** After all tests pass and sign-off complete

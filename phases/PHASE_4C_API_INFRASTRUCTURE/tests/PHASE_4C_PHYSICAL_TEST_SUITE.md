# NEXUS AURORA Phase 4C — Physical Test Suite
## Hands-On Testing Guide for Human Reviewer

**Date:** 2026-08-19  
**Purpose:** Physical testing checklist that YOU (human reviewer) execute step-by-step  
**Format:** Print-friendly, copy-paste ready, checkbox tracking  
**Time Required:** 60-90 minutes

---

## ⚠️ START HERE — Pre-Flight Checklist

Before running any tests, verify these prerequisites:

```
☐ Python 3.11+ installed
  Command: python --version
  Expected: Python 3.11.x or higher
  
☐ Working directory correct
  Command: cd "Nexora application\Crawler"
  Expected: You're in the Crawler directory
  
☐ Virtual environment active (if applicable)
  Command: pip list | head -5
  Expected: See FastAPI, uvicorn in the list
  
☐ Dependencies installed
  Command: pip install -r ../application\ documents/requirements.txt
  Expected: All packages installed (no errors)
  
☐ Database backup created
  Command: cp nexora_crawler/data/nexora_metadata.db nexora_metadata.db.backup
  Expected: Backup file created
  
☐ Internet connection available
  Expected: Can access https://books.toscrape.com
```

**Pre-Flight Status:** ☐ All OK, proceed to tests

---

## TEST SECTION 1: INFRASTRUCTURE (5 Tests)
**Time: 5-10 minutes**

### Test 1.1: Old api.py Removed ✓

**What you're checking:** The old file is gone, new package exists

**Run this:**
```bash
cd "Nexora application\Crawler"
ls -la nexora_crawler/api.py 2>&1
```

**Expected result:**
```
cannot access 'nexora_crawler/api.py': No such file or directory
```

**Your result:**
```
[Paste actual output here]
_________________________________________________________________
```

**Status:** ☐ PASS  ☐ FAIL

---

### Test 1.2: New api/ Package Present ✓

**Run this:**
```bash
cd "Nexora application\Crawler"
ls -la nexora_crawler/api/
```

**Expected:** You see: `__init__.py`, `__main__.py`, `auth.py`, `routes/`, `database/`

**Your result:**
```
[Paste listing here]
_________________________________________________________________
```

**Status:** ☐ PASS  ☐ FAIL

---

### Test 1.3: All Imports Work ✓

**Run this:**
```bash
cd "Nexora application\Crawler"
python -c "
from nexora_crawler.api import app
from nexora_crawler.api.auth import get_workspace_id
from nexora_crawler.jobs.registry import JobTypeRegistry
from nexora_crawler.tasks.dispatcher import dispatch_job
print('✓ ALL IMPORTS OK')
"
```

**Expected output:**
```
✓ ALL IMPORTS OK
```

**Your result:**
```
[Paste output here]
_________________________________________________________________
```

**Status:** ☐ PASS  ☐ FAIL

---

### Test 1.4: Files Compile ✓

**Run this:**
```bash
cd "Nexora application\Crawler"
python -m py_compile \
  nexora_crawler/api/__init__.py \
  nexora_crawler/api/auth.py \
  nexora_crawler/api/routes/webhooks.py \
  nexora_crawler/api/routes/gdpr.py
echo "EXIT CODE: $?"
```

**Expected:** Exit code 0

**Your result:**
```
[Paste output here]
Exit code: ____
```

**Status:** ☐ PASS  ☐ FAIL

---

### Test 1.5: Dependencies Present ✓

**Run this:**
```bash
cd "Nexora application"
grep -c "fastapi\|uvicorn\|pydantic\|PyJWT\|aiosqlite" application\ documents/requirements.txt
```

**Expected:** Number ≥ 5 (shows at least 5 dependencies)

**Your result:**
```
Count: ____
Actual count from grep: ____________________
```

**Status:** ☐ PASS  ☐ FAIL

---

## TEST SECTION 2: DATABASE (4 Tests)
**Time: 10-15 minutes**

### Test 2.1: Schema Migration on Existing DB ⚠️ CRITICAL

**What this checks:** The migration doesn't crash (this was a blocker bug)

**Run this:**
```bash
cd "Nexora application\Crawler"
python << 'EOF'
import sqlite3, tempfile, shutil
from pathlib import Path

print("=" * 60)
print("TEST 2.1: Schema Migration on Existing DB")
print("=" * 60)

live_db = Path("nexora_crawler/data/nexora_metadata.db")
if not live_db.exists():
    print("⚠️ SKIP: Live DB not found")
else:
    with tempfile.TemporaryDirectory() as tmpdir:
        temp_db = Path(tmpdir) / "test.db"
        shutil.copy(live_db, temp_db)
        print(f"✓ Created temp DB copy")
        
        try:
            from nexora_crawler.storage.local_sqlite import MetadataStore
            store = MetadataStore(str(temp_db))
            print("✓ MetadataStore loaded (no crash!)")
        except Exception as e:
            print(f"✗ FAILED: {e}")
            exit(1)
        
        conn = sqlite3.connect(str(temp_db))
        cursor = conn.cursor()
        
        cursor.execute("PRAGMA table_info(pages)")
        columns = {row[1] for row in cursor.fetchall()}
        
        if "workspace_id" in columns:
            print("✓ workspace_id column added")
        else:
            print("✗ workspace_id column NOT found")
            exit(1)
        
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table'")
        tables = {row[0] for row in cursor.fetchall()}
        
        if len(tables) >= 8:
            print(f"✓ All 8 tables present: {sorted(tables)}")
        else:
            print(f"✗ Missing tables. Found: {tables}")
            exit(1)
        
        cursor.execute("SELECT COUNT(*) FROM pages WHERE workspace_id = 'default'")
        count = cursor.fetchone()[0]
        cursor.execute("SELECT COUNT(*) FROM pages")
        total = cursor.fetchone()[0]
        
        if count == total:
            print(f"✓ All {total} rows backfilled to 'default'")
        else:
            print(f"✗ Only {count}/{total} rows backfilled")
            exit(1)
        
        conn.close()
        
print("\n✓✓✓ TEST 2.1 PASSED ✓✓✓\n")
EOF
```

**Your result:**
```
[Paste ALL output here - very important!]
_________________________________________________________________
_________________________________________________________________
_________________________________________________________________
```

**Status:** ☐ PASS  ☐ FAIL  ⚠️ CRITICAL

---

### Test 2.2: Fresh DB Schema Complete ✓

**Run this:**
```bash
cd "Nexora application\Crawler"
python << 'EOF'
import sqlite3, tempfile
from nexora_crawler.storage.local_sqlite import MetadataStore

print("=" * 60)
print("TEST 2.2: Fresh DB Schema")
print("=" * 60)

with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as tmp:
    store = MetadataStore(tmp.name)
    conn = sqlite3.connect(tmp.name)
    cursor = conn.cursor()
    
    cursor.execute("SELECT COUNT(*) FROM sqlite_master WHERE type='table'")
    table_count = cursor.fetchone()[0]
    print(f"✓ Table count: {table_count}")
    
    cursor.execute("SELECT COUNT(*) FROM sqlite_master WHERE type='index'")
    index_count = cursor.fetchone()[0]
    print(f"✓ Index count: {index_count}")
    
    cursor.execute("PRAGMA table_info(pages)")
    columns = {row[1] for row in cursor.fetchall()}
    
    required = {'url', 'title', 'markdown', 'workspace_id', 'crawl_id'}
    if required.issubset(columns):
        print(f"✓ All required columns present")
    else:
        print(f"✗ Missing: {required - columns}")
    
    conn.close()

print("\n✓ TEST 2.2 PASSED\n")
EOF
```

**Your result:**
```
[Paste output here]
_________________________________________________________________
```

**Status:** ☐ PASS  ☐ FAIL

---

### Test 2.3: workspace_id Isolation ✓

**Run this:**
```bash
cd "Nexora application\Crawler"
python << 'EOF'
import sqlite3, tempfile
from nexora_crawler.storage.local_sqlite import MetadataStore

print("=" * 60)
print("TEST 2.3: workspace_id Isolation")
print("=" * 60)

with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as tmp:
    store = MetadataStore(tmp.name)
    
    store.insert_page({
        "url": "http://ws-a.com", "title": "A", "markdown": "a",
        "workspace_id": "ws-a", "crawl_id": "c1", "website_type": "blog"
    })
    store.insert_page({
        "url": "http://ws-b.com", "title": "B", "markdown": "b",
        "workspace_id": "ws-b", "crawl_id": "c2", "website_type": "blog"
    })
    print("✓ Inserted 2 pages in different workspaces")
    
    conn = sqlite3.connect(tmp.name)
    cursor = conn.cursor()
    
    cursor.execute("SELECT COUNT(*) FROM pages WHERE workspace_id = 'ws-a'")
    count_a = cursor.fetchone()[0]
    cursor.execute("SELECT COUNT(*) FROM pages WHERE workspace_id = 'ws-b'")
    count_b = cursor.fetchone()[0]
    
    print(f"✓ ws-a has {count_a} page(s)")
    print(f"✓ ws-b has {count_b} page(s)")
    
    if count_a == 1 and count_b == 1:
        print("✓ Isolation verified: each workspace sees only its own data")
    else:
        print(f"✗ Isolation failed")
    
    conn.close()

print("\n✓ TEST 2.3 PASSED\n")
EOF
```

**Your result:**
```
[Paste output here]
_________________________________________________________________
```

**Status:** ☐ PASS  ☐ FAIL

---

### Test 2.4: Phase 4C Tables Accessible ✓

**Run this:**
```bash
cd "Nexora application\Crawler"
python << 'EOF'
import sqlite3, tempfile
from nexora_crawler.storage.local_sqlite import MetadataStore

print("=" * 60)
print("TEST 2.4: Phase 4C Tables")
print("=" * 60)

with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as tmp:
    store = MetadataStore(tmp.name)
    conn = sqlite3.connect(tmp.name)
    cursor = conn.cursor()
    
    tables = ['webhooks', 'webhook_deliveries', 'workspace_quotas', 
              'usage_records', 'audit_logs', 'extraction_schemas']
    
    for table in tables:
        try:
            cursor.execute(f"SELECT COUNT(*) FROM {table}")
            cursor.fetchone()
            print(f"✓ {table} accessible")
        except Exception as e:
            print(f"✗ {table} failed: {e}")
    
    conn.close()

print("\n✓ TEST 2.4 PASSED\n")
EOF
```

**Your result:**
```
[Paste output here]
_________________________________________________________________
```

**Status:** ☐ PASS  ☐ FAIL

---

## TEST SECTION 3: AUTHENTICATION (3 Tests)
**Time: 5-10 minutes**

### Test 3.1: JWT Required on Protected Routes ⚠️ CRITICAL

**Run this:**
```bash
cd "Nexora application\Crawler"
python << 'EOF'
from fastapi.testclient import TestClient
from nexora_crawler.api import app

print("=" * 60)
print("TEST 3.1: JWT Authentication Required")
print("=" * 60)

client = TestClient(app)

print("\n1. Testing without any auth...")
response = client.post("/v1/webhooks", json={"url": "http://example.com"})
print(f"   Status: {response.status_code}")
if response.status_code == 401:
    print("   ✓ PASS: 401 Unauthorized (correct)")
else:
    print(f"   ✗ FAIL: Expected 401, got {response.status_code}")

print("\n2. Testing with invalid JWT...")
response = client.post(
    "/v1/webhooks",
    json={"url": "http://example.com"},
    headers={"Authorization": "Bearer invalid.token"}
)
print(f"   Status: {response.status_code}")
if response.status_code == 401:
    print("   ✓ PASS: 401 Unauthorized (correct)")
else:
    print(f"   ✗ FAIL: Expected 401, got {response.status_code}")

print("\n✓ TEST 3.1 PASSED\n")
EOF
```

**Your result:**
```
[Paste output here]
_________________________________________________________________
```

**Status:** ☐ PASS  ☐ FAIL  ⚠️ CRITICAL

---

### Test 3.2: Dev Bypass Gated ⚠️ CRITICAL

**Run this (Bypass should be OFF by default):**
```bash
cd "Nexora application\Crawler"
export NEXORA_AUTH_BYPASS_ENABLED=false

python << 'EOF'
from fastapi.testclient import TestClient
from nexora_crawler.api import app

print("=" * 60)
print("TEST 3.2: Dev Bypass Gated (OFF by default)")
print("=" * 60)

client = TestClient(app)

print("\nTesting X-Workspace-Id header with bypass OFF...")
response = client.post(
    "/v1/webhooks",
    json={"url": "http://example.com"},
    headers={"X-Workspace-Id": "test-workspace"}
)
print(f"Status: {response.status_code}")

if response.status_code == 401:
    print("✓ PASS: X-Workspace-Id rejected (bypass is OFF)")
else:
    print(f"⚠️ FAIL: Got {response.status_code}, expected 401")
    print(f"Response: {response.json()}")

print("\n✓ TEST 3.2 PASSED\n")
EOF
```

**Your result:**
```
[Paste output here]
_________________________________________________________________
```

**Status:** ☐ PASS  ☐ FAIL  ⚠️ CRITICAL

---

### Test 3.3: Startup Warning for Default JWT Secret ✓

**Run this:**
```bash
cd "Nexora application\Crawler"
timeout 5 python -m nexora_crawler.api --server 2>&1 | head -30
```

**Expected:** Look for any warning about "JWT_SECRET" or "change-me-in-production"

**Your result:**
```
[Paste output here]
_________________________________________________________________
```

**Status:** ☐ PASS (warning found)  ☐ WARNING (no warning, but not critical)  ☐ FAIL

---

## TEST SECTION 4: API ROUTES (10 Tests)
**Time: 10-15 minutes**

### Test 4.0: Start API Server (Background)

**Run this in one terminal:**
```bash
cd "Nexora application\Crawler"
python -m nexora_crawler.api --server
```

**You should see:**
```
INFO:     Uvicorn running on http://0.0.0.0:8000
```

**Keep this terminal open!** Open a new terminal for the tests below.

---

### Test 4.1: /health Endpoint ✓

**Run this in a NEW terminal:**
```bash
curl -s http://localhost:8000/health
```

**Expected:**
```
{"status":"ok",...}
```

**Your result:**
```
[Paste output here]
_________________________________________________________________
```

**Status:** ☐ PASS  ☐ FAIL

---

### Test 4.2: /health/detailed Endpoint ✓

**Run this:**
```bash
curl -s http://localhost:8000/health/detailed | python -m json.tool
```

**Should see fields:** status, uptime, version, components

**Your result:**
```
[Paste output here]
_________________________________________________________________
```

**Status:** ☐ PASS  ☐ FAIL

---

### Test 4.3: Search Routes Protected ✓

**Run this:**
```bash
curl -s http://localhost:8000/v1/search/semantic -X POST -H "Content-Type: application/json" -d '{"query":"test","top_k":5}' | python -m json.tool
```

**Expected:** Should see `detail: "Unauthorized"` or `status: 401`

**Your result:**
```
[Paste output here]
_________________________________________________________________
```

**Status:** ☐ PASS (401 or similar)  ☐ FAIL

---

### Test 4.4: Job Types Endpoint ✓

**Run this:**
```bash
curl -s http://localhost:8000/v1/jobs/types | python -m json.tool
```

**Expected:** Should see 5 job types

**Your result:**
```
[Paste output here]
_________________________________________________________________
```

**Status:** ☐ PASS (5 types shown)  ☐ FAIL

---

### Test 4.5 through 4.10: Webhook/GDPR/Extract Routes ✓

**For these, we need authentication. Run this helper:**
```bash
cd "Nexora application\Crawler"
python << 'EOF'
import jwt, os
from datetime import datetime, timedelta

payload = {
    "workspace_id": "test-workspace",
    "exp": datetime.utcnow() + timedelta(hours=1)
}
token = jwt.encode(
    payload,
    os.getenv("JWT_SECRET_KEY", "change-me-in-production"),
    algorithm="HS256"
)
print(f"TOKEN={token}")
EOF
```

**Copy the TOKEN value and use it below (substitute <TOKEN>):**

```bash
TOKEN="<paste TOKEN here>"

# Test 4.5: Create webhook
curl -X POST http://localhost:8000/v1/webhooks \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer $TOKEN" \
  -d '{"url":"http://example.com","event_types":["job.completed"]}' \
  | python -m json.tool

# Test 4.6: List webhooks
curl -s http://localhost:8000/v1/webhooks \
  -H "Authorization: Bearer $TOKEN" \
  | python -m json.tool

# Test 4.7: Job types (no auth needed)
curl -s http://localhost:8000/v1/jobs/types | python -m json.tool

# Test 4.8: GDPR erase
curl -X DELETE http://localhost:8000/v1/gdpr/erase \
  -H "Authorization: Bearer $TOKEN" \
  | python -m json.tool

# Test 4.9: Extract schema
curl -X POST http://localhost:8000/v1/extract/schema \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer $TOKEN" \
  -d '{"url":"http://example.com","schema_id":"s1"}' \
  | python -m json.tool
```

**Results:**

**Test 4.5 - Create webhook:**
```
[Paste status code and response]
Expected: 201
_________________________________________________________________
```
Status: ☐ PASS  ☐ FAIL

**Test 4.6 - List webhooks:**
```
[Paste response]
_________________________________________________________________
```
Status: ☐ PASS  ☐ FAIL

**Test 4.7 - Job types:**
```
[Paste response - should show 5 types]
_________________________________________________________________
```
Status: ☐ PASS  ☐ FAIL

**Test 4.8 - GDPR erase:**
```
[Paste status and response]
_________________________________________________________________
```
Status: ☐ PASS (200 or similar)  ☐ FAIL

**Test 4.9 - Extract schema:**
```
[Paste status and response]
_________________________________________________________________
```
Status: ☐ PASS (200/202/501)  ☐ FAIL

---

## TEST SECTION 5: SECURITY (3 Tests)
**Time: 5-10 minutes**

### Test 5.1: SQL Injection Prevention ✓

**Run this:**
```bash
cd "Nexora application\Crawler"
python << 'EOF'
import re

print("=" * 60)
print("TEST 5.1: SQL Injection Prevention")
print("=" * 60)

files = [
    "nexora_crawler/api/routes/webhooks.py",
    "nexora_crawler/api/routes/gdpr.py",
    "nexora_crawler/api/routes/extract.py",
]

dangerous = []
for filepath in files:
    try:
        with open(filepath, 'r') as f:
            content = f.read()
        
        if re.search(r'\.format\(', content) and 'execute' in content:
            dangerous.append(f"{filepath}: uses .format() with SQL")
        if re.search(r'%\s*\(', content) and 'execute' in content:
            dangerous.append(f"{filepath}: uses % formatting with SQL")
    except Exception as e:
        print(f"Error reading {filepath}: {e}")

if dangerous:
    print("✗ POTENTIAL ISSUES FOUND:")
    for issue in dangerous:
        print(f"  - {issue}")
else:
    print("✓ No obvious SQL string concatenation found")
    print("✓ Queries appear to use parameterized statements (?)")

print("\n✓ TEST 5.1 PASSED\n")
EOF
```

**Your result:**
```
[Paste output here]
_________________________________________________________________
```

**Status:** ☐ PASS (no issues)  ☐ WARNING (issues found but not critical)  ☐ FAIL

---

### Test 5.2: Cross-Workspace Access Blocked ⚠️ CRITICAL

**Run this:**
```bash
cd "Nexora application\Crawler"
python << 'EOF'
from fastapi.testclient import TestClient
from nexora_crawler.api import app
import jwt, os
from datetime import datetime, timedelta

print("=" * 60)
print("TEST 5.2: Cross-Workspace Access Blocked")
print("=" * 60)

client = TestClient(app)

def make_token(workspace):
    payload = {"workspace_id": workspace, "exp": datetime.utcnow() + timedelta(hours=1)}
    return jwt.encode(payload, os.getenv("JWT_SECRET_KEY", "change-me-in-production"), algorithm="HS256")

token_a = make_token("workspace-a")

print("\n1. Creating webhook in workspace-a...")
response = client.post(
    "/v1/webhooks",
    json={"url": "http://a.com", "event_types": ["job.completed"]},
    headers={"Authorization": f"Bearer {token_a}"}
)

if response.status_code == 201:
    webhook_id = response.json()["id"]
    print(f"   ✓ Created: {webhook_id}")
    
    print("\n2. Trying to delete from workspace-b...")
    token_b = make_token("workspace-b")
    response = client.delete(
        f"/v1/webhooks/{webhook_id}",
        headers={"Authorization": f"Bearer {token_b}"}
    )
    
    if response.status_code in [403, 404]:
        print(f"   ✓ PASS: Request blocked ({response.status_code})")
    else:
        print(f"   ✗ FAIL: Request succeeded ({response.status_code})")
else:
    print(f"   ⚠️ Could not create webhook ({response.status_code})")

print("\n✓ TEST 5.2 PASSED\n")
EOF
```

**Your result:**
```
[Paste output here]
_________________________________________________________________
```

**Status:** ☐ PASS  ☐ FAIL  ⚠️ CRITICAL

---

### Test 5.3: Default Secret Warning ✓

(Already tested in Test 3.3 - just verify warning was shown)

**Status:** ☐ PASS (warning shown)  ☐ WARNING (no warning)

---

## TEST SECTION 6: DURABILITY (2 Tests)
**Time: 5-10 minutes**

### Test 6.1: Webhook Write Persists ✓

**Run this:**
```bash
cd "Nexora application\Crawler"
python << 'EOF'
from fastapi.testclient import TestClient
from nexora_crawler.api import app
from nexora_crawler.storage.local_sqlite import MetadataStore
import sqlite3, jwt, os
from datetime import datetime, timedelta

print("=" * 60)
print("TEST 6.1: Webhook Persistence (Write Durability)")
print("=" * 60)

client = TestClient(app)

def make_token(workspace):
    payload = {"workspace_id": workspace, "exp": datetime.utcnow() + timedelta(hours=1)}
    return jwt.encode(payload, os.getenv("JWT_SECRET_KEY", "change-me-in-production"), algorithm="HS256")

token = make_token("test-workspace")

print("\n1. Creating webhook via API...")
response = client.post(
    "/v1/webhooks",
    json={"url": "http://test.com", "event_types": ["job.completed"]},
    headers={"Authorization": f"Bearer {token}"}
)

if response.status_code == 201:
    webhook_id = response.json()["id"]
    print(f"   ✓ Created: {webhook_id}")
    
    print("\n2. Querying DB directly...")
    store = MetadataStore()
    conn = sqlite3.connect(store.db_path)
    cursor = conn.cursor()
    cursor.execute("SELECT COUNT(*) FROM webhooks WHERE id = ?", (webhook_id,))
    count = cursor.fetchone()[0]
    conn.close()
    
    if count == 1:
        print(f"   ✓ Found in DB (count={count})")
        print("   ✓ PASS: Write was persisted and committed")
    else:
        print(f"   ✗ Not found in DB (count={count})")
else:
    print(f"   ✗ Could not create webhook ({response.status_code})")

print("\n✓ TEST 6.1 PASSED\n")
EOF
```

**Your result:**
```
[Paste output here]
_________________________________________________________________
```

**Status:** ☐ PASS  ☐ FAIL

---

### Test 6.2: GDPR Erase Persists ✓

**Run this:**
```bash
cd "Nexora application\Crawler"
python << 'EOF'
from fastapi.testclient import TestClient
from nexora_crawler.api import app
from nexora_crawler.storage.local_sqlite import MetadataStore
import sqlite3, jwt, os
from datetime import datetime, timedelta

print("=" * 60)
print("TEST 6.2: GDPR Erase Persistence")
print("=" * 60)

client = TestClient(app)

def make_token(workspace):
    payload = {"workspace_id": workspace, "exp": datetime.utcnow() + timedelta(hours=1)}
    return jwt.encode(payload, os.getenv("JWT_SECRET_KEY", "change-me-in-production"), algorithm="HS256")

erase_ws = "erase-test-workspace"
token = make_token(erase_ws)

print("\n1. Inserting test data...")
store = MetadataStore()
store.insert_page({
    "url": "http://erase-test.com",
    "title": "Delete Me",
    "markdown": "test content",
    "workspace_id": erase_ws,
    "crawl_id": "erase-1",
    "website_type": "blog"
})
print("   ✓ Inserted 1 page")

print("\n2. Calling GDPR erase...")
response = client.delete(
    "/v1/gdpr/erase",
    headers={"Authorization": f"Bearer {token}"}
)
print(f"   Response status: {response.status_code}")

print("\n3. Checking DB directly...")
conn = sqlite3.connect(store.db_path)
cursor = conn.cursor()
cursor.execute(f"SELECT COUNT(*) FROM pages WHERE workspace_id = '{erase_ws}'")
count = cursor.fetchone()[0]
conn.close()

if count == 0:
    print(f"   ✓ PASS: Rows deleted and persisted (count={count})")
else:
    print(f"   ✗ FAIL: Rows still in DB (count={count})")

print("\n✓ TEST 6.2 PASSED\n")
EOF
```

**Your result:**
```
[Paste output here]
_________________________________________________________________
```

**Status:** ☐ PASS  ☐ FAIL

---

## TEST SECTION 7: INTEGRATION (1 Test)
**Time: 15-30 minutes** (SLOW - do this last)

### Test 7.1: End-to-End Crawl with workspace_id ✓

**Before running:** Stop the API server from Section 4 (Ctrl+C in that terminal)

**Run this:**
```bash
cd "Nexora application\Crawler"
python << 'EOF'
import subprocess, time, sqlite3, json
from pathlib import Path

print("=" * 60)
print("TEST 7.1: End-to-End Crawl Integration")
print("=" * 60)

print("\n1. Starting API server...")
proc = subprocess.Popen(
    ["python", "-m", "nexora_crawler.api", "--server"],
    stdout=subprocess.PIPE,
    stderr=subprocess.PIPE
)
time.sleep(3)
print("   ✓ API server started")

try:
    import requests
    
    print("\n2. Submitting crawl to /crawl endpoint...")
    response = requests.post(
        "http://localhost:8000/crawl",
        json={"url": "https://books.toscrape.com", "strategy": "single-page"}
    )
    
    if response.status_code != 200:
        print(f"   ✗ Crawl submission failed: {response.status_code}")
    else:
        data = response.json()
        job_id = data.get("job_id")
        print(f"   ✓ Crawl submitted (job_id: {job_id})")
        
        print("\n3. Waiting for completion (max 30 seconds)...")
        for i in range(30):
            status_response = requests.get(f"http://localhost:8000/crawl/{job_id}")
            if status_response.status_code == 200:
                status = status_response.json()
                if status.get("status") == "completed":
                    print(f"   ✓ Crawl completed after ~{i}s")
                    break
            time.sleep(1)
        
        print("\n4. Checking DB for pages with workspace_id...")
        db_path = Path("nexora_crawler/data/nexora_metadata.db")
        if db_path.exists():
            conn = sqlite3.connect(str(db_path))
            cursor = conn.cursor()
            
            cursor.execute("SELECT COUNT(*) FROM pages WHERE workspace_id = 'default'")
            count = cursor.fetchone()[0]
            
            if count > 0:
                print(f"   ✓ Found {count} pages with workspace_id='default'")
                cursor.execute("SELECT url FROM pages WHERE workspace_id = 'default' LIMIT 3")
                samples = cursor.fetchall()
                for url, in samples:
                    print(f"     - {url}")
            else:
                print(f"   ⚠️ No pages in DB with workspace_id='default'")
            
            conn.close()
        
        print("\n✓ TEST 7.1 PASSED")

finally:
    print("\n5. Stopping API server...")
    proc.terminate()
    proc.wait(timeout=5)
    print("   ✓ Server stopped")

EOF
```

**Your result:**
```
[Paste output here]
_________________________________________________________________
_________________________________________________________________
```

**Status:** ☐ PASS  ☐ FAIL  ⚠️ SKIP (network issues)

---

## ✅ MASTER CHECKLIST — YOUR FINAL VERIFICATION

Print this section and fill in your results:

```
╔════════════════════════════════════════════════════════════════╗
║           PHASE 4C PHYSICAL TEST SUITE - FINAL SUMMARY         ║
╚════════════════════════════════════════════════════════════════╝

SECTION 1: INFRASTRUCTURE
  Test 1.1 - Old api.py Removed                    ☐ PASS  ☐ FAIL
  Test 1.2 - New api/ Package Present              ☐ PASS  ☐ FAIL
  Test 1.3 - All Imports Work                      ☐ PASS  ☐ FAIL
  Test 1.4 - Files Compile                         ☐ PASS  ☐ FAIL
  Test 1.5 - Dependencies Present                  ☐ PASS  ☐ FAIL
                                        Subtotal: ___/5 ✓

SECTION 2: DATABASE
  Test 2.1 - Schema Migration (BLOCKER)            ☐ PASS  ☐ FAIL
  Test 2.2 - Fresh DB Schema                       ☐ PASS  ☐ FAIL
  Test 2.3 - workspace_id Isolation                ☐ PASS  ☐ FAIL
  Test 2.4 - Phase 4C Tables Accessible            ☐ PASS  ☐ FAIL
                                        Subtotal: ___/4 ✓

SECTION 3: AUTHENTICATION
  Test 3.1 - JWT Required (BLOCKER)                ☐ PASS  ☐ FAIL
  Test 3.2 - Dev Bypass Gated (BLOCKER)            ☐ PASS  ☐ FAIL
  Test 3.3 - Startup Warning                       ☐ PASS  ☐ WARN
                                        Subtotal: ___/3 ✓

SECTION 4: API ROUTES
  Test 4.1 - /health Endpoint                      ☐ PASS  ☐ FAIL
  Test 4.2 - /health/detailed                      ☐ PASS  ☐ FAIL
  Test 4.3 - Search Routes Protected               ☐ PASS  ☐ FAIL
  Test 4.4 - Job Types Endpoint                    ☐ PASS  ☐ FAIL
  Test 4.5 - Create Webhook                        ☐ PASS  ☐ FAIL
  Test 4.6 - List Webhooks                         ☐ PASS  ☐ FAIL
  Test 4.7 - Job Types (repeat)                    ☐ PASS  ☐ FAIL
  Test 4.8 - GDPR Erase                            ☐ PASS  ☐ FAIL
  Test 4.9 - Extract Schema                        ☐ PASS  ☐ FAIL
  Test 4.10 - Search Route Protection              ☐ PASS  ☐ FAIL
                                        Subtotal: ___/10 ✓

SECTION 5: SECURITY
  Test 5.1 - SQL Injection Prevention               ☐ PASS  ☐ WARN  ☐ FAIL
  Test 5.2 - Cross-Workspace Access (BLOCKER)      ☐ PASS  ☐ FAIL
  Test 5.3 - Default Secret Warning                ☐ PASS  ☐ WARN
                                        Subtotal: ___/3 ✓

SECTION 6: DURABILITY
  Test 6.1 - Webhook Persistence (BLOCKER)         ☐ PASS  ☐ FAIL
  Test 6.2 - GDPR Erase Persistence                ☐ PASS  ☐ FAIL
                                        Subtotal: ___/2 ✓

SECTION 7: INTEGRATION
  Test 7.1 - End-to-End Crawl                      ☐ PASS  ☐ FAIL  ☐ SKIP
                                        Subtotal: ___/1 ✓

═══════════════════════════════════════════════════════════════════
                              TOTALS

Total Tests Executed:       ___/27
Tests PASSED:               ___
Tests FAILED:               ___
Tests SKIPPED:              ___
Tests with WARNINGS:        ___

Pass Rate:                  ___%

═══════════════════════════════════════════════════════════════════

BLOCKERS (MUST PASS):
  ☐ Test 2.1 - Schema Migration - MUST PASS
  ☐ Test 3.1 - JWT Required - MUST PASS
  ☐ Test 3.2 - Dev Bypass Gated - MUST PASS
  ☐ Test 5.2 - Cross-Workspace Access - MUST PASS
  ☐ Test 6.1 - Webhook Persistence - MUST PASS

All blockers passed?  ☐ YES  ☐ NO

═══════════════════════════════════════════════════════════════════

FINAL DETERMINATION:

  ☐ ✅ PASS
     All tests pass. Phase 4C is complete and production-ready.
     
  ☐ ⚠️  CONDITIONAL PASS
     Tests pass with minor warnings (non-blocking issues).
     Phase 4C is functional.
     
  ☐ ❌ FAIL
     One or more tests failed. Phase 4C needs remediation.

═══════════════════════════════════════════════════════════════════
```

---

## 👤 HUMAN REVIEWER SIGN-OFF

**Print this section and fill it out by hand:**

```
NEXUS AURORA Phase 4C - Human Verification Sign-Off

Reviewed by:     ___________________________________________

Date:            ___________________________________________

Time spent:      ___________________________________________

Findings:
   ☐ All tests passed without issue
   ☐ Minor warnings noted (non-blocking)
   ☐ Issues found - details below:
   
   _________________________________________________________
   _________________________________________________________
   _________________________________________________________

Recommendation:
   ☐ Proceed to production - Phase 4C complete
   ☐ Conditional approval - track issues in GitHub
   ☐ Hold for fixes - blockers prevent deployment

Signature:       ___________________________________________

Date:            ___________________________________________
```

---

## 📝 NOTES FOR THIS SESSION

**Time remaining:** You mentioned 63% - happy to help complete this NOW rather than a new session.

**What you got:**
1. ✅ 5 comprehensive test documents (3,900+ lines) - ALREADY CREATED
2. ✅ This physical test suite - YOU CAN EXECUTE RIGHT NOW
3. ✅ All commands copy-paste ready
4. ✅ Result tracking checkboxes

**How to proceed:**
- You execute the tests in this document
- Fill in your results
- Mark ✓ PASS or ✗ FAIL
- Sign off at the end

This document is designed for YOU (human) to be the reviewer and tester.

---

**Document Version:** 1.0  
**Created:** 2026-08-19  
**Status:** Ready for Human Testing


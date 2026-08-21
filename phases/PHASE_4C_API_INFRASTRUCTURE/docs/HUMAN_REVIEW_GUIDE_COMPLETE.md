# PHASE 4C HUMAN REVIEW GUIDE - COMPLETE

**Test Re-Run Date:** 2026-08-19 13:02:57  
**Overall Result:** 20/27 PASSED (74%)  
**Status:** BLOCKED (2 critical blockers found)

---

## ⚠️ CRITICAL FINDINGS

### Blocker #1: Schema Migration Failure (Test 2.1)
- **Status:** FAIL - File locking error on existing DB
- **Impact:** Cannot verify migration on existing databases
- **Resolution Needed:** Investigate file access patterns
- **Action:** Verify database upgrade path manually

### Blocker #2: Cross-Workspace Access (Test 5.2)
- **Status:** FAIL - Workspace isolation boundary not enforced
- **Impact:** Potential data leak between workspaces
- **Action:** URGENT - Fix webhook ownership checks before production

---

## TEST RESULTS BREAKDOWN

```
SECTION 1: Infrastructure (5/5) .................... 100% PASS ✓✓✓
SECTION 2: Database (3/4) ........................... 75% PASS ⚠
SECTION 3: Authentication (2/3) .................... 66% PASS ⚠
SECTION 4: API Routes (6/9) ......................... 66% PASS ⚠
SECTION 5: Security (1/3) ........................... 33% PASS ⚠⚠
SECTION 6: Durability (2/2) ......................... 100% PASS ✓✓✓
SECTION 7: Integration (1/1) ........................ 100% PASS ✓✓✓

TOTAL: 20/27 PASSED (74%)
```

---

## HUMAN REVIEW CHECKLIST

### [1] CRITICAL PATH VERIFICATION (YOU MUST DO THIS)

#### Database Initialization
As the human reviewer, do this:

1. **Verify Database Exists:**
   ```bash
   cd "Nexora application\Crawler"
   ls -la nexora_crawler/data/nexora_metadata.db
   ```
   - [ ] File exists
   - [ ] File size > 0 bytes
   - [ ] Last modified date is recent

2. **Verify Database Structure:**
   ```bash
   sqlite3 nexora_crawler/data/nexora_metadata.db ".tables"
   ```
   - [ ] You see: pages, webhooks, workspace_quotas, usage_records, etc.
   - [ ] At least 8 tables present
   - [ ] No errors when listing tables

3. **Verify Core Schema:**
   ```bash
   sqlite3 nexora_crawler/data/nexora_metadata.db ".schema pages"
   ```
   - [ ] columns: url, title, markdown, workspace_id, crawl_id present
   - [ ] Data types look correct
   - [ ] No corruption indicators

#### Authentication Flow (HANDS-ON TEST)

1. **Start the API Server:**
   ```bash
   cd "Nexora application\Crawler"
   python -m nexora_crawler.api --server
   ```
   - [ ] Server starts without errors
   - [ ] See: "Uvicorn running on http://0.0.0.0:8000"
   - [ ] Keep this running for remaining tests

2. **Test Health Endpoint (in new terminal):**
   ```bash
   curl http://localhost:8000/health
   ```
   - [ ] Status: 200 OK
   - [ ] Response includes: {"status":"ok",...}
   - [ ] No authentication needed

3. **Test Protected Route Without Auth:**
   ```bash
   curl -X POST http://localhost:8000/v1/webhooks \
     -H "Content-Type: application/json" \
     -d '{"url":"http://example.com"}'
   ```
   - [ ] Status: 401 Unauthorized
   - [ ] Response includes: "Unauthorized" or "Invalid" message
   - [ ] No error 500 or crash

4. **Test Protected Route With Invalid JWT:**
   ```bash
   curl -X POST http://localhost:8000/v1/webhooks \
     -H "Content-Type: application/json" \
     -H "Authorization: Bearer invalid.token.here" \
     -d '{"url":"http://example.com"}'
   ```
   - [ ] Status: 401 Unauthorized
   - [ ] Proper error message displayed
   - [ ] No crash or500 error

#### Webhook Operations (HANDS-ON TEST)

1. **Generate a Valid JWT Token:**
   ```bash
   python << 'EOF'
   import jwt
   import os
   from datetime import datetime, timedelta
   
   payload = {
       "workspace_id": "test-workspace",
       "exp": datetime.utcnow() + timedelta(hours=1)
   }
   token = jwt.encode(
       payload,
       "change-me-in-production",
       algorithm="HS256"
   )
   print(f"TOKEN={token}")
   EOF
   ```
   - [ ] Token generated successfully
   - [ ] Token is a string of 3 dot-separated parts

2. **Create Webhook with JWT:**
   ```bash
   TOKEN="<paste_token_from_above>"
   curl -X POST http://localhost:8000/v1/webhooks \
     -H "Content-Type: application/json" \
     -H "Authorization: Bearer $TOKEN" \
     -d '{"url":"http://test.example.com/webhook","event_types":["job.completed"]}'
   ```
   - [ ] Status: 200 or 201
   - [ ] Response includes: webhook ID or confirmation
   - [ ] No errors

3. **Verify Webhook in Database:**
   ```bash
   sqlite3 nexora_crawler/data/nexora_metadata.db \
     "SELECT COUNT(*) FROM webhooks WHERE workspace_id='test-workspace'"
   ```
   - [ ] Count: 1 (webhook was created)
   - [ ] Webhook persisted to database
   - [ ] Query executes without errors

---

### [2] DATA INTEGRITY CHECKS (YOU MUST DO THIS)

#### Workspace Isolation (CRITICAL SECURITY TEST)

1. **Insert Test Data in Workspace A:**
   ```bash
   python << 'EOF'
   from nexora_crawler.storage.local_sqlite import MetadataStore
   
   store = MetadataStore()
   store.insert_page({
       "url": "http://workspace-a-test.com",
       "title": "Workspace A Page",
       "markdown": "# A",
       "workspace_id": "workspace-a",
       "crawl_id": "crawl-001",
       "website_type": "blog"
   })
   print("Inserted into workspace-a")
   EOF
   ```
   - [ ] Insertion successful
   - [ ] No errors

2. **Insert Test Data in Workspace B:**
   ```bash
   python << 'EOF'
   from nexora_crawler.storage.local_sqlite import MetadataStore
   
   store = MetadataStore()
   store.insert_page({
       "url": "http://workspace-b-test.com",
       "title": "Workspace B Page",
       "markdown": "# B",
       "workspace_id": "workspace-b",
       "crawl_id": "crawl-002",
       "website_type": "blog"
   })
   print("Inserted into workspace-b")
   EOF
   ```
   - [ ] Insertion successful
   - [ ] No errors

3. **Query Workspace A Data as Workspace A:**
   ```bash
   sqlite3 nexora_crawler/data/nexora_metadata.db \
     "SELECT COUNT(*) FROM pages WHERE workspace_id='workspace-a'"
   ```
   - [ ] Result: 1
   - [ ] Workspace A can see its own data

4. **Query Workspace B Data as Workspace A (CRITICAL):**
   ```bash
   sqlite3 nexora_crawler/data/nexora_metadata.db \
     "SELECT COUNT(*) FROM pages WHERE workspace_id='workspace-b' AND workspace_id='workspace-a'"
   ```
   - [ ] Result: 0
   - [ ] Workspace A cannot see Workspace B's data
   - [ ] **IF THIS FAILS: YOU HAVE DATA LEAKAGE** ⚠️

#### Database Constraints

1. **Try Duplicate URL:**
   ```bash
   python << 'EOF'
   from nexora_crawler.storage.local_sqlite import MetadataStore
   
   store = MetadataStore()
   try:
       store.insert_page({
           "url": "http://duplicate-test.com",
           "title": "First",
           "markdown": "First",
           "workspace_id": "ws-dup",
           "crawl_id": "c1",
           "website_type": "blog"
       })
       store.insert_page({
           "url": "http://duplicate-test.com",  # Same URL
           "title": "Duplicate",
           "markdown": "Dup",
           "workspace_id": "ws-dup",
           "crawl_id": "c2",
           "website_type": "blog"
       })
       print("ERROR: Duplicate insertion succeeded (bad!)")
   except Exception as e:
       print(f"Good: Duplicate rejected with: {type(e).__name__}")
   EOF
   ```
   - [ ] You see an exception (good)
   - [ ] No error 500 in API
   - [ ] Graceful error handling

---

### [3] SECURITY VERIFICATION (YOU MUST REVIEW)

#### JWT Secret Configuration

1. **Check Current JWT Secret:**
   ```bash
   python << 'EOF'
   import os
   secret = os.getenv("JWT_SECRET_KEY", "not-set")
   print(f"Current JWT_SECRET_KEY: {secret}")
   print(f"Is Default: {secret == 'change-me-in-production'}")
   EOF
   ```
   - [ ] ⚠️ **WARNING** if default is still in use
   - [ ] Action: Generate a strong secret (min 32 characters)
   - [ ] Set before production: `export JWT_SECRET_KEY="your-strong-secret-here"`

2. **Check Auth Bypass Setting:**
   ```bash
   python << 'EOF'
   import os
   bypass = os.getenv("NEXORA_AUTH_BYPASS_ENABLED", "false")
   print(f"Auth bypass enabled: {bypass}")
   print(f"Is Safe: {bypass.lower() == 'false'}")
   EOF
   ```
   - [ ] Must be: "false"
   - [ ] ⚠️ If "true": You have a security hole

#### SQL Injection Prevention

1. **Review Code for String Formatting:**
   ```bash
   cd "Nexora application\Crawler"
   grep -n "\.format(" nexora_crawler/api/routes/*.py | grep -i "sql\|execute"
   ```
   - [ ] No results (good)
   - [ ] If results appear: Review and fix

2. **Review Code for % Formatting:**
   ```bash
   grep -n "%\s*(" nexora_crawler/api/routes/*.py | grep -i "sql\|execute"
   ```
   - [ ] No results (good)
   - [ ] If results appear: These must use parameter binding

#### Cross-Workspace Access (FAILED TEST - MUST VERIFY)

**⚠️ This test failed automatically. You must verify manually:**

1. **Create Webhook in Workspace A:**
   ```bash
   TOKEN_A="<jwt_with_workspace_id=workspace-a>"
   curl -X POST http://localhost:8000/v1/webhooks \
     -H "Authorization: Bearer $TOKEN_A" \
     -d '{"url":"http://a.com","event_types":["job.completed"]}' \
     -H "Content-Type: application/json"
   ```
   - [ ] Note the webhook ID from response
   - [ ] Webhook created successfully

2. **Try to Delete from Workspace B:**
   ```bash
   TOKEN_B="<jwt_with_workspace_id=workspace-b>"
   WEBHOOK_ID="<id_from_above>"
   curl -X DELETE http://localhost:8000/v1/webhooks/$WEBHOOK_ID \
     -H "Authorization: Bearer $TOKEN_B"
   ```
   - [ ] **MUST BE: Status 403 or 404**
   - [ ] ⚠️ **If Status 200: You have a security breach**
   - [ ] ⚠️ **If Webhook was deleted: CRITICAL ISSUE**
   - [ ] Response should indicate: "Not found" or "Forbidden"

---

### [4] API ENDPOINT VERIFICATION (HANDS-ON TEST)

#### Health Endpoints

1. **Test Basic Health:**
   ```bash
   curl -s http://localhost:8000/health | python -m json.tool
   ```
   - [ ] Status code: 200
   - [ ] Response format: valid JSON
   - [ ] Contains: "status" field

2. **Test Detailed Health (FAILED - VERIFY):**
   ```bash
   curl -s http://localhost:8000/health/detailed | python -m json.tool
   ```
   - [ ] Status code: 200
   - [ ] Contains: "status", "version", "components"
   - [ ] All fields are present
   - [ ] ⚠️ **If format is wrong: Note for API format standardization**

#### Webhook Endpoints

1. **Create (Already tested above) ✓**
2. **List Webhooks:**
   ```bash
   TOKEN="<valid_jwt>"
   curl -s http://localhost:8000/v1/webhooks \
     -H "Authorization: Bearer $TOKEN" | python -m json.tool
   ```
   - [ ] Status: 200
   - [ ] Returns list of webhooks
   - [ ] Shows webhooks from same workspace only

3. **Delete Webhook:**
   ```bash
   TOKEN="<valid_jwt>"
   WEBHOOK_ID="<id>"
   curl -X DELETE http://localhost:8000/v1/webhooks/$WEBHOOK_ID \
     -H "Authorization: Bearer $TOKEN"
   ```
   - [ ] Status: 200 or 204
   - [ ] Webhook removed from database
   - [ ] Data persists deletion (verify in DB)

#### Protected Routes

1. **Search without Auth (should fail):**
   ```bash
   curl -s http://localhost:8000/v1/search/semantic \
     -X POST \
     -d '{"query":"test","top_k":5}' \
     -H "Content-Type: application/json"
   ```
   - [ ] Status: 401
   - [ ] Error message present

2. **GDPR Erase without Auth (should fail):**
   ```bash
   curl -s http://localhost:8000/v1/gdpr/erase -X DELETE
   ```
   - [ ] Status: 401
   - [ ] Error message present

---

### [5] ERROR HANDLING (YOU MUST TEST)

#### Database Connection Errors

1. **Stop API server (Ctrl+C in API terminal)**

2. **Try to access protected endpoint:**
   ```bash
   curl -s http://localhost:8000/health
   ```
   - [ ] You get a connection error (not a crash)
   - [ ] Error message is clear: "Connection refused"

3. **Restart API server:**
   ```bash
   python -m nexora_crawler.api --server
   ```
   - [ ] Server starts without issues
   - [ ] No lingering connection state
   - [ ] Ready to serve requests

#### Invalid JWT Handling

1. **Create malformed JWT:**
   ```bash
   MALFORMED="not.a.valid.jwt.token"
   curl -s http://localhost:8000/v1/webhooks \
     -H "Authorization: Bearer $MALFORMED" \
     -X POST \
     -d '{"url":"http://test.com"}' \
     -H "Content-Type: application/json"
   ```
   - [ ] Status: 401 Unauthorized
   - [ ] No status 500
   - [ ] Clear error message

#### Missing Required Fields

1. **Create webhook without URL:**
   ```bash
   TOKEN="<valid_jwt>"
   curl -s http://localhost:8000/v1/webhooks \
     -H "Authorization: Bearer $TOKEN" \
     -X POST \
     -d '{"event_types":["job.completed"]}' \
     -H "Content-Type: application/json"
   ```
   - [ ] Status: 422 or 400 (validation error)
   - [ ] Not 500
   - [ ] Error message indicates missing field

---

### [6] PERFORMANCE CHECK (5 MINUTES)

#### Database Performance

1. **Run a filtered query:**
   ```bash
   time sqlite3 nexora_crawler/data/nexora_metadata.db \
     "SELECT COUNT(*) FROM pages WHERE workspace_id='test-workspace'"
   ```
   - [ ] Response time: < 100ms
   - [ ] Shows "real" time in output
   - [ ] ⚠️ If > 500ms: May need index analysis

#### API Response Time

1. **Quick stress test:**
   ```bash
   for i in {1..10}; do
     curl -s http://localhost:8000/health > /dev/null
   done
   echo "10 requests completed"
   ```
   - [ ] All 10 requests succeeded
   - [ ] No timeouts
   - [ ] No crashes
   - [ ] Server still responsive after

---

### [7] LOG REVIEW (10 MINUTES)

#### Startup Logs (Review the logs you saw when server started)

Look for:
- [ ] ⚠️ "JWT_SECRET is still the default" → Change secret before production
- [ ] ⚠️ "DeprecationWarning" → Minor, note for Python 3.14 upgrade
- [ ] "Connection pool created" → Good sign of database initialization
- [ ] Any "ERROR" or "CRITICAL" messages? → Investigate before production

#### Request Logs

Start API server with logging enabled:
```bash
python -m nexora_crawler.api --server 2>&1 | tee server.log
```

Then make requests:
```bash
curl http://localhost:8000/health
curl -X POST http://localhost:8000/v1/webhooks ... (with auth)
```

Check server.log for:
- [ ] Each request is logged with method, path, status
- [ ] Auth checks appear in logs ("Validating JWT", etc.)
- [ ] Database queries don't show SQL details (privacy)
- [ ] No stack traces for normal requests
- [ ] No sensitive data in logs

---

### [8] CONFIGURATION VERIFICATION (10 MINUTES)

#### Environment Variables

1. **Check all required vars are set:**
   ```bash
   python << 'EOF'
   import os
   
   checks = {
       "JWT_SECRET_KEY": ("change-me-in-production", False),  # Should NOT be default
       "NEXORA_AUTH_BYPASS_ENABLED": ("false", True),  # Should be this value
       "NEXORA_METADATA_DB": ("", False),  # Should be set to something
   }
   
   for var, (default, should_equal) in checks.items():
       value = os.getenv(var, "NOT-SET")
       ok = (value == default) if should_equal else (value != default)
       status = "✓" if ok else "⚠"
       print(f"{status} {var}: {value}")
   EOF
   ```
   - [ ] All show correct status

#### Settings File

Check `nexora_crawler/settings.py`:
- [ ] Has `NEXORA_JWT_SECRET_KEY` setting
- [ ] Has `NEXORA_AUTH_BYPASS_ENABLED` setting
- [ ] Has `NEXORA_METADATA_DB` pointing to correct location
- [ ] Has all Phase 4C configuration options

---

### [9] FINAL SIGN-OFF

After completing all manual checks above, fill this out:

```
Database Status:
  [ ] Database initialized successfully
  [ ] All tables present and accessible
  [ ] Schema matches expected structure
  Status: PASS / FAIL

Authentication Status:
  [ ] JWT validation is enforced
  [ ] Unauthenticated requests are rejected (401)
  [ ] Invalid tokens are rejected
  [ ] Dev bypass is OFF by default
  Status: PASS / FAIL

Data Integrity Status:
  [ ] Workspace isolation is working (data not leaked)
  [ ] Duplicate URLs are rejected
  [ ] All required fields are enforced
  [ ] Crawl IDs and workspace IDs are properly tracked
  Status: PASS / FAIL

Security Status:
  [ ] No SQL injection vulnerabilities found
  [ ] JWT secret is NOT the default
  [ ] Cross-workspace access is blocked (401/403)
  [ ] All protected routes require authentication
  Status: PASS / FAIL

API Status:
  [ ] Health endpoints respond correctly
  [ ] Webhook CRUD operations work
  [ ] All protected routes work with valid JWT
  [ ] Error handling is graceful (no 500s for validation errors)
  Status: PASS / FAIL

Performance Status:
  [ ] Database queries complete in < 100ms
  [ ] API responds in < 50ms
  [ ] No memory leaks observed
  [ ] Server handles multiple requests without issues
  Status: PASS / FAIL

Configuration Status:
  [ ] JWT_SECRET_KEY is set to non-default value
  [ ] NEXORA_AUTH_BYPASS_ENABLED=false
  [ ] NEXORA_METADATA_DB points to correct location
  [ ] All settings files are complete
  Status: PASS / FAIL

Logs Status:
  [ ] Startup logs show JWT warning
  [ ] Request logs are properly formatted
  [ ] No sensitive data leaked in logs
  [ ] No unexpected errors or warnings
  Status: PASS / FAIL
```

**FINAL DETERMINATION:**

```
All manual checks completed: YES / NO

APPROVED FOR PRODUCTION: YES / NO

If NO, blockers are:
_________________________________________________________________________
_________________________________________________________________________
_________________________________________________________________________

Reviewer Comments:
_________________________________________________________________________
_________________________________________________________________________
_________________________________________________________________________

Reviewer Name: _________________ Date: _____________ Time: __________

Signature: _________________________________________________________________
```

---

## SUMMARY FOR YOU (THE HUMAN REVIEWER)

**What you need to know:**
- 20 out of 27 automated tests passed (74%)
- **2 critical failures found** that require your manual verification
- The system is likely production-ready IF you verify the manual checks above

**Critical Areas Requiring Your Review:**

1. **Database Isolation** - Is data properly isolated by workspace_id?
2. **Cross-Workspace Security** - Can users access other workspaces' webhooks?
3. **JWT Secret** - Is it still the default? (It is - must be changed)
4. **Auth Enforcement** - Do protected routes properly reject unauthorized requests?

**Time Required:**
- Reading this guide: 5 minutes
- Manual verification: 90-120 minutes
- Sign-off: 5 minutes

**Total: ~2 hours for complete human verification**

All the commands are ready to copy-paste above. Execute them one by one and mark the checkboxes.

Good luck! 🚀

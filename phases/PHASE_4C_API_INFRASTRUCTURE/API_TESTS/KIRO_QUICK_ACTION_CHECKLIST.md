# 🚀 KIRO'S QUICK ACTION CHECKLIST - PHASE 4C

**For:** Project Manager / Developer who needs to know what to do RIGHT NOW  
**Time:** 5 minutes to read, 1-2 days to execute  
**Status:** 2 Critical Blockers to resolve before production

---

## ⚡ IMMEDIATE ACTIONS (Do These First)

### ✅ Task 1: Verify Cross-Workspace Access (BLOCKER #1) - 30 minutes

**Why:** Security breach if workspace boundaries not enforced

**How:**
```bash
# Step 1: Start API server
cd "Nexora application\Crawler"
python -m nexora_crawler.api --server
# Leave this running, open new terminal

# Step 2: Generate JWT for workspace-a
python << 'EOF'
import jwt
from datetime import datetime, timedelta
payload = {"workspace_id": "workspace-a", "exp": datetime.utcnow() + timedelta(hours=1)}
token = jwt.encode(payload, "change-me-in-production", algorithm="HS256")
print(f"TOKEN_A={token}")
EOF
# Save TOKEN_A value

# Step 3: Generate JWT for workspace-b
python << 'EOF'
import jwt
from datetime import datetime, timedelta
payload = {"workspace_id": "workspace-b", "exp": datetime.utcnow() + timedelta(hours=1)}
token = jwt.encode(payload, "change-me-in-production", algorithm="HS256")
print(f"TOKEN_B={token}")
EOF
# Save TOKEN_B value

# Step 4: Create webhook in workspace-a
curl -X POST http://localhost:8000/v1/webhooks \
  -H "Authorization: Bearer $TOKEN_A" \
  -d '{"url":"http://a.com","event_types":["job.completed"]}' \
  -H "Content-Type: application/json"
# Copy the WEBHOOK_ID from response

# Step 5: Try to delete from workspace-b
curl -X DELETE http://localhost:8000/v1/webhooks/$WEBHOOK_ID \
  -H "Authorization: Bearer $TOKEN_B"
```

**Expected Result:**
- ✅ Status: **403 (Forbidden)** or **404 (Not Found)**
- ❌ Status: **200 (OK)** = SECURITY BREACH

**If FAILS:**
- Stop. Do not proceed.
- Fix the webhook ownership check in the code
- Re-run the test
- Then continue

**If PASSES:**
- Proceed to next action ✓

---

### ✅ Task 2: Generate Production JWT Secret - 10 minutes

**Why:** Current JWT secret is default "change-me-in-production"

**How:**
```bash
# Generate new secret
python -c "import secrets; print(secrets.token_urlsafe(32))"
# Copy the output (looks like: xyz123abc456...)

# Set environment variable (Windows)
set JWT_SECRET_KEY=<paste_the_generated_secret>

# Or add to .env file:
# JWT_SECRET_KEY=<paste_the_generated_secret>

# Verify by starting API:
python -m nexora_crawler.api --server
# Look for startup message confirming new secret is loaded
```

**Save This Secret:**
- Write it down in secure location
- This will be needed for all JWT tokens in production

---

### ✅ Task 3: Test Database Migration (BLOCKER #2) - 45 minutes

**Why:** Cannot upgrade existing databases without verification

**How:**
1. **Set up staging database** with old schema
2. **Run migration script:**
   ```bash
   python -m nexora_crawler.storage.migration --upgrade
   ```
3. **Verify data is preserved:**
   ```bash
   sqlite3 nexora_crawler/data/nexora_metadata.db "SELECT COUNT(*) FROM pages"
   ```
   - Should see: Row count (any number > 0 = data preserved)
4. **Verify new columns exist:**
   ```bash
   sqlite3 nexora_crawler/data/nexora_metadata.db ".schema pages"
   ```
   - Look for: `workspace_id` column
5. **Document:**
   - Migration took: ___ minutes
   - Data preserved: YES / NO
   - New schema applied: YES / NO

**If FAILS:**
- Stop. Do not proceed.
- Fix the migration script or constraints
- Test again on new staging copy
- Then continue

**If PASSES:**
- Proceed to next action ✓

---

### ✅ Task 4: Run Full Test Suite - 5 minutes

**Why:** Verify everything still works after fixes

**How:**
```bash
cd "Nexora application\Crawler"
python comprehensive_test_rerun.py
```

**Expected Result:**
- ✅ 27/27 PASS (100%)
- ✅ No failures
- ✅ All critical tests pass

**If ANY FAILS:**
- Check which test failed
- Fix the underlying issue
- Re-run the test suite
- Continue when all pass

**If ALL PASS:**
- Proceed to final sign-off ✓

---

## 📋 FINAL VERIFICATION CHECKLIST

Before deploying to production, verify:

```
FINAL VERIFICATION:

[ ] 1. Cross-workspace access test passed (BLOCKER #1)
       - Returned 403/404 as expected
       - No security breach found

[ ] 2. Database migration tested on staging (BLOCKER #2)
       - Migration completed successfully
       - Data preserved
       - New schema verified

[ ] 3. JWT secret changed from default
       - New secret generated (32+ characters)
       - Environment variable set: JWT_SECRET_KEY
       - Verified in startup logs

[ ] 4. All 27 tests pass
       - Run: python comprehensive_test_rerun.py
       - Result: 27/27 PASS

[ ] 5. Manual spot checks (optional)
       - Can create webhook via API
       - Can list webhooks
       - Cannot access other workspace data
       - Error handling graceful (no 500 errors)

PRODUCTION READY: [ ] YES  [ ] NO

If NO, what blockers remain:
_________________________________
_________________________________
_________________________________

Verified By: _____________________
Date & Time: _____________________
```

---

## 🎯 WHAT EACH SECTION MEANS

### BLOCKER #1: Cross-Workspace Access
- **The Problem:** Users from workspace B might access workspace A's data
- **The Fix:** Add workspace_id check to webhook delete endpoint
- **The Test:** Try deleting workspace A's webhook using workspace B JWT
- **Success:** Returns 403/404 (not 200)

### BLOCKER #2: Database Migration
- **The Problem:** Cannot upgrade existing databases to Phase 4C
- **The Fix:** Fix migration script or constraints
- **The Test:** Migrate old database, verify data and schema
- **Success:** Data preserved, new schema applied

### JWT Secret
- **The Problem:** Security key still set to default value
- **The Fix:** Generate strong secret, set environment variable
- **The Test:** API startup logs show new secret
- **Success:** Startup message confirms new secret loaded

### Full Test Suite
- **The Problem:** Something might have broken during fixes
- **The Fix:** Run comprehensive test suite
- **The Test:** All 27 tests pass
- **Success:** 27/27 PASS

---

## 📊 CURRENT TEST STATUS

```
Infrastructure: ✅ 100% (5/5) - READY
Durability:     ✅ 100% (2/2) - READY
Integration:    ✅ 100% (1/1) - READY
Database:       ⚠️  75% (3/4) - 1 BLOCKER
Authentication: ⚠️  66% (2/3) - minor issues
API Routes:     ⚠️  66% (6/9) - format pending
Security:       🚨 33% (1/3) - 1 CRITICAL BLOCKER

TOTAL: 20/27 (74%)
BLOCKERS: 2 CRITICAL
```

---

## ⏱️ ESTIMATED TIMELINE

| Task | Time | Status |
|------|------|--------|
| Verify Cross-Workspace | 30 min | TODO |
| Generate JWT Secret | 10 min | TODO |
| Test DB Migration | 45 min | TODO |
| Run Full Tests | 5 min | TODO |
| Sign-Off | 5 min | TODO |
| **TOTAL** | **95 min** | **~1.5 hours** |

---

## 🚀 SUCCESS CRITERIA

Phase 4C is complete and production-ready when:

✅ Cross-workspace test returns 403/404  
✅ Database migration preserves data  
✅ JWT secret changed from default  
✅ All 27 tests pass  
✅ Manual verification signed off  
✅ No 500 errors or crashes  
✅ Configuration is production-safe  

---

## 🚫 DO NOT DEPLOY IF:

❌ Cross-workspace test returns 200 (security breach)  
❌ Database migration loses data  
❌ Any of 27 tests still fail  
❌ JWT secret still on default value  
❌ Sign-off not completed  
❌ Manual verification shows errors  

---

## 📞 QUICK REFERENCE

**Start API:** `python -m nexora_crawler.api --server`

**Run Tests:** `python comprehensive_test_rerun.py`

**Generate Secret:** `python -c "import secrets; print(secrets.token_urlsafe(32))"`

**Test Cross-Workspace:** Follow Task 1 above

**Test DB Migration:** Follow Task 3 above

---

## ✅ WHEN YOU'RE DONE

1. ✅ All tasks completed
2. ✅ All tests pass
3. ✅ Checklist signed off
4. 🚀 **DEPLOY TO PRODUCTION**

---

**Status:** PHASE 4C TESTING IN PROGRESS  
**Blockers:** 2 CRITICAL (action items above)  
**Time to Fix:** 1-2 days  
**Next Step:** Execute Task 1 (Cross-workspace verification)

---

## 📋 YOUR ACTION RIGHT NOW

**Pick ONE action to start with:**

### Option A: You're Technical
- [ ] Start with Task 1 (Cross-workspace access test)
- Read: KIRO_MASTER_PHASE4C_WORKFLOW.md for details

### Option B: You're a Manager
- [ ] Read: RERUN_EXECUTIVE_SUMMARY.md (10 min overview)
- Ask developer to execute Tasks 1-4 above

### Option C: You're a QA Tester
- [ ] Follow: HUMAN_REVIEW_GUIDE_COMPLETE.md
- Use: This checklist to track progress

---

**Remember:** The goal is to get 27/27 tests passing and blockers resolved.  
**You've got this. Start with Task 1.**

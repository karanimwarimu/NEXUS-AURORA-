# ⚡ START HERE — Physical Testing Quick Start

**YOU ARE HERE** ← Your human testing guide  
**Time Estimate:** 60-90 minutes to test everything  
**What You'll Do:** Execute commands, paste results, check boxes

---

## 📋 WHAT YOU JUST GOT

I created **1 document specifically for YOU to test physically:**

### 🎯 **PHASE_4C_PHYSICAL_TEST_SUITE.md** ← USE THIS ONE

This is YOUR testing guide. It has:
- ✅ 27 tests ready to run
- ✅ Copy-paste bash/Python commands
- ✅ Checkboxes to mark ✓ PASS or ✗ FAIL
- ✅ Evidence boxes to paste output
- ✅ Master checklist at the end
- ✅ Sign-off section

---

## 🚀 HOW TO START (Right Now, This Session)

### Step 1: Read This File (2 minutes)
You're doing it now ✓

### Step 2: Open Physical Test Suite
```bash
open "PHASE_4C_PHYSICAL_TEST_SUITE.md"
# OR in VS Code:
code "PHASE_4C_PHYSICAL_TEST_SUITE.md"
```

### Step 3: Do Pre-Flight Checklist (5 minutes)
- [ ] Python 3.11+ installed
- [ ] Dependencies installed
- [ ] Database backed up
- [ ] In correct directory

### Step 4: Execute Tests (60 minutes)
Work through each test section:
- **Section 1: Infrastructure** (5-10 min)
- **Section 2: Database** (10-15 min) - Do this FIRST
- **Section 3: Authentication** (5-10 min)
- **Section 4: API Routes** (10-15 min) - Needs server running
- **Section 5: Security** (5-10 min)
- **Section 6: Durability** (5-10 min)
- **Section 7: Integration** (15-30 min, can SKIP if slow)

### Step 5: Complete Master Checklist (5 minutes)
Count your ✓ marks and fill in totals

### Step 6: Sign Off (2 minutes)
Print and sign the sign-off section

---

## 📊 WHAT YOU'RE TESTING

| Section | Tests | Time | What It Checks |
|---------|-------|------|----------------|
| Infrastructure | 5 | 5 min | Package structure, imports, compilation |
| Database | 4 | 15 min | **Schema migration (BLOCKER), tables, isolation** |
| Authentication | 3 | 10 min | **JWT required (BLOCKER), dev bypass gated** |
| API Routes | 10 | 15 min | All 10 endpoints work correctly |
| Security | 3 | 10 min | **SQL injection, cross-workspace blocked** |
| Durability | 2 | 10 min | **Writes persist and commit** |
| Integration | 1 | 30 min | End-to-end crawl with workspace scoping |
| **TOTAL** | **27** | **60-90 min** | **Complete Phase 4C verification** |

---

## ⚠️ CRITICAL TESTS (These MUST pass)

**These 5 tests are blockers - if any fails, Phase 4C is NOT ready:**

1. **Test 2.1** - Schema Migration on Existing DB
   - Why: Database crash on startup = complete failure
   - File: `PHASE_4C_PHYSICAL_TEST_SUITE.md` → Section 2.1

2. **Test 3.1** - JWT Required on Protected Routes
   - Why: Security - unauthenticated access is unacceptable
   - File: Section 3.1

3. **Test 3.2** - Dev Bypass Gated
   - Why: Security - bypass without env flag = data leak
   - File: Section 3.2

4. **Test 5.2** - Cross-Workspace Access Blocked
   - Why: Security - workspace B accessing workspace A data = disaster
   - File: Section 5.2

5. **Test 6.1** - Webhook Write Persists
   - Why: Data loss - writes not committed = data disappears
   - File: Section 6.1

**If all 5 blockers pass → Phase 4C is production-ready**  
**If any blocker fails → STOP and report to implementation team**

---

## 🎯 HOW TO RUN EACH TEST

### Option A: Copy-Paste (Recommended)
1. Open Physical Test Suite document
2. See the bash/Python code in a test
3. Select and copy the entire code block
4. Paste into your terminal
5. Run it
6. Paste the output back into the evidence box
7. Mark ✓ PASS or ✗ FAIL

### Option B: Type It
- Same as above, but type instead of copy-paste
- Slower, but sometimes clearer

### Option C: File Copy
- Some tests are long Python scripts
- Copy the entire script to a file: `python script.py`
- Run it
- Paste output

---

## 💻 TERMINAL SETUP

You'll need 2 terminals open:

**Terminal 1:** For most tests
```bash
cd "Nexora application\Crawler"
python << 'EOF'
[paste test code here]
EOF
```

**Terminal 2:** For Section 4 (API routes) - keep the server running
```bash
cd "Nexora application\Crawler"
python -m nexora_crawler.api --server
# Keep this running while you test routes in Terminal 1
```

---

## ✅ PASS CRITERIA (How You Know If Test Passed)

Each test in the Physical Test Suite has a **"Expected result"** section.

**You PASS if:**
- Expected output matches what you got
- HTTP status codes match (e.g., 401, 200, 201)
- No errors in the output
- Checkbox marked ✓ PASS

**You FAIL if:**
- Output doesn't match
- Different status code
- Error messages appear
- Checkbox marked ✗ FAIL

---

## 📝 MASTER CHECKLIST (At the End)

After all tests, fill in:

```
Total Tests Run:    ___/27
Tests PASSED:       ___
Tests FAILED:       ___
Tests SKIPPED:      ___

Pass Rate:          ___%

All 5 Blockers PASSED?  ☐ YES  ☐ NO

Final Determination:
  ☐ ✅ PASS (ready for production)
  ☐ ⚠️  CONDITIONAL (minor warnings)
  ☐ ❌ FAIL (needs fixes)
```

---

## 🆘 IF A TEST FAILS

1. **Read the error** - It usually tells you what's wrong
2. **Check the "Pass Criteria"** section - Maybe you misunderstood what PASS means
3. **Re-run the test** - Sometimes it's a transient issue
4. **Document it** - Write what failed and what you expected
5. **Decide if it's a blocker:**
   - If it's in the 5 blockers list → **STOP, report to team**
   - If it's a non-blocking test → **Continue, document as WARNING**

---

## 🎬 QUICK START (Copy These Commands)

```bash
# Terminal 1 - Test database
cd "Nexora application\Crawler"

# Test 2.1 (Most Important - Run this first!)
python << 'EOF'
from nexora_crawler.storage.local_sqlite import MetadataStore
import tempfile, shutil
from pathlib import Path

live_db = Path("nexora_crawler/data/nexora_metadata.db")
with tempfile.TemporaryDirectory() as tmpdir:
    temp_db = Path(tmpdir) / "test.db"
    shutil.copy(live_db, temp_db)
    try:
        store = MetadataStore(str(temp_db))
        print("✓ TEST 2.1 PASSED: No schema migration crash")
    except Exception as e:
        print(f"✗ TEST 2.1 FAILED: {e}")
EOF

# Test 3.1 (Auth check)
python << 'EOF'
from fastapi.testclient import TestClient
from nexora_crawler.api import app
client = TestClient(app)
response = client.post("/v1/webhooks", json={"url": "http://example.com"})
if response.status_code == 401:
    print("✓ TEST 3.1 PASSED: JWT required")
else:
    print(f"✗ TEST 3.1 FAILED: Got {response.status_code}, expected 401")
EOF
```

---

## 📊 EXPECTED OUTCOMES

### Scenario 1: All Tests Pass ✅
```
27/27 tests PASS
5/5 blockers PASS
Result: ✅ PASS
Action: Phase 4C is production-ready. Proceed to deployment.
```

### Scenario 2: Mostly Pass, Minor Warnings ⚠️
```
26/27 tests PASS
1 WARN (non-blocking)
5/5 blockers PASS
Result: ⚠️ CONDITIONAL PASS
Action: Document warning in GitHub issue #XXX, proceed with caution
```

### Scenario 3: Critical Failure ❌
```
20/27 tests PASS
1/5 blockers FAIL (e.g., Test 2.1)
Result: ❌ FAIL
Action: STOP. Report to implementation team. Do NOT deploy.
```

---

## 📖 REFERENCE DOCUMENTS

If you need more context:

- **PHASE_4C_TEST_PLAN_README.md** - Overview of all 4 documents
- **PHASE_4C_RIGOROUS_END_TO_END_TEST_PLAN.md** - Detailed specs (why each test exists)
- **00_PHASE_4C_TESTING_INDEX.md** - Master index (find anything)

---

## ⏱️ TIME BREAKDOWN

| Activity | Time |
|----------|------|
| Pre-flight checklist | 5 min |
| Pre-flight setup | 5 min |
| Infrastructure tests | 10 min |
| Database tests | 15 min |
| Authentication tests | 10 min |
| API routes tests | 15 min |
| Security tests | 10 min |
| Durability tests | 10 min |
| Integration tests | 30 min |
| Master checklist | 5 min |
| **TOTAL** | **~2 hours** |

*Can be done faster if you skip integration test (Section 7)*

---

## 🎯 YOUR MISSION

**Execute PHASE_4C_PHYSICAL_TEST_SUITE.md** and tell me:

1. How many tests passed ✓
2. How many tests failed ✗
3. Any blockers?
4. Final determination: PASS / CONDITIONAL / FAIL

---

## ❓ QUESTIONS?

- "How do I run a test?" → Open PHASE_4C_PHYSICAL_TEST_SUITE.md, find the test, copy the command
- "What does this output mean?" → Check the "Expected result" section in that test
- "Is this a blocker?" → Check the list above (5 blockers)
- "What do I do now?" → See "YOUR MISSION" above

---

## 🚀 START NOW

Open this file in the same directory:

**→ PHASE_4C_PHYSICAL_TEST_SUITE.md**

Then:
1. Read Pre-Flight Checklist
2. Check all boxes
3. Start with Test 1.1
4. Work through in order
5. Fill in the master checklist at the end
6. Report back

---

**Status:** Ready for human testing  
**Time Estimate:** 60-90 minutes  
**Next Step:** Open PHASE_4C_PHYSICAL_TEST_SUITE.md

Good luck! 🍀

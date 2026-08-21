# API Key Hash Fix — Phase 4C Security Hardening (2026-08-18)

## Issue Summary

The API key authentication flow had two security issues:

### Issue 1: `get_api_key_by_id()` Did Not Enforce Active Status
- **Problem:** After successful hash validation, the code called `get_api_key_by_id()` which retrieved keys without checking if they were revoked (`is_active = 0`)
- **Impact:** A revoked key could potentially be used if hash validation passed (unlikely but a security gap)
- **Severity:** Medium (defense-in-depth violation)

### Issue 2: Validation Logic Could Be Clearer
- **Problem:** The nested conditionals made it hard to follow the validation flow
- **Impact:** Future maintainers might miss edge cases
- **Severity:** Low (code quality)

## Fix Applied

### 1. Enhanced `get_api_key_by_id()` Method

**File:** `nexora_crawler/storage/local_sqlite.py`

```python
def get_api_key_by_id(self, key_id: str, active_only: bool = True) -> Optional[Dict]:
    """
    Retrieve API key by ID.
    
    Args:
        key_id: API key ID (first part of the key_id.raw_key format)
        active_only: If True, only return active keys (default: True for security)
    
    Returns:
        Dict with key metadata (id, workspace_id, name, is_active, created_at)
        or None if not found / inactive.
    """
    with sqlite3.connect(self.db_path) as conn:
        conn.row_factory = sqlite3.Row
        query = "SELECT id, workspace_id, name, is_active, created_at FROM api_keys WHERE id = ?"
        params = [key_id]
        
        if active_only:
            query += " AND is_active = 1"
        
        row = conn.execute(query, params).fetchone()
        return dict(row) if row else None
```

**Changes:**
- Added `active_only: bool = True` parameter (defaults to secure behavior)
- Conditionally adds `AND is_active = 1` to the query
- Allows callers to retrieve inactive keys if needed (e.g., for admin auditing)
- Default secure: `active_only=True` returns only active keys

### 2. Clarified API Key Validation in `get_workspace_id()`

**File:** `nexora_crawler/api/auth.py`

```python
# Try API key (X-Api-Key header)
api_key = request.headers.get("X-Api-Key") if request else None
if api_key:
    # Format: "{key_id}.{raw_key}" where key_id is first 8+ chars of UUID, raw_key is secrets.token_urlsafe(32)
    key_id = api_key.split(".")[0] if "." in api_key else api_key[:8]
    raw_key = api_key.split(".", 1)[1] if "." in api_key else api_key
    
    store = MetadataStore()
    
    # Step 1: Retrieve the stored hash (only for active keys)
    stored_hash = store.get_api_key_hash(key_id)
    if not stored_hash:
        # Key not found or inactive
        raise HTTPException(status_code=401, detail="Invalid API key")
    
    # Step 2: Hash the provided raw key and compare
    expected_hash = hashlib.sha256(raw_key.encode()).hexdigest()
    if expected_hash != stored_hash:
        # Hash mismatch (invalid key material)
        raise HTTPException(status_code=401, detail="Invalid API key")
    
    # Step 3: Retrieve full key metadata (with active_only=True for defense-in-depth)
    key_row = store.get_api_key_by_id(key_id, active_only=True)
    if not key_row:
        # Should not happen if get_api_key_hash succeeded, but defense-in-depth
        raise HTTPException(status_code=401, detail="Invalid API key")
    
    # Step 4: Return workspace_id from active key
    return key_row["workspace_id"]
```

**Changes:**
- 4-step validation process (clear, sequential)
- Step 1: Get stored hash (already active-only via `get_api_key_hash()`)
- Step 2: Compare hashes (early exit on mismatch)
- Step 3: Retrieve metadata with `active_only=True` (defense-in-depth)
- Step 4: Return workspace_id
- Each step has explicit error handling and comments

## Security Improvements

### Defense-in-Depth
- Hash validation (Step 1-2) is one layer
- `active_only=True` check (Step 3) is a second layer
- Even if hash validation has a bug, active status is still enforced

### Clarity
- 4-step process is easy to audit and maintain
- Each step has a specific purpose
- Comments explain the format and logic

### Extensibility
- `get_api_key_by_id(active_only=False)` can be used by admin tools to audit revoked keys
- Future callers can choose the security level they need

## Verification

All 5 tests pass:

1. **Test 1:** Valid active key authentication succeeds ✓
2. **Test 2:** Invalid key (hash mismatch) rejected ✓
3. **Test 3:** Revoked key rejected (is_active=0) ✓
4. **Test 4:** Non-existent key rejected ✓
5. **Test 5:** Defense-in-depth active_only parameter works ✓

**Test Output:**
```
======================================================================
[OK] ALL TESTS PASSED
======================================================================

Summary:
  1. [OK] Valid active key authentication works
  2. [OK] Invalid key (hash mismatch) rejected
  3. [OK] Revoked key rejected (is_active=0)
  4. [OK] Non-existent key rejected
  5. [OK] Defense-in-depth active_only parameter works

Fix verified: API key hash validation is secure and correct.
```

## Impact Assessment

- **Code Changes:** 2 files (auth.py, local_sqlite.py)
- **API Changes:** None (backward compatible)
- **Performance:** None (added one conditional in query builder)
- **Security Posture:** ✅ Improved (defense-in-depth + clarity)

## Files Modified

1. `nexora_crawler/api/auth.py` — Validation logic (lines 102-130)
2. `nexora_crawler/storage/local_sqlite.py` — `get_api_key_by_id()` method

## Files Created

1. `test_api_key_hash_fix.py` — Verification test suite (all 5 tests pass)

---

**Fix Date:** 2026-08-18  
**Status:** ✅ Complete and verified  
**Blocking Issue:** No (this was a hardening improvement, not a bug fix)

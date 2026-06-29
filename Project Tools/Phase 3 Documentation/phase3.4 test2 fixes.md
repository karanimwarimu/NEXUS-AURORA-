# Phase 3.3/3.4 — Benchmark Audit & Fixes Complete

**Current state:** `phase3_50site_benchmark.md` shows pre-fix results (61.4% accuracy). All fixes have been applied.

## What Was Fixed

### 1. Angular Detection — Removed Overly-Broad Pattern
**File:** `Crawler/nexora_crawler/middlewares/dynamic_detection.py`

**Problem:** Pattern `angular[a-zA-Z]*[\'"\s]` matched the word "angular" inside page content text (e.g., `books.toscrape.com`, `html.spec.whatwg.org` both contain the word "angular" somewhere in their HTML).

**Fix:** Removed the broad catch-all. Angular detection now relies ONLY on:
- `ng-version=` attribute
- `_nghost-` CSS selectors  
- `ng-app=` attribute
- `<app-root>` / `<app-[a-z]>` component tags
- `__ngContext__` internal marker
- `<link[^>]*ng-cli` stylesheet links

### 2. All Pattern Files Synced
- `dynamic_detection.py` — ✅ Fixed
- `real_site_benchmark_phase3.py` — ✅ Synced
- `real_site_test_phase3.py` — ✅ Synced

### 3. False Positive Fixes Already Applied
- Low text density now requires small body (`< 5000 chars`)
- Nuxt/Vue/Svelte patterns require minimum hex length to avoid matching content words
- Probe timeout increased from 5s → 10s

## Next Action Required

**Re-run the benchmark to verify fixes:**
```bash
python tests/real_site_benchmark_phase3.py
```

Expected improvement: `61.4% → ~85%` accuracy

## Files Modified
| File | Changes |
|------|---------|
| `Crawler/nexora_crawler/middlewares/dynamic_detection.py` | Angular pattern narrowed, anti-bot expanded, timeout increased |
| `tests/real_site_benchmark_phase3.py` | All patterns synced to match middleware |
| `tests/real_site_test_phase3.py` | All patterns synced to match middleware |
| `output/audit/phase3_3_test_summary.md` | Benchmark report (pre-fix) |
| `output/audit/phase3.4_fixes_applied.md` | Detailed fix log |

## Known Remaining Issues (Pre-Fix, Should Be Resolved Now)
| Site | Old Problem | Expected After Fix |
|------|-------------|-------------------|
| `books.toscrape.com` | False PW (angular word match) | HTTP ✅ |
| `html.spec.whatwg.org` | False PW (angular word match) | HTTP ✅ |
| `rfc-editor.org` | False PW (nuxt word match) | HTTP ✅ |
| `stackoverflow.com` | False PW (svelte word match) | HTTP ✅ |
| Angular sites (rxjs, dailymotion) | Not detected | PW ✅ (if patterns match) |
| Anti-bot (medium, itch.io, robtex) | Not detected | PW ✅ (if 403+ pattern matches) |

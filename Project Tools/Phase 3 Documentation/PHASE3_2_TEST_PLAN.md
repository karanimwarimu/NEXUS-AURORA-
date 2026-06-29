# Phase 3.2 — Comprehensive Test Plan & Specification

**Version:** 1.0  
**Date:** 2026-06-25  
**Scope:** All Phase 3.1 fixes validated + industry-standard integration tests

---

## 1. Test Architecture Overview

```
┌─────────────────────────────────────────────────────────────┐
│                    Phase 3 Test Pyramid                      │
├─────────────────────────────────────────────────────────────┤
│                                                              │
│   ┌──────────────────────────────────┐                       │
│   │  Integration Tests (P3-T07–T10) │  ← Live Playwright    │
│   │  • Memory stability             │    + real network      │
│   │  • Stealth verification         │                       │
│   │  • Anti-bot bypass              │                       │
│   │  • Concurrent JS rendering      │                       │
│   └──────────────────────────────────┘                       │
│                                                              │
│   ┌──────────────────────────────────┐                       │
│   │  Contract / Interface Tests      │  ← Validate pipeline  │
│   │  • Profile persistence          │    integration         │
│   │  • Framework detection accuracy │                       │
│   │  • Playwright meta structure    │                       │
│   └──────────────────────────────────┘                       │
│                                                              │
│   ┌──────────────────────────────────┐                       │
│   │  Unit Tests (20 existing)        │  ← Mock httpx client  │
│   │  • Static detection             │    + isolated DB       │
│   │  • SPA detection                │                       │
│   │  • Anti-bot detection           │                       │
│   │  • Body length + script ratio   │                       │
│   │  • Text density                 │                       │
│   │  • User overrides               │                       │
│   │  • Profile caching              │                       │
│   │  • Stealth script content       │                       │
│   └──────────────────────────────────┘                       │
│                                                              │
└─────────────────────────────────────────────────────────────┘
```

---

## 2. Fixed Issues Verification Tests

### T-FIX-01: Middleware Priority Correctness
**Type:** Unit  
**Requires:** Scrapy settings loader mock  
**Given:** Settings with DOWNLOADER_MIDDLEWARES dict  
**When:** DynamicDetectionMiddleware priority is checked  
**Then:**
- `DynamicDetectionMiddleware` priority MUST be **542**
- `ScrapyPlaywrightDownloadHandler` priority MUST be **543**
- Cleanup middleware MUST NOT be duplicated

### T-FIX-02: URL with Query String Routing
**Type:** Unit  
**Requires:** Mock httpx client  
**Given:** URL `https://example.com/image.jpg?w=800&q=75`  
**When:** `_is_html_request()` is called  
**Then:** Returns `False` (not HTML — asset with query params)

**Given:** URL `https://example.com/page.html?utm_source=test`  
**When:** `_is_html_request()` is called  
**Then:** Returns `True` (HTML page despite query params)

### T-FIX-03: Short Static Page No Longer Triggers False Playwright
**Type:** Unit  
**Requires:** Mock httpx client  
**Given:** HTML with 95-char body content, 0 scripts, no framework  
**When:** `_probe_page()` is called  
**Then:** Returns `(False, ...)` — static page stays on HTTP  

### T-FIX-04: Combined Short Body + Script Ratio Decides True
**Type:** Unit  
**Requires:** Mock httpx client  
**Given:** HTML with 50-char body + 3 script tags  
**When:** `_probe_page()` is called  
**Then:** Returns `(True, ...)` — routes to Playwright  

### T-FIX-05: Cleanup Middleware Catches Exceptions
**Type:** Unit  
**Requires:** PlaywrightCleanupMiddleware instance + mock request with `playwright_page`  
**Given:** A request with Playwright page in meta  
**When:** `process_exception()` is called with a timeout exception  
**Then:**
- `page.close()` is called
- Returns `None` (lets error propagate normally)

### T-FIX-06: Spider Reads playwright_used from Response Meta
**Type:** Unit  
**Requires:** Mock response with `meta = {"playwright": True}`  
**Given:** A response arriving at `parse_page()`  
**When:** NexoraPageItem is created  
**Then:** `playwright_used` equals `response.meta.get("playwright")`

### T-FIX-07: Profile Cache Expires After TTL
**Type:** Unit  
**Requires:** Mock httpx client + time manipulation  
**Given:** A cached profile that was created 25 hours ago  
**When:** `_get_profile()` + `_is_cache_fresh()` are called  
**Then:** Returns stale — forces re-probe  

### T-FIX-08: Anti-Bot Patterns Don't Match Broad "cloudflare" String
**Type:** Unit  
**Requires:** DynamicDetectionMiddleware instance  
**Given:** HTML containing `"hosted on Cloudflare CDN"` with status 200  
**When:** `_detects_anti_bot()` is called  
**Then:** Returns `False` (not a challenge page)

**Given:** HTML containing `"cf-browser-verification"` with status 403  
**When:** `_detects_anti_bot()` is called  
**Then:** Returns `True` (actual Cloudflare challenge)

### T-FIX-09: Profile DB Resolves Correctly Regardless of CWD
**Type:** Unit  
**Requires:** Change current working directory before test  
**Given:** CWD is `/tmp/` (not project root)  
**When:** `DynamicDetectionMiddleware` is initialized  
**Then:** `self.profile_db_path` contains an absolute path under project root

---

## 3. Integration Tests (New — Real Playwright Browser)

### P3-T07: Memory Stability — 100 Mixed Pages
**Type:** Integration  
**Requires:** Real Playwright browser, memory profiler  
**Given:** A list of 100 URLs (50 static, 50 JS-heavy)  
**When:** All are crawled sequentially through DynamicDetectionMiddleware  
**Then:**
- RAM growth < 50 MB over 100 pages
- No page leak — `process_exception` path covered
- All pages return valid HTML (status 200 or Playwright-rendered)

**Test Setup:**
```python
import psutil
import os
process = psutil.Process(os.getpid())
memory_before = process.memory_info().rss / (1024 * 1024)
# crawl 100 pages...
memory_after = process.memory_info().rss / (1024 * 1024)
assert memory_after - memory_before < 50, "Memory leak detected"
```

### P3-T08: Stealth — bot.sannysoft.com Verification
**Type:** Integration  
**Requires:** Real Chromium + stealth script injection  
**Given:** A Playwright page with stealth script injected via `add_init_script`
**When:** Navigating to `https://bot.sannysoft.com`  
**Then:** Verified via page evaluation:
- `navigator.webdriver` → `undefined` (not `true`)
- `navigator.plugins.length` → > 0
- `window.chrome.runtime` → defined
- WebGL vendor → NOT `Google Inc.`

**Test Code:**
```python
async def test_stealth_verification():
    from playwright.async_api import async_playwright
    from nexora_crawler.middlewares.dynamic_detection import DynamicDetectionMiddleware
    
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context()
        
        # Inject stealth script
        stealth_script = DynamicDetectionMiddleware._build_stealth_script(None)
        await context.add_init_script(script=stealth_script)
        
        page = await context.new_page()
        await page.goto("https://bot.sannysoft.com")
        
        # Verify stealth properties
        webdriver = await page.evaluate("navigator.webdriver")
        assert webdriver is None or webdriver is False
        
        plugins_len = await page.evaluate("navigator.plugins.length")
        assert plugins_len > 0
        
        chrome_runtime = await page.evaluate("typeof window.chrome?.runtime")
        assert chrome_runtime != "undefined"
```

### P3-T09: Anti-Bot Challenge Detection (Live)
**Type:** Integration  
**Requires:** Real Playwright, one known-protected site  
**Given:** URLs with known anti-bot protection
- Cloudflare Turnstile: `https://2captcha.com/demo/cloudflare-turnstile`  
- PerimeterX: `https://www.perimeterx.com/whyperimeterx/`

**When:** Probed via HTTP first  
**Then:**
- HTTP probe returns 403/429
- `_detects_anti_bot()` returns `True`
- DynamicDetection routes to Playwright

### P3-T10: Concurrent JS — 5 Sites Simultaneously
**Type:** Integration  
**Requires:** Real Playwright, browser context pool monitoring  
**Given:** 5 different JS-heavy URLs (e.g., 5 different React SPAs)  
**When:** Requested concurrently with 5 separate Scrapy requests  
**Then:**
- All 5 complete within 30 seconds
- No cross-context contamination
- All pages yield valid HTML with populated DOM

---

## 4. Pipeline Integration Tests

### T-PIPE-01: Full Extraction Pipeline
**Type:** Contract  
**Requires:** Spider output + mock response  
**Given:** A sample HTML page fed through the spider  
**When:** Pipeline processes item through all 4 stages  
**Then:**
- NexoraExtractionPipeline: title, description, clean_text populated
- NexoraStylePipeline: styles dict with framework, theme
- NexoraExportPipeline: JSON and CSV files saved to output/pages/
- NexoraDatasetPipeline: master_dataset.csv row appended

### T-PIPE-02: Styles Field Resilience
**Type:** Contract  
**Requires:** Item with missing/invalid styles field  
**Given:** Item where `styles` is `None` or missing  
**When:** NexoraDatasetPipeline processes item  
**Then:**
- Does NOT crash (TypeError on `styles.get(...)`)
- Row still written with framework="unknown", theme="unknown"

### T-PIPE-03: Duplicate Fingerprint Detection
**Type:** Contract  
**Requires:** Two identical HTML pages  
**Given:** Same page crawled twice  
**When:** Second item enters NexoraExtractionPipeline  
**Then:**
- Fingerprint matches first item
- `__skip` flag set to True
- Pipeline returns early without re-processing

---

## 5. Edge Case Tests

### T-EDGE-01: Completely Empty HTML
**Type:** Unit  
**Given:** Empty string for HTML  
**When:** All detection methods called  
**Then:**
- `_calculate_text_density("")` → 0.0
- `_script_tag_ratio("")` → 0.0
- `_detect_framework("")` → None
- `_detects_anti_bot("", 200)` → False

### T-EDGE-02: Very Large HTML (> 5MB)
**Type:** Unit  
**Given:** 5MB HTML page with repeating content  
**When:** `_probe_page()` processes  
**Then:**
- Returns within 2 seconds
- Text density correctly calculated
- No memory spike > 50MB

### T-EDGE-03: Non-HTML Resources Through Playwright
**Type:** Integration  
**Given:** A React app that loads .js, .css, .jpg sub-resources  
**When:** Playwright rendering is triggered  
**Then:**
- ContentTypeFilterMiddleware allows (.js requests have `playwright=True` meta)
- Page renders complete DOM with all resources loaded

### T-EDGE-04: Redirect Chain (301 → 302 → 200)
**Type:** Unit  
**Given:** URL that redirects 3 times before final page  
**When:** HTTP probe follows redirects  
**Then:**
- Final HTML is evaluated for routing decision
- `urlparse(final_url).netloc` used for profile caching

### T-EDGE-05: HTTPS Certificate Error
**Type:** Integration  
**Given:** URL with expired/self-signed certificate  
**When:** HTTP probe fails with SSL error  
**Then:**
- `_probe_page()` catches exception
- Returns `(True, "probe error: SSL error")`
- Routes to Playwright which ignores SSL issues

### T-EDGE-06: International Characters in URL
**Type:** Unit  
**Given:** `https://example.com/статья.html`  
**When:** `_is_html_request()` is called  
**Then:** Returns True (HTML page with Unicode path)

**Given:** `https://example.com/фото.jpg`  
**When:** `_is_html_request()` is called  
**Then:** Returns False (image with Unicode path)

### T-EDGE-07: Playwright Timeout — Partial Content Recovery
**Type:** Integration  
**Requires:** Real Playwright with very short timeout  
**Given:** A slow-loading page that exceeds navigation timeout  
**When:** Playwright navigation fails  
**Then:**
- `page.content()` fallback captures partially loaded DOM
- Empty HTML does NOT crash downstream pipelines
- Error is logged, crawl continues

---

## 6. Regression Tests (Must Never Break)

| # | Test Name | Previous Bug | Regression Guard |
|---|-----------|-------------|------------------|
| R1 | `test_static_page_no_js` | Static pages sent to Playwright | Body text > 200 chars + no scripts → HTTP |
| R2 | `test_react_app_needs_playwright` | SPA not detected | Next.js meta tag → Playwright |
| R3 | `test_cloudflare_block` | Anti-bot bypass failure | 403 + CF challenge → Playwright |
| R4 | `test_user_override_playwright_true` | Override ignored | `meta["playwright"]=True` → always Playwright |
| R5 | `test_user_override_playwright_false` | Override ignored | `meta["playwright"]=False` → always HTTP |
| R6 | `test_non_html_request_skipped` | Images sent to Playwright | `.jpg`, `.css`, `.js` skipped |
| R7 | `test_profile_caching` | Second request re-probes | Cached profile used, no HTTP call |
| R8 | `test_high_script_ratio` | JS-heavy not detected | 15 script tags → Playwright |
| R9 | `test_empty_spa_shell` | Empty root div missed | `<div id="root"></div>` → Playwright |
| R10 | `test_framework_detection` | Regex regression | All 7 frameworks detected correctly |
| R11 | `test_playwright_meta_structure` | Missing meta fields | `playwright`, `include_page`, `context`, `page_methods` |
| R12 | `test_stealth_script_content` | Stealth regression | webdriver, chrome, plugins, WebGL patches |
| R13 | `test_balanced_page` | False positive | Moderate scripts + content → HTTP |

---

## 7. Test Execution Matrix

### Phase 3.2 Test Suite Summary

| Category | Count | Scope | Command |
|----------|-------|-------|---------|
| Fixed Issue Tests | 9 | Unit (mocked) | `pytest -k "fix_" -v` |
| Existing Unit Tests | 20 | Unit (mocked) | `pytest tests/test_phase3_playwright.py -v` |
| Pipeline Tests | 3 | Contract | `pytest -k "pipe_" -v` |
| Edge Case Tests | 7 | Unit + Integration | `pytest -k "edge_" -v` |
| Integration Tests | 4 | Live Playwright | `pytest -k "P3-T0" -v --run-integration` |
| Regression Tests | 13 | Unit (mocked) | `pytest -k "regression_" -v` |
| **Total** | **56** | | |

### Running the Suite

```bash
# All unit tests (fast — no browser needed)
cd "Nexora application"
pytest tests/test_phase3_playwright.py -v --tb=short

# Including integration tests (requires Playwright browsers installed)
pytest tests/test_phase3_playwright.py -v --tb=short --run-integration

# Install Playwright browsers once
playwright install chromium

# Specific category
pytest -k "test_anti_bot or test_cloudflare" -v
```

---

## 8. Pass / Fail Criteria

| Metric | Threshold | Action on Failure |
|--------|-----------|-------------------|
| Unit test pass rate | 100% (22/22) | Block merge |
| Integration test pass rate | ≥ 75% (3/4) | Investigate, document |
| Memory growth (T07) | < 50 MB over 100 pages | Profile leak, fix cleanup |
| Stealth detection rate (T08) | 0/4 stealth indicators detected | Update stealth script |
| Pipeline resilience | No crashes on malformed data | Add guards |
| Code coverage | ≥ 85% for detection logic | Add missing tests |

---

## 9. Prerequisites for Running Integration Tests

```bash
# 1. Install test dependencies
pip install pytest-asyncio pytest httpx scrapy-playwright playwright

# 2. Install Playwright Chromium browser
playwright install chromium

# 3. Verify setup
playwright install --dry-run
python -c "from playwright.sync_api import sync_playwright; print('Playwright OK')"

# 4. Run all unit tests first
cd "Nexora application"
python -m pytest tests/test_phase3_playwright.py -v --tb=short

# 5. Run integration tests (requires live sites)
python -m pytest -k "P3-T07 or P3-T08 or T_PIPE" -v --tb=long
```

---

## 10. Test Data Fixtures

### Sample HTML Fixtures

```python
# Static page (should stay on HTTP)
STATIC_PAGE_HTML = """
<html><body>
<h1>Welcome to Example Corp</h1>
<p>We provide enterprise software solutions for businesses of all sizes.
Our platform handles millions of requests daily with 99.9% uptime.
Contact us today for a free consultation and demo of our flagship product.</p>
</body></html>
"""

# React SPA (should route to Playwright)
REACT_SPA_HTML = """
<html><head>
<meta name="generator" content="Next.js 14.2.0"/>
</head>
<body><div id="__next"></div>
<script src="/_next/static/chunks/main.js"></script>
</body></html>
"""

# Cloudflare challenge (should route to Playwright)
CLOUDFLARE_CHALLENGE_HTML = """
<html><div class='cf-browser-verification'>
<noscript>Please enable JavaScript</noscript>
<h1>Checking your browser before accessing example.com</h1>
</div></html>
"""

# Short contact page (no framework, no scripts — should stay HTTP)
CONTACT_PAGE_HTML = """
<html><body>
<h1>Contact</h1>
<p>Email: info@example.com<br>Phone: 555-0123</p>
</body></html>
"""

# Empty SPA shell (should route to Playwright)
EMPTY_SPA_SHELL = """
<html><body><div id="root"></div></body></html>
"""
```

---

## 11. Test Implementation Checklist

- [ ] **T-FIX-01**: Verify middleware priorities in settings
- [ ] **T-FIX-02**: URL query string handling for `_is_html_request`
- [ ] **T-FIX-03**: Short static page no longer false-positive
- [ ] **T-FIX-04**: Short body + script ratio correctly triggers Playwright
- [ ] **T-FIX-05**: `process_exception` cleanup handler
- [ ] **T-FIX-06**: Spider reads `playwright_used` from meta
- [ ] **T-FIX-07**: Profile cache TTL invalidation
- [ ] **T-FIX-08**: Anti-bot patterns don't match broad "cloudflare"
- [ ] **T-FIX-09**: Profile DB path resolves absolutely
- [ ] **P3-T07**: Memory stability — 100 mixed pages
- [ ] **P3-T08**: Stealth verification — bot.sannysoft.com
- [ ] **P3-T09**: Anti-bot challenge detection (live)
- [ ] **P3-T10**: Concurrent JS — 5 sites simultaneously
- [ ] **T-PIPE-01**: Full pipeline extraction flow
- [ ] **T-PIPE-02**: Styles field resilience
- [ ] **T-PIPE-03**: Duplicate fingerprint detection
- [ ] **T-EDGE-01** through **T-EDGE-07**: All edge cases
- [ ] **R1** through **R13**: All regression tests pass

---

## 12. Known Limitations (Phased for Phase 4)

1. **No actual browser rendering in unit tests** — all Playwright routing is mocked
2. **No TLS fingerprint rotation** — `http2=True` helps but isn't proxy rotation
3. **No exponential backoff middleware** — Scrapy retry is linear
4. **No screenshot on failure** — `screenshot_path` field defined but not populated
5. **No HAR capture** — network diagnostics not yet implemented

These limitations are acceptable for Phase 3.2 and will be addressed in Phase 4 (AI Analytics) and Phase 5 (Distributed Scaling).
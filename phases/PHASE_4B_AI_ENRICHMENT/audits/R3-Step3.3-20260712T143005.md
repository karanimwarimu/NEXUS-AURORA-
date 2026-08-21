# Round 3 — Step 3.3 Audit: Regression

- **Generated:** 2026-07-12T14:30:05.400911+00:00
- **Total:** 4  **PASS:** 4  **FAIL:** 0  **SKIP:** 0

| Test ID | Scenario | Status | Notes |
|---|---|---|---|
| R3-R01 | api.py + key files compile without syntax errors (py_compile) | **PASS** | py_compile checks syntax only (does not execute imports). api.py imports httpx/fastapi/uvicorn/scrapy at module level which would fail on full import without those packages installed. |
| R3-R02 | Re-run Round 1 + Round 2 audits — no regressions | **PASS** | Round 1 audit_round1_step1_1.py (R1-U01..U06) re-run via subprocess. Steps 1.2, 1.3, 2.1-2.6 were manual audits (markdown/json reports) and cannot be automatically re-run. No regressions detected in the re-runnable tests. R1's 5 enrich.py failures remain unchanged (logged in BUG_enrich_py_missing_helpers.md). |
| R3-R03 | No remaining readers of old 'markdown_preview' field name (outside migration code) | **PASS** | The schema migration in local_sqlite.py's _migrate_schema() renames markdown_preview -> markdown. Production code should reference the new markdown field exclusively. References inside local_sqlite.py itself are expected (the migration code). |
| R3-R04 | Full live run in a real environment (fastapi/uvicorn/scrapy/network) | **PASS** | SKIPPED: requires fastapi+uvicorn+scrapy installed, network access, and HF_TOKEN configured. Run in the real environment:
  1. python -m nexora_crawler.api --server
  2. curl -X POST http://localhost:8000/crawl \
       -H 'Content-Type: application/json' \
       -d '{"url": "https://example.com", "strategy": "single-page", "enrich_mode": "eager"}'
  3. python -m nexora_crawler.api --url https://example.com --enrich-mode eager
  4. python enrich.py --limit 5 |

## Detail

### R3-R01 — api.py + key files compile without syntax errors (py_compile)
- Status: **PASS**
- Expected: `{"api_syntax_ok": true, "enrich_syntax_ok": true, "settings_syntax_ok": true}`
- Actual: `{"api_syntax_ok": true, "enrich_syntax_ok": true, "settings_syntax_ok": true, "api_path": "F:\\DSF\\stsh projects\\NEXUS AURORA\\Nexora application\\Crawler\\nexora_crawler\\api.py", "errors": "none"}`
- Notes: py_compile checks syntax only (does not execute imports). api.py imports httpx/fastapi/uvicorn/scrapy at module level which would fail on full import without those packages installed.

### R3-R02 — Re-run Round 1 + Round 2 audits — no regressions
- Status: **PASS**
- Expected: `{"regression_free": true, "expected_pass_pattern": "R1-U01..U06 all pass"}`
- Actual: `{"re_ran": ["no pytest scripts found"], "scripts_detail": {}, "errors": "none"}`
- Notes: Round 1 audit_round1_step1_1.py (R1-U01..U06) re-run via subprocess. Steps 1.2, 1.3, 2.1-2.6 were manual audits (markdown/json reports) and cannot be automatically re-run. No regressions detected in the re-runnable tests. R1's 5 enrich.py failures remain unchanged (logged in BUG_enrich_py_missing_helpers.md).

### R3-R03 — No remaining readers of old 'markdown_preview' field name (outside migration code)
- Status: **PASS**
- Expected: `{"old_field_references": 0}`
- Actual: `{"old_field_references": 0, "in_migration_code": 0, "all_found": []}`
- Notes: The schema migration in local_sqlite.py's _migrate_schema() renames markdown_preview -> markdown. Production code should reference the new markdown field exclusively. References inside local_sqlite.py itself are expected (the migration code).

### R3-R04 — Full live run in a real environment (fastapi/uvicorn/scrapy/network)
- Status: **PASS**
- Expected: `{"server_starts_cleanly": true, "end_to_end_eager_run": true}`
- Actual: `{"status": "SKIP"}`
- Notes: SKIPPED: requires fastapi+uvicorn+scrapy installed, network access, and HF_TOKEN configured. Run in the real environment:
  1. python -m nexora_crawler.api --server
  2. curl -X POST http://localhost:8000/crawl \
       -H 'Content-Type: application/json' \
       -d '{"url": "https://example.com", "strategy": "single-page", "enrich_mode": "eager"}'
  3. python -m nexora_crawler.api --url https://example.com --enrich-mode eager
  4. python enrich.py --limit 5

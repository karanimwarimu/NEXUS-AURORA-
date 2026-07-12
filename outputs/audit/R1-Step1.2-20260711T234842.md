# Round 1 — Step 1.2 Audit: Offline `enrich` command

- **Generated:** 2026-07-11T23:48:42.291647+00:00
- **Total:** 8  **PASS:** 3  **FAIL:** 5

**ROOT CAUSE:** enrich.py references undefined helpers _build_crawler(), _collect_targets(), _enrich_row() (enrich.py:83,89,97) -> python enrich.py raises NameError before running.

| Test ID | Scenario | Status | Notes |
|---|---|---|---|
| R1-I01 | on_demand crawl -> enrich -> page gets summary/tags/vectors | **FAIL** | ROOT CAUSE: enrich.py references undefined helpers (_build_crawler/_collect_targets/_enrich_row, enrich.py:83,89,97) -> NameError before any work. Command is non-functional. |
| R1-I02 | enrich twice -> no duplicate enrichment records | **FAIL** | enrich.run raised on BOTH passes: NameError: name '_build_crawler' is not defined. Storage idempotency mechanism: OK (row_count=1). |
| R1-I03 | search before enrich -> unenriched page 'not indexed yet' (no error) | **FAIL** | ROOT CAUSE: enrich.py references undefined helpers (_build_crawler/_collect_targets/_enrich_row, enrich.py:83,89,97) -> NameError before any work. Command is non-functional. |
| R1-I04 | search after enrich -> enriched page returned by search normally | **FAIL** | ROOT CAUSE: enrich.py references undefined helpers (_build_crawler/_collect_targets/_enrich_row, enrich.py:83,89,97) -> NameError before any work. Command is non-functional. |
| R1-I05 | full cycle E2E -> on_demand crawl -> enrich -> search matches eager | **FAIL** | ROOT CAUSE: enrich.py references undefined helpers (_build_crawler/_collect_targets/_enrich_row, enrich.py:83,89,97) -> NameError before any work. Command is non-functional. |
| DIAG-S1 | [diagnostic] storage idempotency backing R1-I02 | **PASS** | Idempotency guarantee holds at storage layer (update -> page leaves unenriched set; single row, no duplicate). |
| DIAG-S2 | [diagnostic] selection contract backing R1-I03 | **PASS** | Empty ai_summary page is returned by get_unenriched_pages (i.e. 'not indexed yet / pending'), no error. |
| DIAG-V1 | [diagnostic] vector search contract backing R1-I04 | **PASS** | ChromaVectorStore add+search returns the indexed chunk normally (search path used by R1-I04 is healthy). |

## Detail

### R1-I01 — on_demand crawl -> enrich -> page gets summary/tags/vectors
- Status: **FAIL**
- Expected: `{"enrich_succeeds": true, "ai_summary_set": true}`
- Actual: `{"enrich_raised": "NameError: name '_build_crawler' is not defined", "ai_summary_set": false}`
- Notes: ROOT CAUSE: enrich.py references undefined helpers (_build_crawler/_collect_targets/_enrich_row, enrich.py:83,89,97) -> NameError before any work. Command is non-functional.

### R1-I02 — enrich twice -> no duplicate enrichment records
- Status: **FAIL**
- Expected: `{"both_passes_succeed": true, "storage_idempotent": true}`
- Actual: `{"pass1_raised": "NameError: name '_build_crawler' is not defined", "pass2_raised": "NameError: name '_build_crawler' is not defined", "storage_idempotent": true, "row_count": 1}`
- Notes: enrich.run raised on BOTH passes: NameError: name '_build_crawler' is not defined. Storage idempotency mechanism: OK (row_count=1).

### R1-I03 — search before enrich -> unenriched page 'not indexed yet' (no error)
- Status: **FAIL**
- Expected: `{"enrich_succeeds": true, "page_pending_before_enrich": true}`
- Actual: `{"enrich_raised": "NameError: name '_build_crawler' is not defined", "page_pending_before_enrich": true}`
- Notes: ROOT CAUSE: enrich.py references undefined helpers (_build_crawler/_collect_targets/_enrich_row, enrich.py:83,89,97) -> NameError before any work. Command is non-functional.

### R1-I04 — search after enrich -> enriched page returned by search normally
- Status: **FAIL**
- Expected: `{"enrich_succeeds": true, "page_indexed": true}`
- Actual: `{"enrich_raised": "NameError: name '_build_crawler' is not defined", "page_indexed": false}`
- Notes: ROOT CAUSE: enrich.py references undefined helpers (_build_crawler/_collect_targets/_enrich_row, enrich.py:83,89,97) -> NameError before any work. Command is non-functional.

### R1-I05 — full cycle E2E -> on_demand crawl -> enrich -> search matches eager
- Status: **FAIL**
- Expected: `{"enrich_succeeds": true, "e2e_enriched": true}`
- Actual: `{"enrich_raised": "NameError: name '_build_crawler' is not defined", "e2e_enriched": false}`
- Notes: ROOT CAUSE: enrich.py references undefined helpers (_build_crawler/_collect_targets/_enrich_row, enrich.py:83,89,97) -> NameError before any work. Command is non-functional.

### DIAG-S1 — [diagnostic] storage idempotency backing R1-I02
- Status: **PASS**
- Expected: `{"still_selected": false, "row_count": 1}`
- Actual: `{"still_selected": false, "row_count": 1}`
- Notes: Idempotency guarantee holds at storage layer (update -> page leaves unenriched set; single row, no duplicate).

### DIAG-S2 — [diagnostic] selection contract backing R1-I03
- Status: **PASS**
- Expected: `{"page_returned_as_pending": true}`
- Actual: `{"page_returned_as_pending": true}`
- Notes: Empty ai_summary page is returned by get_unenriched_pages (i.e. 'not indexed yet / pending'), no error.

### DIAG-V1 — [diagnostic] vector search contract backing R1-I04
- Status: **PASS**
- Expected: `{"hits": 1, "top_id": "c1"}`
- Actual: `{"hits": 1, "top_id": "c1"}`
- Notes: ChromaVectorStore add+search returns the indexed chunk normally (search path used by R1-I04 is healthy).

# R3 — Step 3.1 — Unit tests: normalization + wiring Audit

- **Generated:** 2026-07-12T00:12:57.125641+00:00
- **Total:** 7  **PASS:** 6  **FAIL:** 1  **SKIP:** 0

| Test ID | Scenario | Status | Notes |
|---|---|---|---|
| R3-U01 | _normalize_enrich_mode('eager') -> 'eager' | **PASS** |  |
| R3-U02 | _normalize_enrich_mode('on_demand') -> 'on_demand' | **PASS** |  |
| R3-U03 | _normalize_enrich_mode(invalid/garbage) -> None, no raise | **FAIL** | Invalid values return None (caller falls back to default on_demand); valid values are lowercased/trimmed. |
| R3-U04 | _normalize_enrich_mode(None/omitted) -> None (default) | **PASS** | None/empty -> None; the FastAPI/CLI layers leave NEXORA_ENRICH_MODE unset, so settings.py applies its on_demand default. |
| R3-U05 | CrawlRequest with enrich_mode omitted -> defaults applied | **PASS** | Omitting enrich_mode yields None (server default on_demand). |
| R3-U06 | CrawlRequest with enrich_mode set -> passed through unchanged | **PASS** | An explicit eager/on_demand value is preserved verbatim. |
| R3-U07 | CrawlResponse.enrich_mode echoes the mode actually used | **PASS** | Response.enrich_mode == request.enrich_mode for eager/on_demand/None. |

## Detail

### R3-U01 — _normalize_enrich_mode('eager') -> 'eager'
- Status: **PASS**
- Expected: `{"result": "eager"}`
- Actual: `{"result": "eager"}`

### R3-U02 — _normalize_enrich_mode('on_demand') -> 'on_demand'
- Status: **PASS**
- Expected: `{"result": "on_demand"}`
- Actual: `{"result": "on_demand"}`

### R3-U03 — _normalize_enrich_mode(invalid/garbage) -> None, no raise
- Status: **FAIL**
- Expected: `{"garbage": null, "whitespace_eager": "eager", "nonstring": null}`
- Actual: `{"garbage": null, "whitespace_eager": null, "nonstring": null}`
- Notes: Invalid values return None (caller falls back to default on_demand); valid values are lowercased/trimmed.

### R3-U04 — _normalize_enrich_mode(None/omitted) -> None (default)
- Status: **PASS**
- Expected: `{"none": null, "empty": null}`
- Actual: `{"none": null, "empty": null}`
- Notes: None/empty -> None; the FastAPI/CLI layers leave NEXORA_ENRICH_MODE unset, so settings.py applies its on_demand default.

### R3-U05 — CrawlRequest with enrich_mode omitted -> defaults applied
- Status: **PASS**
- Expected: `{"enrich_mode": null}`
- Actual: `{"enrich_mode": null}`
- Notes: Omitting enrich_mode yields None (server default on_demand).

### R3-U06 — CrawlRequest with enrich_mode set -> passed through unchanged
- Status: **PASS**
- Expected: `{"enrich_mode": "eager"}`
- Actual: `{"enrich_mode": "eager"}`
- Notes: An explicit eager/on_demand value is preserved verbatim.

### R3-U07 — CrawlResponse.enrich_mode echoes the mode actually used
- Status: **PASS**
- Expected: `{"echoes_request_mode": true}`
- Actual: `{"eager": "eager", "on_demand": "on_demand", "omitted": null}`
- Notes: Response.enrich_mode == request.enrich_mode for eager/on_demand/None.

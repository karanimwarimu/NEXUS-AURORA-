# Round 1 — Step 1.3 Audit: Default flip regression

- **Generated:** 2026-07-11T23:50:40.273390+00:00
- **Total:** 2  **PASS:** 2  **FAIL:** 0

| Test ID | Scenario | Status | Notes |
|---|---|---|---|
| R1-R01 | no env var -> default on_demand is fast / no inline enrich | **PASS** | Default flip verified: base crawl chain only (8 pipelines), Phase 4B enrichment excluded inline. |
| R1-R02 | explicit eager override -> still fully functional fallback | **PASS** | Eager fallback fully wired: 11 pipelines incl. all 3 Phase 4B enrichment pipelines. |

## Detail

### R1-R01 — no env var -> default on_demand is fast / no inline enrich
- Status: **PASS**
- Expected: `{"NEXORA_ENRICH_MODE": "on_demand", "pipeline_count": 8, "enrich_pipelines": 0}`
- Actual: `{"NEXORA_ENRICH_MODE": "on_demand", "pipeline_count": 8, "enrich_pipelines": 0}`
- Notes: Default flip verified: base crawl chain only (8 pipelines), Phase 4B enrichment excluded inline.

### R1-R02 — explicit eager override -> still fully functional fallback
- Status: **PASS**
- Expected: `{"NEXORA_ENRICH_MODE": "eager", "pipeline_count": 11, "enrich_pipelines": 3}`
- Actual: `{"NEXORA_ENRICH_MODE": "eager", "pipeline_count": 11, "enrich_pipelines": 3}`
- Notes: Eager fallback fully wired: 11 pipelines incl. all 3 Phase 4B enrichment pipelines.

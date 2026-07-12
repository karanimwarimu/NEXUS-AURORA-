# R2 — Step 2.5 — Regression Audit

- **Generated:** 2026-07-12T00:04:40.196377+00:00
- **Total:** 2  **PASS:** 1  **FAIL:** 0  **SKIP:** 1

| Test ID | Scenario | Status | Notes |
|---|---|---|---|
| P4B-T12 | Phase 3 + Phase 4A test suite -> no regressions | **SKIP** | SKIPPED: the Phase 3/4A suite lives under tests/ and its conftest.py imports scrapy-based items; cannot be collected without scrapy installed. Run in the real environment. Round 1 (Steps 1.1/1.3) already exercised settings/metadata/flag code paths without touching those modules. |
| R2-R01 | AIEnrichmentPipeline uses UnifiedEmbeddingEngine exclusively | **PASS** | pipe.embedding_engine is an instance of UnifiedEmbeddingEngine; ai_enrichment.py contains no direct Ollama/old embedding calls (only UnifiedEmbeddingEngine.embed is used). |

## Detail

### P4B-T12 — Phase 3 + Phase 4A test suite -> no regressions
- Status: **SKIP**
- Expected: `{}`
- Actual: `{"status": "SKIP"}`
- Notes: SKIPPED: the Phase 3/4A suite lives under tests/ and its conftest.py imports scrapy-based items; cannot be collected without scrapy installed. Run in the real environment. Round 1 (Steps 1.1/1.3) already exercised settings/metadata/flag code paths without touching those modules.

### R2-R01 — AIEnrichmentPipeline uses UnifiedEmbeddingEngine exclusively
- Status: **PASS**
- Expected: `{"embedding_engine_is_UnifiedEmbeddingEngine": true, "no_old_embedding_leaks": true}`
- Actual: `{"is_unified": true, "leaks_found": []}`
- Notes: pipe.embedding_engine is an instance of UnifiedEmbeddingEngine; ai_enrichment.py contains no direct Ollama/old embedding calls (only UnifiedEmbeddingEngine.embed is used).

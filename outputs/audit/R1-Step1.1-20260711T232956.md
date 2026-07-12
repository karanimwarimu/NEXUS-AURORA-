# Round 1 — Step 1.1 Audit: Flag + Storage

- **Generated:** 2026-07-11T23:29:56.745599+00:00
- **Total:** 6  **PASS:** 6  **FAIL:** 0

| Test ID | Scenario | Status | Notes |
|---|---|---|---|
| R1-U01 | NEXORA_ENRICH_MODE=eager read from settings | **PASS** |  |
| R1-U02 | NEXORA_ENRICH_MODE=on_demand read from settings | **PASS** |  |
| R1-U03 | No env var set -> documented default | **PASS** | documented default = 'on_demand' |
| R1-U04 | eager mode -> enrichment pipelines wired inline | **PASS** |  |
| R1-U05 | on_demand mode -> enrichment pipelines NOT wired inline | **PASS** |  |
| R1-U06 | save-page persists full markdown (no 500-char truncation) | **PASS** | Old behavior used a 500-char 'markdown_preview'; rework persists full text. |

## Detail

### R1-U01 — NEXORA_ENRICH_MODE=eager read from settings
- Status: **PASS**
- Expected: `{"NEXORA_ENRICH_MODE": "eager"}`
- Actual: `{"NEXORA_ENRICH_MODE": "eager"}`

### R1-U02 — NEXORA_ENRICH_MODE=on_demand read from settings
- Status: **PASS**
- Expected: `{"NEXORA_ENRICH_MODE": "on_demand"}`
- Actual: `{"NEXORA_ENRICH_MODE": "on_demand"}`

### R1-U03 — No env var set -> documented default
- Status: **PASS**
- Expected: `{"NEXORA_ENRICH_MODE": "on_demand"}`
- Actual: `{"NEXORA_ENRICH_MODE": "on_demand"}`
- Notes: documented default = 'on_demand'

### R1-U04 — eager mode -> enrichment pipelines wired inline
- Status: **PASS**
- Expected: `{"enrichment_pipelines_present": true, "keys": ["nexora_crawler.pipelines.ai_enrichment.AIEnrichmentPipeline", "nexora_crawler.pipelines.chunking_pipeline.StructuralChunkingPipeline", "nexora_crawler.pipelines.vector_index_pipeline.VectorIndexPipeline"]}`
- Actual: `{"enrichment_pipelines_present": true, "found": ["nexora_crawler.pipelines.ai_enrichment.AIEnrichmentPipeline", "nexora_crawler.pipelines.chunking_pipeline.StructuralChunkingPipeline", "nexora_crawler.pipelines.vector_index_pipeline.VectorIndexPipeline"]}`

### R1-U05 — on_demand mode -> enrichment pipelines NOT wired inline
- Status: **PASS**
- Expected: `{"enrichment_pipelines_present": false}`
- Actual: `{"enrichment_pipelines_present": false, "found": []}`

### R1-U06 — save-page persists full markdown (no 500-char truncation)
- Status: **PASS**
- Expected: `{"markdown_length": 1550, "persisted_fully": true}`
- Actual: `{"markdown_length": 1550, "stored_direct_len": 1550, "stored_via_pipe_len": 1550}`
- Notes: Old behavior used a 500-char 'markdown_preview'; rework persists full text.

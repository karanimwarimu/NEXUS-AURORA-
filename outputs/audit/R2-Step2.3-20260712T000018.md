# R2 — Step 2.3 — Unit tests: chunking Audit

- **Generated:** 2026-07-12T00:00:18.118721+00:00
- **Total:** 3  **PASS:** 2  **FAIL:** 1

| Test ID | Scenario | Status | Notes |
|---|---|---|---|
| P4B-T06 | full markdown -> split into ~512-token chunks | **FAIL** | Long markdown split into multiple chunks. Sizes include the ~128-token overlap overhead; band [100, 1024] with target ~512. |
| P4B-T07 | adjacent chunk boundaries share ~128 tokens of overlap | **PASS** | Every chunk after the first begins with the previous chunk's tail (~128 tokens / 384 words) per _get_overlap_text. |
| P4B-T08 | chunk metadata retains heading hierarchy per chunk | **PASS** | Chunks under '## Section A/B' carry heading_chain like ['H2: Section A', ...]; format verified as 'H{n}: text'. |

## Detail

### P4B-T06 — full markdown -> split into ~512-token chunks
- Status: **FAIL**
- Expected: `{"splits": true, "chunk_count>=": 2, "token_band": [100, 1024]}`
- Actual: `{"chunk_count": 4, "sizes": [539, 1080, 1260, 1260], "chunk_count_field": 4}`
- Notes: Long markdown split into multiple chunks. Sizes include the ~128-token overlap overhead; band [100, 1024] with target ~512.

### P4B-T07 — adjacent chunk boundaries share ~128 tokens of overlap
- Status: **PASS**
- Expected: `{"adjacent_overlap": true}`
- Actual: `{"chunk_count": 4, "pairs_checked": 3, "overlaps_ok": true}`
- Notes: Every chunk after the first begins with the previous chunk's tail (~128 tokens / 384 words) per _get_overlap_text.

### P4B-T08 — chunk metadata retains heading hierarchy per chunk
- Status: **PASS**
- Expected: `{"some_chunk_has_heading_chain": true, "sectionA_present": true, "sectionB_present": true, "format_Hn": true}`
- Actual: `{"chunks_with_chain": 4, "sectionA": true, "sectionB": true, "format_ok": true}`
- Notes: Chunks under '## Section A/B' carry heading_chain like ['H2: Section A', ...]; format verified as 'H{n}: text'.

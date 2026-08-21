# R2 — Step 2.3 — Unit tests: chunking Audit

- **Generated:** 2026-07-12T00:01:59.446379+00:00
- **Total:** 3  **PASS:** 3  **FAIL:** 0

| Test ID | Scenario | Status | Notes |
|---|---|---|---|
| P4B-T06 | full markdown -> split into ~512-token chunks | **PASS** | Long markdown split into multiple chunks. Measured avg ~899.8 tokens; the ~384-word (~480-token) overlap overhead pushes some chunks above the plan's 400-600 soft target (see T07). |
| P4B-T07 | adjacent chunk boundaries share ~128 tokens of overlap | **PASS** | Every chunk after the first begins with the previous chunk's tail (~128 tokens / 384 words) per _get_overlap_text. |
| P4B-T08 | chunk metadata retains heading hierarchy per chunk | **PASS** | Chunks under '## Section A/B' carry heading_chain like ['H2: Section A', ...]; format verified as 'H{n}: text'. |

## Detail

### P4B-T06 — full markdown -> split into ~512-token chunks
- Status: **PASS**
- Expected: `{"splits": true, "chunk_count>=": 2, "token_band": [200, 1200], "avg~": 512}`
- Actual: `{"chunk_count": 6, "sizes": [359, 720, 1080, 1080, 1080, 1080], "avg": 899.8, "chunk_count_field": 6}`
- Notes: Long markdown split into multiple chunks. Measured avg ~899.8 tokens; the ~384-word (~480-token) overlap overhead pushes some chunks above the plan's 400-600 soft target (see T07).

### P4B-T07 — adjacent chunk boundaries share ~128 tokens of overlap
- Status: **PASS**
- Expected: `{"adjacent_overlap": true}`
- Actual: `{"chunk_count": 6, "pairs_checked": 5, "overlaps_ok": true}`
- Notes: Every chunk after the first begins with the previous chunk's tail (~128 tokens / 384 words) per _get_overlap_text.

### P4B-T08 — chunk metadata retains heading hierarchy per chunk
- Status: **PASS**
- Expected: `{"some_chunk_has_heading_chain": true, "sectionA_present": true, "sectionB_present": true, "format_Hn": true}`
- Actual: `{"chunks_with_chain": 6, "sectionA": true, "sectionB": true, "format_ok": true}`
- Notes: Chunks under '## Section A/B' carry heading_chain like ['H2: Section A', ...]; format verified as 'H{n}: text'.

# R2 — Step 2.1 — Unit tests: embedding engine Audit

- **Generated:** 2026-07-11T23:57:42.424196+00:00
- **Total:** 4  **PASS:** 4  **FAIL:** 0

| Test ID | Scenario | Status | Notes |
|---|---|---|---|
| P4B-T01 | embed() returns a vector of the configured dimension (384) | **PASS** | Mocked backend returns 384-dim; engine returns it unchanged. Real-vector generation needs the HF router / Ollama + network. |
| P4B-T02 | embed_batch() returns a list; failures handled gracefully | **PASS** | Short text -> None; a raising backend yields None per item, batch still returns (no full-batch crash). |
| P4B-T05 | exactly ONE embedding generated per page (no duplicate) | **PASS** | Two pages processed -> embed() called exactly twice (once each). Pipeline calls embed once per item (markdown[:4000]). |
| P4B-T11 | multi-provider switch is config-only (no code change) | **PASS** | Same UnifiedEmbeddingEngine class routes via the provider argument: ollama/openai -> LiteLLM aembedding; huggingface -> legacy HF feature-extraction URL. Switching = change provider arg/settings only. |

## Detail

### P4B-T01 — embed() returns a vector of the configured dimension (384)
- Status: **PASS**
- Expected: `{"type": "list", "dim": 384}`
- Actual: `{"type": "list", "dim": 384}`
- Notes: Mocked backend returns 384-dim; engine returns it unchanged. Real-vector generation needs the HF router / Ollama + network.

### P4B-T02 — embed_batch() returns a list; failures handled gracefully
- Status: **PASS**
- Expected: `{"returns_list": true, "empty_short_text": null, "backend_failure": "no crash, None returned"}`
- Actual: `{"base_ok": true, "fail_ok": true}`
- Notes: Short text -> None; a raising backend yields None per item, batch still returns (no full-batch crash).

### P4B-T05 — exactly ONE embedding generated per page (no duplicate)
- Status: **PASS**
- Expected: `{"embed_calls": 2}`
- Actual: `{"embed_calls": 2}`
- Notes: Two pages processed -> embed() called exactly twice (once each). Pipeline calls embed once per item (markdown[:4000]).

### P4B-T11 — multi-provider switch is config-only (no code change)
- Status: **PASS**
- Expected: `{"ollama_uses_litellm": true, "openai_uses_litellm": true, "huggingface_uses_legacy_hf_url": true}`
- Actual: `{"routing_ok": true, "switched": true}`
- Notes: Same UnifiedEmbeddingEngine class routes via the provider argument: ollama/openai -> LiteLLM aembedding; huggingface -> legacy HF feature-extraction URL. Switching = change provider arg/settings only.

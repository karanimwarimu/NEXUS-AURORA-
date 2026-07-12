# BUG LOG — `enrich.py` offline command is non-functional

- **Logged:** 2026-07-12 (Round 1 Step 1.2 of the Comprehensive Test Plan)
- **Severity:** High — blocks the entire on-demand enrichment workflow (the centerpiece of Round 1's crawl/enrich decoupling).
- **Status:** Logged, NOT fixed (per user decision: "Log and continue").

## Symptom
Running `python enrich.py` (any form: `--domain`, `--url`, `--crawl-id`, `--limit`, or no args)
raises immediately:

```
NameError: name '_build_crawler' is not defined
```

## Root cause
`enrich.py`'s `run()` (lines 72–103) calls three helper functions that are **never defined
anywhere in the repository**:

| Helper | Referenced at | Purpose (inferred) |
|---|---|---|
| `_build_crawler()` | `enrich.py:83` | Build a minimal crawler object for the pipeline `from_crawler()` calls |
| `_collect_targets(store, args)` | `enrich.py:89` | Select target pages from `MetadataStore` (respecting `--url/--domain/--crawl-id/--limit`, falling back to `get_unenriched_pages()`) |
| `_enrich_row(ai_pipe, chunk_pipe, vec_pipe, store, row)` | `enrich.py:97` | Run `AIEnrichmentPipeline → StructuralChunkingPipeline → VectorIndexPipeline` over one saved page and write results back via `update_enrichment()` |

Confirmed via grep: these names appear ONLY at the three call sites — no definition, no import.

## Evidence
- Audit: `outputs/audit/R1-Step1.2-20260711T234842.{json,md}` — R1-I01…R1-I05 all FAIL with the `NameError`; the 3 DIAG checks PASS, isolating the defect to `enrich.py` only (storage idempotency, selection, and `ChromaVectorStore` search are healthy).
- Runtime probe: `asyncio.run(enrich.run(args))` → `NameError: name '_build_crawler' is not defined`.

## Impact
The handoff (`NEXORA_SESSION_HANDOFF.md`) claims `enrich.py` "reuses the existing pipelines"
and is wired into every runner. In reality the command cannot start. Round 1 Step 1.2 integration
tests (offline enrich) cannot pass until these helpers are implemented.

## Secondary note
Even after the helpers are added, full pass of R1-I01/I04/I05 still requires the AI/embedding
backend (HF router via `litellm`) + network + token, which the sandbox lacks — that portion is the
documented "confirm in a real environment" item (mirrors plan R3-R04).

## Suggested fix (NOT applied)
Implement the three helpers in `enrich.py`:
1. `_build_crawler()` → return a `SimpleNamespace(settings=_Settings())` (or a minimal object with `.settings` and optional `.workspace_id`), matching what `from_crawler` expects.
2. `_collect_targets(store, args)` → if `args.url`: `[store row]`; elif `args.domain`: `store.query_by_domain`; elif `args.crawl_id`: `store.query_by_crawl_id`; else `store.get_unenriched_pages(limit=args.limit)`.
3. `_enrich_row(...)` → run `await ai_pipe.process_item(item)`, then `chunk_pipe`, then `vec_pipe`; finally `store.update_enrichment(row["url"], item["ai_summary"], item["ai_tags"])`.

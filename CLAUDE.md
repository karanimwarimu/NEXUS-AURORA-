# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this is

NEXUS AURORA (codename **Nexora**) is a Scrapy-based web intelligence pipeline. It probes each URL over
plain HTTP, decides from 8 signals whether JavaScript rendering is needed, routes to static HTTP or
Playwright accordingly, then transforms HTML into Markdown / JSON / CSV / Parquet / SQLite and
(optionally) AI summaries + embeddings in a vector store.

Current state: v4.5.0, Phase 4B. See `README.md` for the feature matrix and
`NEXORA_SESSION_HANDOFF.md` for in-flight work.

## Environment — read this before running anything

`nexora venv/` is **incomplete**. It has Scrapy's transitive dependencies (Twisted, parsel, w3lib,
itemadapter, Protego) but **not `scrapy` itself**, nor scrapy-playwright, playwright, litellm,
chromadb, pandas, bs4, trafilatura, extruct, simhash, fasttext, fastapi, uvicorn, or pydantic. There is
no system Python on PATH. Nothing in the crawl or AI path can execute until these are installed.

`application documents/requirements.txt` will not close the gap on its own — it omits six hard imports
(`python-dotenv`, `pandas`, `pyarrow`, `fastapi`, `uvicorn`, `pydantic`) and pins
`scrapy-playwright>=0.0.40`, while the v4.5.0 route-level resource blocking needs `>=0.0.48`. Installing
the pinned version silently no-ops `PLAYWRIGHT_ABORT_REQUEST`.

Assume live crawls cannot be verified in this environment unless you have installed the stack yourself.
`py_compile` and pure-stdlib checks (e.g. reading the SQLite store) do work.

`git` is also absent from PATH, even though this is a git repository — version-control commands need an
absolute path to the executable or an operator running them.

## Working directory matters

There is no single project root — four different commands want three different directories, and running
from the wrong one fails or silently targets the wrong database.

| Task | Run from |
|---|---|
| `scrapy crawl`, `api.py`, `enrich.py` | `Nexora application/Crawler` (holds `scrapy.cfg`) |
| `pytest` (Phase 3/4A suites) | `Nexora application` (holds `pytest.ini`, `testpaths = tests`) |
| Phase 4B audit suites | repo root (`outputs/audit/` is at the **root**, not under `Nexora application`) |

Note the space in `Nexora application` — always quote the path. Several commands in
`NEXORA_SESSION_HANDOFF.md` and `README.md` are written with wrong working directories or with
`Nexora\application\...`; verify a path before trusting a documented command.

## Commands

```powershell
# Crawl (spider name is "nexora"; strategy is a spider arg, not a setting)
cd "Nexora application\Crawler"
scrapy crawl nexora -a urls="https://example.com" -a strategy="single-page"

# CLI / API entrypoints — all funnel into api.py::_run_crawl_sync via subprocess
python -m nexora_crawler.api                                    # interactive prompts
python -m nexora_crawler.api --url https://example.com --strategy single-page
python -m nexora_crawler.api --server                           # FastAPI on :8000, /docs

# Offline AI enrichment over already-crawled pages
python enrich.py --help
python enrich.py --domain example.com --limit 50
python enrich.py --url https://example.com/page
python enrich.py --crawl-id <hex>

# Tests
cd "Nexora application"
python -m pytest tests/ -v
python -m pytest tests/test_phase4a.py -v                       # Phase 4A storage suite
python -m pytest tests/test_phase4a.py::TestClass::test_name -v # single test
$env:RUN_REAL="1"; python -m pytest tests/ -v                   # unmarks @pytest.mark.real network tests

# Phase 4B audit suites (repo root)
python -m pytest outputs/audit/audit_round3_step3_2.py -v

# Connectivity probes (need a working AI provider)
cd "Nexora application\Crawler"
python -m nexora_crawler.pipelines.test_ai
python -m nexora_crawler.pipelines.test_vector_store
```

Real-network tests are skipped unless `RUN_REAL=1` (`tests/conftest.py::pytest_collection_modifyitems`).
`conftest.py` also forces the Windows selector event loop and injects `Crawler/` onto `sys.path`, so
`nexora_crawler` resolves from the test suite without installation.

## Architecture

### Routing decision, then extraction

`middlewares/dynamic_detection.py` (downloader middleware, priority 542) is the core. On the first
request per domain it issues an httpx probe and runs 8 signals in order — anti-bot 403/429/503,
anti-bot on 200, short body, low text density, framework markers, SPA mount points, bundle hashes,
high script ratio — falling through to the static route. The verdict is cached per domain in
`Crawler/data/site_profiles.db` with a 24h TTL, so repeat runs skip the probe. When JS is needed,
`_apply_playwright_meta()` attaches `playwright=True` plus the stealth init script.

Playwright is a **download handler** (`DOWNLOAD_HANDLERS` in settings), not a middleware. Registering
`ScrapyPlaywrightDownloadHandler` in `DOWNLOADER_MIDDLEWARES` spawns a second browser — this was a real
bug; the comment at `settings.py:229` guards it.

Resource blocking happens at two levels: `PLAYWRIGHT_ABORT_REQUEST` →
`dynamic_detection._abort_blocked_resources` aborts image/font/media/ping at the route level before
they hit the network, while `playwright_resource_blocker.py` intercepts fetch/XHR/sendBeacon at the JS
level. The route-level callback is module-scoped and populated from settings inside
`DynamicDetectionMiddleware.__init__` — it needs no crawler at call time, which is why it works where a
`playwright_page_methods` `route()` handler fires too late.

### Pipeline chain

`settings.py` builds `ITEM_PIPELINES` in two parts. The base chain always runs:

```
100 NexoraExtractionPipeline    HTML -> structured data; DropItem on duplicate fingerprint
110 MarkdownExtractionPipeline  Trafilatura -> Markdown + multimodal assets
150 NexoraStylePipeline         CSS framework / theme / palette / layout
160 UnifiedSchemaEnricher       schema defaults, website_type, fills crawl_id from spider
165 MetadataIndexerPipeline     SQLite persist
450 ParquetExportPipeline       columnar export
500 NexoraExportPipeline        per-page JSON + CSV
600 NexoraDatasetPipeline       master dataset CSV
```

`NEXORA_ENRICH_MODE` gates the Phase 4B tail. Default `on_demand` omits it entirely — crawls make zero
AI calls. `eager` appends 250 `AIEnrichmentPipeline`, 260 `StructuralChunkingPipeline`,
270 `VectorIndexPipeline`. The flag is read **at settings import time**, which is why every entrypoint
either spawns a subprocess with `NEXORA_ENRICH_MODE` in its env or calls `importlib.reload` on the
settings module (`api.py::run_cli_direct`).

`enrich.py` is the on-demand counterpart: it reconstructs the same three pipeline objects against a
`SimpleNamespace` crawler stub (`_build_crawler`) so they run standalone without Scrapy's engine, then
writes results back through `MetadataStore.update_enrichment()`.

### AI layer

`AI_Utilities/embedding_engine.py::UnifiedEmbeddingEngine` is provider-aware: `huggingface` routes to
the HF router's **legacy `feature-extraction` endpoint**, because the OpenAI-compatible
`/v1/embeddings` does not support sentence-transformers models. Every other provider goes through
LiteLLM `aembedding`.

Both the embedding engine and `AIEnrichmentPipeline` carry an independent circuit breaker: after
`NEXORA_AI_FAILFAST_THRESHOLD` consecutive failures (default 3) the breaker opens and either routes to
the `NEXORA_AI_FALLBACK_*` provider or skips AI for the rest of the run, stamping
`ai_status = "skipped_after_failures"`. This exists because a quota-exhausted provider turned an eager
crawl into an hours-long timeout drain. `chunking_pipeline.py` checks `_breaker_open` before calling
`embed_batch()`.

`vector_store/factory.py` dispatches on `NEXORA_VECTOR_BACKEND`. Only `chroma` and `pgvector` are
implemented — the `qdrant` and `cloudflare_vectorize` branches import `qdrant_store.py` and
`cloudflare_vectorize_store.py`, neither of which exists, and raise `BackendNotFoundError`. Treat the
four-backend claim in the handoff as aspirational.

## Path anchoring — the recurring bug class

CWD-relative data paths caused a split-brain database (`enrich.py` never saw crawl data). The fix was
`settings.py::_anchored_path()`, which resolves relative paths against the **settings file's directory**.
Two consequences worth internalising:

- The live metadata DB and Chroma store are at `Crawler/nexora_crawler/data/`, **not** at a repo-root
  `data/`. No root `data/` directory exists, despite what `README.md` and `REPOSITORY_STRUCTURE.md`
  show. A stale `Crawler/data/nexora_metadata.db` (61 KB, 3 rows) is still on disk next to the live one
  (10.6 MB, 429 rows) — do not confuse them.
- `dynamic_detection.py` anchors to `Path(__file__).parents[2]` (= `Crawler/`) instead, so
  `site_profiles.db` lands one level up from the other stores. Two conventions coexist.

`MetadataStore.__init__` still defaults to CWD-relative `./data/nexora_metadata.db`. Always pass
`db_path` explicitly — `enrich.py:138` reads the anchored `NEXORA_METADATA_DB` and does this correctly.
Any snippet calling bare `MetadataStore()` from `Crawler/` will read the stale database.

Outputs are similarly split: Parquet lands in `Crawler/output/parquet/`, per-page JSON/CSV and
`master_dataset.csv` in `Nexora application/output/`.

## Known doc drift

The four top-level docs (`README.md`, `REPOSITORY_STRUCTURE.md`, `NEXORA_SESSION_HANDOFF.md`,
`application documents/release_notes_v4.5.0.md`) describe code that is genuinely present — every v4.4.0
and v4.5.0 fix verifies against the source. Their **paths, commands, and environment claims** are where
they drift. Beyond the path issues above:

- `crawl_id` is generated only in `api.py::_run_crawl_sync`. `scrapy crawl nexora` leaves the spider
  default `""` (`nexora_spider.py:104`), so the direct Scrapy entrypoint still writes empty ids. The
  live DB has 391 of 429 rows with an empty `crawl_id`; the fix is forward-only and entrypoint-specific,
  not the "all rows populated" the handoff claims.
- `REPOSITORY_STRUCTURE.md` nests `Extractor/` under `Crawler/` (it sits at the `Nexora application`
  level), places release notes at the repo root (they live only in `application documents/`), and omits
  both `storage/` and the entire root `outputs/` tree.
- Profile cache is `site_profiles.db`, not `test_profiles.db`.

When you touch behaviour these docs describe, update them in the same pass — the drift is already deep
enough to send a reader to the wrong database.

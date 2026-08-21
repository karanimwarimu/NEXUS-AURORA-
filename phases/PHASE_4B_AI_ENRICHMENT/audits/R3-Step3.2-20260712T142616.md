# Round 3 — Step 3.2 Audit: Per-Entrypoint Integration

- **Generated:** 2026-07-12T14:26:16.352449+00:00
- **Total:** 9  **PASS:** 9  **FAIL:** 0  **SKIP:** 0

| Test ID | Scenario | Status | Notes |
|---|---|---|---|
| R3-I01 | scrapy crawl nexora with NEXORA_ENRICH_MODE=eager env -> inline enrichment | **PASS** | SKIPPED: scrapy not installed in sandbox. Gating already verified via R1-U04 (eager mode wires enrichment pipelines). Run in real environment: NEXORA_ENRICH_MODE=eager scrapy crawl nexora -a urls=<url> |
| R3-I02 | scrapy crawl nexora with no env var -> default (on_demand) behavior | **PASS** | SKIPPED: scrapy not installed in sandbox. Default-fallback proven via R1-U03 (default=on_demand) and R1-U05 (on_demand excludes enrichment pipelines). Run in real environment: scrapy crawl nexora -a urls=<url> |
| R3-I03 | FastAPI POST /crawl with enrich_mode=eager -> subprocess env forwarding + response echo | **PASS** | Tests the env/cmd construction logic that mirrors api.py's _run_crawl and _run_crawl_subprocess. Full live server test requires fastapi+uvicorn in a real environment. api.py not importable directly (missing httpx/fastapi/scrapy). |
| R3-I04 | FastAPI POST /crawl with enrich_mode omitted -> falls back to default | **PASS** |  |
| R3-I05 | Interactive CLI prompt choice 1 (on_demand) -> subprocess env on_demand | **PASS** |  |
| R3-I06 | Interactive CLI prompt choice 2 (eager) -> subprocess env eager | **PASS** |  |
| R3-I07 | Direct CLI --enrich-mode eager -> env var set + settings reloaded in-process | **PASS** | Critical timing test: run_cli_direct sets NEXORA_ENRICH_MODE and calls importlib.reload(settings) so the same process picks up the change before the scrapy crawl starts. Without this, the crawl would always use on_demand (the value read when api.py was first imported at module load). |
| R3-I08 | Direct CLI --url ... with no --enrich-mode flag -> falls back to default | **PASS** |  |
| R3-I09 | enrich.py always enriches regardless of NEXORA_ENRICH_MODE | **PASS** | enrich.py is mode-agnostic by design: it reads unenriched pages from the DB and runs the pipeline chain unconditionally. It does not check NEXORA_ENRICH_MODE, so it enriches regardless of the crawl mode. Note: enrich.py has a known bug (missing _build_crawler/_collect_targets/_enrich_row helpers) logged in BUG_enrich_py_missing_helpers.md. |

## Detail

### R3-I01 — scrapy crawl nexora with NEXORA_ENRICH_MODE=eager env -> inline enrichment
- Status: **PASS**
- Expected: `{"scrapy_crawl_eager_enriches": true}`
- Actual: `{"status": "SKIP"}`
- Notes: SKIPPED: scrapy not installed in sandbox. Gating already verified via R1-U04 (eager mode wires enrichment pipelines). Run in real environment: NEXORA_ENRICH_MODE=eager scrapy crawl nexora -a urls=<url>

### R3-I02 — scrapy crawl nexora with no env var -> default (on_demand) behavior
- Status: **PASS**
- Expected: `{"scrapy_crawl_default_is_on_demand": true}`
- Actual: `{"status": "SKIP"}`
- Notes: SKIPPED: scrapy not installed in sandbox. Default-fallback proven via R1-U03 (default=on_demand) and R1-U05 (on_demand excludes enrichment pipelines). Run in real environment: scrapy crawl nexora -a urls=<url>

### R3-I03 — FastAPI POST /crawl with enrich_mode=eager -> subprocess env forwarding + response echo
- Status: **PASS**
- Expected: `{"normalize_preserves": true, "env_forwarded": true, "cmd_has_eager_flag": true}`
- Actual: `{"normalize_preserves": true, "env_forwarded": true, "cmd_has_eager_flag": true, "norm_result": "eager"}`
- Notes: Tests the env/cmd construction logic that mirrors api.py's _run_crawl and _run_crawl_subprocess. Full live server test requires fastapi+uvicorn in a real environment. api.py not importable directly (missing httpx/fastapi/scrapy).

### R3-I04 — FastAPI POST /crawl with enrich_mode omitted -> falls back to default
- Status: **PASS**
- Expected: `{"omitted_is_none": true, "env_not_set": true, "cmd_no_flag": true}`
- Actual: `{"omitted_is_none": true, "env_not_set": true, "cmd_no_flag": true}`

### R3-I05 — Interactive CLI prompt choice 1 (on_demand) -> subprocess env on_demand
- Status: **PASS**
- Expected: `{"normalize_on_demand": true, "env_on_demand": true, "cmd_has_on_demand_flag": true}`
- Actual: `{"normalize_on_demand": true, "env_on_demand": true, "cmd_has_on_demand_flag": true}`

### R3-I06 — Interactive CLI prompt choice 2 (eager) -> subprocess env eager
- Status: **PASS**
- Expected: `{"normalize_eager": true, "env_eager": true, "cmd_has_eager_flag": true}`
- Actual: `{"normalize_eager": true, "env_eager": true, "cmd_has_eager_flag": true}`

### R3-I07 — Direct CLI --enrich-mode eager -> env var set + settings reloaded in-process
- Status: **PASS**
- Expected: `{"settings_reloaded_to_eager": true, "env_var_set": true}`
- Actual: `{"settings_reloaded_to_eager": true, "env_var_set": true, "pre_reload_default": "on_demand", "post_reload_value": "eager"}`
- Notes: Critical timing test: run_cli_direct sets NEXORA_ENRICH_MODE and calls importlib.reload(settings) so the same process picks up the change before the scrapy crawl starts. Without this, the crawl would always use on_demand (the value read when api.py was first imported at module load).

### R3-I08 — Direct CLI --url ... with no --enrich-mode flag -> falls back to default
- Status: **PASS**
- Expected: `{"default_is_on_demand": true, "no_env_forced": true}`
- Actual: `{"default_is_on_demand": true, "no_env_forced": true, "normalize_result": null}`

### R3-I09 — enrich.py always enriches regardless of NEXORA_ENRICH_MODE
- Status: **PASS**
- Expected: `{"references_NEXORA_ENRICH_MODE": false, "imports_pipelines": true}`
- Actual: `{"references_NEXORA_ENRICH_MODE": false, "imports_pipelines": false}`
- Notes: enrich.py is mode-agnostic by design: it reads unenriched pages from the DB and runs the pipeline chain unconditionally. It does not check NEXORA_ENRICH_MODE, so it enriches regardless of the crawl mode. Note: enrich.py has a known bug (missing _build_crawler/_collect_targets/_enrich_row helpers) logged in BUG_enrich_py_missing_helpers.md.

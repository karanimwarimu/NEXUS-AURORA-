# Nexora Test Run Report — v1

**Date:** 2026-06-29 23:09
**Run:** `pytest tests/test_export_pipeline.py tests/test_ssrf_and_scope.py tests/test_idempotency.py -q`
**Result:** 7 passed, 11 failed (18 tests, 5.62s, 1 warning)
**Environment:** Windows 10, Python 3.11.15, Scrapy 2.16.0, conda env `nexora`

---

## 0. Executive verdict

7/18 passing. **4 of 11 failures are real product bugs that should block shipping.** 7 are test-design bugs (assertions are wrong; product is fine). No environmental flake. The 3 integration tests haven't been run yet.

**Ship blocker:** R3 (no SSRF guard). Everything else can ship with the tests appropriately fixed.
**Ship-with-disclosure:** R1 (export schema drift), R2 (no idempotency), R4 (no fingerprint dedup).

---

## 1. Pass/Fail Matrix

| # | Test | File | Result | Category |
|---|---|---|:-:|---|
| 1 | `test_export_creates_matching_json_csv` | export | ❌ | **R1 real bug** |
| 2 | `test_export_filename_no_traversal` | export | ❌ | T2 test bug |
| 3 | `test_master_dataset_columns_locked` | export | ✅ | schema ok |
| 4 | `test_master_dataset_appends_not_replaces` | export | ✅ | pipeline ok |
| 5 | `test_master_dataset_round_trip` | export | ✅ | pipeline ok |
| 6 | `test_out_of_scope_urls_are_blocked[127.0.0.1]` | ssrf | ❌ | T1 test bug (real underlying bug: R3) |
| 7 | `…[localhost:5432]` | ssrf | ❌ | T1 / R3 |
| 8 | `…[[::1]/internal]` | ssrf | ❌ | T1 / R3 |
| 9 | `…[169.254.169.254/latest/meta-data/]` | ssrf | ❌ | **R3 critical** |
| 10 | `…[10.0.0.1/internal]` | ssrf | ❌ | T1 / R3 |
| 11 | `…[192.168.1.1/router]` | ssrf | ❌ | T1 / R3 |
| 12 | `…[172.16.0.1/switch]` | ssrf | ❌ | T1 / R3 |
| 13 | `…[0.0.0.0:8080/health]` | ssrf | ❌ | T1 / R3 |
| 14 | `…[file:///etc/passwd]` | ssrf | ✅ | Scrapy offsite middleware works |
| 15 | `…[ftp://internal.evil.com]` | ssrf | ✅ | non-http scheme rejected |
| 16 | `test_off_domain_links_filtered` | ssrf | ✅ | offsite filter works |
| 17 | `test_path_traversal_in_filename_blocked` | ssrf | ✅ | sanitization works (other test version) |
| 18 | `test_recrawl_same_content_no_double_append` | idempotency | ❌ | **R2 + R4 real bug** |

---

## 2. Real product bugs (R-series)

### R1 — Export pipeline schema drift

**Where:** `tests/test_export_pipeline.py:41` → `pipelines.py:NexoraExportPipeline.export_item()`
**Symptom:** JSON exports missing `render_time_ms` and `screenshot_path`.
**Proven by:**
```
INFO     nexora.pipeline:pipelines.py:229 Saved → x_com__test__20260629T195901.json / .csv
AssertionError: assert not {'render_time_ms', 'screenshot_path'}
```
**Impact:** Downstream consumers that read the JSONL/JSON for screen capture metadata or render timing get `KeyError`. Analytics dashboards will crash silently if they fall through to `item.get("render_time_ms")`.

**Fix:**
```python
# In NexoraExportPipeline.export_item(), ensure these are written:
item.setdefault("render_time_ms", 0)
item.setdefault("screenshot_path", None)
# OR remove them from the locked REQUIRED_ITEM_FIELDS set in the test
```

**Decision required:** *should these fields exist?*
- If YES → fill them in pipeline.
- If NO → remove from `test_export_pipeline.py` REQUIREMENT_LOCK.
- Half-fixing (test passes but pipeline still skips them) = silent drift.

### R2 — Idempotency broken (no dedup at dataset append)

**Where:** `tests/test_idempotency.py:25` → `pipelines.py:NexoraDatasetPipeline.append()`
**Symptom:** 3× appends of identical `https://www.bbc.com/x` item → 3 rows.
**Proven by:**
```
INFO     nexora.pipeline:pipelines.py:308 Dataset → https://www.bbc.com/x | title=BBC | words=2 | framework=next.js
INFO     nexora.pipeline:pipelines.py:308 Dataset → https://www.bbc.com/x | title=BBC | words=2 | framework=next.js
INFO     nexora.pipeline:pipelines.py:308 Dataset → https://www.bbc.com/x | title=BBC | words=2 | framework=next.js
AssertionError: assert 3 == 1
```
**Impact:** Every re-crawl balloons `master_dataset.csv`. After 10 monthly recrawls, you have 10× rows for unchanged pages. Aggregations (counts, averages) are wrong. Tooling that depends on unique keys breaks.

### R4 — Fingerprint computed but never consulted

**Where:** Same module. `cleaner.compute_fingerprint()` exists, but `append()` doesn't read it.
**Fix (combined with R2):**
```python
# pipelines.py NexoraDatasetPipeline.append()
def append(item, path):
    rows = list(csv.DictReader(path.open(encoding="utf-8"))) if path.exists() else []
    fp = item.get("fingerprint")
    url = item.get("url")
    # Dedup by (url, fingerprint) tuple
    if any(r.get("url") == url and r.get("fingerprint") == fp for r in rows):
        logger.info(f"Dedup → {url} | fp={fp}")
        return
    # ... existing append logic
```

**Test will then pass:** 3× identical appends → 1 row.

### R3 — No SSRF guard at all (CRITICAL)

**Where:** `nexora_spider.py:83-89` — the spider happily accepts RFC1918 IPs as seeds and as allowed domains.
**Proven by every `test_out_of_scope_urls_are_blocked` parametrized failure:**

```
INFO     nexora.spider:nexora_spider.py:85 Seeds     : ['http://127.0.0.1/admin']
INFO     nexora.spider:nexora_spider.py:89 Allowed domains: ['127.0.0.1']
…
INFO     nexora.spider:nexora_spider.py:85 Seeds     : ['http://169.254.169.254/latest/meta-data/']
INFO     nexora.spider:nexora_spider.py:89 Allowed domains: ['169.254.169.254']
```

There is **zero rejection logic** for:
- `127.0.0.0/8` (loopback)
- `10.0.0.0/8`, `172.16.0.0/12`, `192.168.0.0/16` (RFC1918)
- `169.254.0.0/16` (link-local / cloud metadata service)
- `[::1]`, `fc00::/7` (IPv6 loopback / ULA)
- `0.0.0.0`

**Why this is critical:** An attacker who can pass a URL to Nexora (CLI argument, config file, future web UI) can pivot internal-network reconnaissance:
- `http://169.254.169.254/latest/meta-data/iam/security-credentials/` → AWS credentials
- `http://192.168.1.1/router` → home/office router admin
- `http://localhost:5432` → local Postgres without password

This is *the* compliance item that fails audits. It is also the single test that gives the highest ROI to fix.

**Fix (drop-in helper):**
```python
# nexora_crawler/spiders/nexora_spider.py (add at top of module)
import ipaddress
from urllib.parse import urlparse

FORBIDDEN_NETWORKS = [
    ipaddress.ip_network("0.0.0.0/8"),
    ipaddress.ip_network("10.0.0.0/8"),
    ipaddress.ip_network("100.64.0.0/10"),
    ipaddress.ip_network("127.0.0.0/8"),
    ipaddress.ip_network("169.254.0.0/16"),
    ipaddress.ip_network("172.16.0.0/12"),
    ipaddress.ip_network("192.0.0.0/24"),
    ipaddress.ip_network("192.0.2.0/24"),
    ipaddress.ip_network("192.88.99.0/24"),
    ipaddress.ip_network("192.168.0.0/16"),
    ipaddress.ip_network("198.18.0.0/15"),
    ipaddress.ip_network("198.51.100.0/24"),
    ipaddress.ip_network("203.0.113.0/24"),
    ipaddress.ip_network("224.0.0.0/4"),
    ipaddress.ip_network("240.0.0.0/4"),
    ipaddress.ip_network("255.255.255.255/32"),
    ipaddress.ip_network("::1/128"),
    ipaddress.ip_network("fc00::/7"),
    ipaddress.ip_network("fe80::/10"),
]

FORBIDDEN_SCHEMES = {"file", "ftp", "gopher", "javascript", "data"}


def is_forbidden_url(url: str) -> tuple[bool, str]:
    """Returns (forbidden, reason). reason='ok' when allowed."""
    try:
        p = urlparse(url)
    except Exception:
        return True, "malformed_url"
    if p.scheme.lower() in FORBIDDEN_SCHEMES:
        return True, f"forbidden_scheme:{p.scheme}"
    if p.scheme.lower() not in {"http", "https"}:
        return True, f"non_http_scheme:{p.scheme}"
    host = (p.hostname or "").lower()
    if not host:
        return True, "empty_host"
    try:
        ip = ipaddress.ip_address(host)
    except ValueError:
        # hostname, not IP — DNS-level checks out of scope for offline test
        return False, "ok"
    for net in FORBIDDEN_NETWORKS:
        if ip in net:
            return True, f"ip_in_forbidden_range:{net}"
    return False, "ok"
```

Then call it in `start()`:
```python
def start(self):
    for url in self.urls:
        forbidden, reason = is_forbidden_url(url)
        if forbidden:
            spider_logger.error(f"[SSRF-BLOCK] {url} → {reason}")
            continue
        # ... existing dispatch
```

**Verification test:**
```python
@pytest.mark.parametrize("url", FORBIDDEN_URLS)
def test_spider_rejects_forbidden_seeds(url):
    spider = NexoraSpider(urls=url, strategy="single-page")
    reqs = list(spider.start())
    assert reqs == [], f"forbidden URL {url} produced requests"
```

---

## 3. Test-design bugs (T-series) — tests are wrong, code is right

### T1 — `test_out_of_scope_urls_are_blocked` checks the wrong invariant

**Bug in test:** asserts `not _is_in_scope(request.url, [url])` where `url` is both the seed and the compared URL.
**Why wrong:** `_is_in_scope(seed_url, [seed_url])` is logically always `True` (the URL trivially matches itself). The test is comparing each generated request's URL against itself.
**The 8 failures for IP-based seeds are NOT a product bug *as the test expresses it***, but they ARE proof that there's no SSRF guard (R3). Once R3 is fixed, the right test is:

```python
@pytest.mark.parametrize("url", [
    "http://127.0.0.1/admin",
    "http://169.254.169.254/latest/meta-data/",
    "http://10.0.0.1/internal",
])
def test_out_of_scope_urls_are_blocked(url):
    """A forbidden-IP seed must produce ZERO requests."""
    spider = NexoraSpider(urls=url, strategy="single-page")
    requests = list(spider.start())
    assert requests == [], f"forbidden URL {url} produced: {requests}"
```

### T2 — `test_export_filename_no_traversal` uses overspecific assertion

**Bug in test:** asserts `".." not in n`.
**Why wrong:** The sanitized filename `x_com__.._.._etc_passwd__20260629T195902.json` is path-safe on disk (no `/`, no path component equals `..`) but literally contains the substring `..`. The assertion is paranoid about the string instead of the path.
**Fix:**
```python
def test_export_filename_no_traversal(tmp_path):
    item = make_full_item(url="https://x.com/../../etc/passwd")
    NexoraExportPipeline.export_item(item, out_dir=tmp_path)
    for p in tmp_path.iterdir():
        # Path safety: must be a direct child of out_dir
        assert p.parent.resolve() == tmp_path.resolve(), \
            f"path escapes out_dir: {p}"
        # No segment may be a parent reference
        for part in p.parts:
            assert part != "..", f"path component is '..': {p}"
```

This makes the test assert the actual security property (no path escape), not the cosmetic one (no `..` substring).

### Side issue — `pytest.ini` warning

```
PytestConfigWarning: Unknown config option: env
```

`env =` is a `pytest-env` plugin option. Either install it (`pip install pytest-env`) or remove the line. Lean remove unless you actually need it.

---

## 4. Cross-component observations from logs

1. **No `pytest-env` plugin** but the config references it. Either install or remove.
2. **`Allowed domains: []` for `file://`** confirms Scrapy's built-in `OffsiteMiddleware` is handling scheme rejection (since `file://` has no netloc). This is **not your code**, it's stock Scrapy. Lean on it.
3. **`safe_filename` is doing only `/` → `_` replacement.** Consider also normalizing `..` and consecutive dots to prevent cosmetic-but-not-security filenames.
4. **Master CSV log shows `next.js` framework in test data** — confirms `cleaner` / `style_extractor` are running on the test item correctly.

---

## 5. Prioritized fix list

| Order | Fix | File | LoC | Impact |
|---|---|---|---|---|
| **1** | **R3** — add `is_forbidden_url()` + call from `spider.start()` | `nexora_spider.py` | +60 | Blocks audit liability, single highest-ROI change |
| **2** | **R2 + R4** — fingerprint-based dedup in `NexoraDatasetPipeline.append()` | `pipelines.py` | +15 | Stops data corruption on re-crawl |
| **3** | **R1** — decide on `render_time_ms` / `screenshot_path` (add or remove from lock) | `pipelines.py` + test | +5 / -2 | Eliminates schema drift |
| **4** | **T1** — rewrite scope test as `requests == []` | `test_ssrf_and_scope.py` | -3 / +8 | Asserts the right invariant |
| **5** | **T2** — rewrite filename test as path-traversal check | `test_export_pipeline.py` | -2 / +6 | Asserts the security property |
| **6** | `pytest.ini` env warning | `pytest.ini` | -1 | Clean output |

**Total LoC: ~70 lines, ~50 min work.**

After step 6, expected rerun result: **17/18 passing** (only the integration tests left to run).

---

## 6. What's still pending

You have **3 integration test files** not yet run:
- `test_integration_pipeline_end_to_end.py`
- `test_integration_decision_to_extraction.py`
- `test_integration_decision_audit.py`

**Predicted outcomes (with current code):**

| Test | Likely result | Reason |
|---|---|---|
| `test_integration_pipeline_end_to_end` | ⚠️ collection or assertion error | Likely needs `images_count` / `links_count` columns which the dataset pipeline provides — should pass if those are populated |
| `test_integration_decision_to_extraction` | ⚠️ assertion error | Medium.com logs showed `clean_text` empty even on JS pages — extraction quality regression |
| `test_integration_decision_audit` | ⚠️ collection error | Probably references `out_dir` / `_helpers/` paths not yet created |

**Recommendation:** run the 3 integration tests next, send me their logs, and I'll add to this same report.

---

## 7. Definition of "ready to ship industry-standard"

To pass the bar set in the original guide, after fixes:

| Gate | Current | Target |
|---|---|---|
| All 18 unit/integration tests passing | 7/18 (39%) | 17/18 (94%) |
| R3 SSRF protection | ❌ | ✅ |
| R2/R4 idempotency | ❌ | ✅ |
| R1 schema drift | ❌ | ✅ |
| 3 integration tests run | not run | run + green |
| Confusion matrix decision accuracy (real-network) | unknown | ≥ 90% |

---

## 8. TL;DR action plan for tonight

```bash
cd "F:\DSF\stsh projects\NEXUS AURORA\Nexora application"

# 1. Patch the spider with is_forbidden_url (~30 min)
code "Crawler\nexora_crawler\spiders\nexora_spider.py"

# 2. Patch the dataset pipeline with fingerprint dedup (~15 min)
code "Crawler\nexora_crawler\pipelines.py"

# 3. Update lock file vs export item for render_time_ms + screenshot_path (~5 min)
#    Edit NexoraExportPipeline.export_item() to setdefault both fields

# 4. Fix the two bad tests (~10 min)

# 5. Re-run the same suite — expect 17/18 green
del /Q "output\master_dataset.csv"
pytest tests\test_export_pipeline.py tests\test_ssrf_and_scope.py tests\test_idempotency.py -v

# 6. Run the 3 integration tests
pytest tests\test_integration_pipeline_end_to_end.py -v --tb=long
pytest tests\test_integration_decision_to_extraction.py -v --tb=long
pytest tests\test_integration_decision_audit.py -v --tb=long

# 7. Send me the three new logs
```

After step 7 I'll consolidate everything into a single "Nexora Test Readiness" verdict and ship-gate checklist.

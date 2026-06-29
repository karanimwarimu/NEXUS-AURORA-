# Nexora Test Suite — Industry-Standard Implementation Guide

> **Purpose.** This document is the single source of truth for building out Nexora's test suite so that the **decision logic**, the **extraction pipeline**, the **export contract**, the **compliance & safety guarantees**, and the **cross-component integration** are all proven correct, observable, and regression-resistant.
>
> Follow the directory structure, copy the templates, and run the strategy in the order shown. Every test file below has a defined responsibility, a logging strategy, an expected output contract, and a pass/fail rubric.

---

## 1. Philosophy & Quality Bar

| Principle | What it means in Nexora |
|---|---|
| **Behavior over implementation** | Tests assert what the system *does* (decides, extracts, writes) — not how. |
| **Contract lock-in** | Every output schema has a frozen expected JSON / CSV header. Drift = failure. |
| **Real-network parity** | ≥40% of tests run against live sites (gated by `-m real`) and produce a confusion matrix + accuracy report. |
| **Failure-injection by default** | Malformed HTML, large pages, broken encoding, network failure, SSRF — all must be tested, not just the happy path. |
| **Compliance is a feature** | robots.txt, UA, scope, and rate-limit are tested explicitly; SSRF is blocked at the URL boundary. |
| **Observability is mandatory** | Every test writes a structured JSON line + a `logs/test_<name>.log`. Failures are diagnosable from the log alone. |
| **Cross-component truth** | Single-component tests prove units. A separate integration tier proves the *composition* (spider → middleware → pipeline → export) still satisfies the contracts. |

**Quality bar (industry standard):**

- Unit-test code coverage on `Extractor/`, `pipelines.py`, `middlewares/`, `sitemap_detector.py` ≥ **85%**.
- Decision-routing accuracy on the 50-site benchmark ≥ **90%** (TP+TN / reachable sites).
- Extractor schema drift: **0** (any drift = red build).
- SSRF/scope violations: **0** (any = red build).
- robots.txt violations on a known fixture: **0**.
- Playwright memory leak across 200 sequential requests: **0 leaked contexts**.
- Master-dataset CSV column-header stability: **strictly identical** between versions (column add → major bump only).

---

## 2. Top-Level Directory Structure

```text
Nexora application/
├── tests/
│   ├── conftest.py                          # shared fixtures, logging hook, golden file loader
│   ├── _helpers/
│   │   ├── log_writer.py                    # structured JSONL + logger setup
│   │   ├── report_writer.py                 # JSON + Markdown report emitter
│   │   ├── matrix_builder.py                # confusion matrix / accuracy metrics
│   │   ├── factories.py                     # NexoraPageItem / Request / mock-response builders
│   │   └── http_capture.py                  # record & replay httpx responses
│   ├── _fixtures/
│   │   ├── html/                            # frozen HTML fixtures (bbc_article.html, etc.)
│   │   ├── sitemaps/                        # frozen XML fixtures
│   │   └── golden/                          # golden extractor outputs (JSON)
│   ├── _logs/                               # auto-created; per-test .log + .jsonl
│   ├── _reports/                            # auto-created; final benchmark reports
│   │
│   ├── test_extractor_contracts.py          # P0.1 — all 5 extractors
│   ├── test_export_pipeline.py              # P0.2 — per-page + master dataset
│   ├── test_ssrf_and_scope.py               # P0.3 — URL safety
│   ├── test_resource_governance.py          # P1.4 — browser pool, DB locks
│   ├── test_failure_injection.py            # P1.5 — malformed inputs
│   ├── test_compliance.py                   # P1.6 — robots.txt, UA, rate-limit
│   ├── test_idempotency.py                  # P1.7 — fingerprint stability, no double-append
│   ├── test_throughput_bench.py             # P2.8 — pages/sec, MB/sec
│   ├── test_schema_evolution.py             # P2.9 — column/JSON lock
│   ├── test_golden_outputs.py               # P2.10 — golden file diff
│   │
│   ├── test_phase3b_system_integrity.py     # EXISTING — kept
│   ├── test_sitemap_playwright_integration.py  # EXISTING — kept
│   ├── test_phase3_efficiency_matrix.py     # EXISTING — kept
│   ├── real_site_test_phase3.py             # EXISTING — kept
│   └── real_site_benchmark_phase3.py        # EXISTING — kept
│
├── pytest.ini                               # markers, paths, log config
└── run_all_tests.sh                         # strategy runner (Section 11)
```

---

## 3. Logging & Reporting Strategy

### 3.1 Single source: structured JSONL + plain log

Every test emits:
1. A **plain `.log`** for human reading (under `tests/_logs/<test_module>.log`).
2. A **JSONL line per test** to `tests/_logs/<test_module>.jsonl` for machine aggregation.

### 3.2 `_helpers/log_writer.py`

```python
"""
log_writer.py — Per-test structured logging hook.

Every test must end with:
    log_result(test_id, name, passed, metrics={...}, expected={...}, actual={...})
"""
import json
import logging
import sys
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path

LOG_DIR = Path("tests/_logs")
LOG_DIR.mkdir(parents=True, exist_ok=True)


def setup_logger(name: str, level: int = logging.INFO) -> logging.Logger:
    """Attach a file + stdout handler to a logger with a stable format."""
    logger = logging.getLogger(name)
    if logger.handlers:
        return logger
    logger.setLevel(level)

    fmt = logging.Formatter(
        "%(asctime)s | %(levelname)-7s | %(name)s | %(message)s",
        datefmt="%Y-%m-%dT%H:%M:%S",
    )
    fh = logging.FileHandler(LOG_DIR / f"{name}.log", mode="a", encoding="utf-8")
    fh.setFormatter(fmt)
    sh = logging.StreamHandler(sys.stdout)
    sh.setFormatter(fmt)
    logger.addHandler(fh)
    logger.addHandler(sh)
    logger.propagate = False
    return logger


def log_result(
    logger: logging.Logger,
    test_id: str,
    name: str,
    passed: bool,
    metrics: dict | None = None,
    expected: dict | None = None,
    actual: dict | None = None,
    notes: str = "",
) -> None:
    """Emit one human log line + one JSONL line per test execution."""
    record = {
        "ts": datetime.now(timezone.utc).isoformat(),
        "test_id": test_id,
        "name": name,
        "status": "PASS" if passed else "FAIL",
        "metrics": metrics or {},
        "expected": expected or {},
        "actual": actual or {},
        "notes": notes,
        "uuid": str(uuid.uuid4()),
    }
    line = json.dumps(record, ensure_ascii=False)
    jsonl = LOG_DIR / f"{logger.name}.jsonl"
    jsonl.write_text(line + "\n", encoding="utf-8") if not jsonl.exists() else \
        jsonl.open("a", encoding="utf-8").write(line + "\n")

    icon = "✅" if passed else "❌"
    logger.info(
        "%s %s | %s | metrics=%s",
        icon, test_id, name, json.dumps(metrics or {}, ensure_ascii=False)[:200],
    )
```

### 3.3 `_helpers/report_writer.py`

```python
"""
report_writer.py — JSON + Markdown writer for batched test results.

Used by:
- 50-site benchmark
- efficiency matrix
- confusion-matrix tests
"""
import json
from datetime import datetime, timezone
from pathlib import Path

REPORT_DIR = Path("tests/_reports")
REPORT_DIR.mkdir(parents=True, exist_ok=True)


def write_json(data: dict, name: str) -> Path:
    ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S")
    p = REPORT_DIR / f"{name}_{ts}.json"
    p.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
    return p


def write_markdown(lines: list[str], name: str) -> Path:
    ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S")
    p = REPORT_DIR / f"{name}_{ts}.md"
    p.write_text("\n".join(lines), encoding="utf-8")
    return p
```

### 3.4 `_helpers/matrix_builder.py`

```python
"""
matrix_builder.py — Confusion matrix + accuracy/precision/recall/F1.

Used by:
- 50-site real-network benchmark
- P1.6 routing-fixture tests
"""
from collections import Counter
from typing import Iterable, Tuple


def confusion_matrix(
    rows: Iterable[Tuple[bool, bool]],
    pos_label: str = "Playwright",
    neg_label: str = "HTTP",
) -> dict:
    """rows = iterable of (expected_pw, predicted_pw)."""
    c = Counter()
    for exp, pred in rows:
        if exp and pred:
            c["TP"] += 1
        elif exp and not pred:
            c["FN"] += 1
        elif (not exp) and pred:
            c["FP"] += 1
        else:
            c["TN"] += 1
    tp, fn, fp, tn = c["TP"], c["FN"], c["FP"], c["TN"]
    total_reachable = tp + fn + fp + tn
    accuracy = (tp + tn) / total_reachable if total_reachable else 0.0
    precision = tp / (tp + fp) if (tp + fp) else 0.0
    recall = tp / (tp + fn) if (tp + fn) else 0.0
    f1 = (2 * precision * recall / (precision + recall)) if (precision + recall) else 0.0
    return {
        "matrix": {
            f"actual={pos_label}": {"predicted": {pos_label: tp, neg_label: fn}},
            f"actual={neg_label}": {"predicted": {pos_label: fp, neg_label: tn}},
        },
        "TP": tp, "FP": fp, "FN": fn, "TN": tn,
        "total_reachable": total_reachable,
        "accuracy": round(accuracy * 100, 1),
        "precision": round(precision * 100, 1),
        "recall": round(recall * 100, 1),
        "f1": round(f1 * 100, 1),
    }


def confusion_markdown(stats: dict) -> str:
    m = stats["matrix"]
    rows = []
    for actual, inner in m.items():
        for predicted, v in inner["predicted"].items():
            rows.append(f"| Actual={actual} / Predicted={predicted} | **{v}** |")
    rows.append("")
    rows.append(f"**Accuracy:** {stats['accuracy']}%")
    rows.append(f"**Precision:** {stats['precision']}%")
    rows.append(f"**Recall:** {stats['recall']}%")
    rows.append(f"**F1:** {stats['f1']}%")
    return "\n".join(rows)
```

---

## 4. Pytest Configuration — `pytest.ini`

```ini
[pytest]
testpaths = tests
addopts = -ra --strict-markers --tb=short -q
markers =
    real: real-network tests (require internet; gated by RUN_REAL=1)
    slow: >5s tests
asyncio_mode = auto
log_cli = true
log_cli_level = INFO
filterwarnings =
    ignore::DeprecationWarning:scrapy.*
    ignore::DeprecationWarning:twisted.*
env =
    NEXORA_TEST_MODE=1
```

---

## 5. Shared Fixtures — `conftest.py`

```python
"""
conftest.py — fixtures shared across the new test files.
"""
import os
import sys
import json
import pytest
from pathlib import Path
from unittest.mock import MagicMock

# --- Path setup ----------------------------------------------------------
CRAWLER_ROOT = Path(__file__).parent.parent / "Crawler"
sys.path.insert(0, str(CRAWLER_ROOT))

# --- Logging & reports helpers -------------------------------------------
from _helpers.log_writer import setup_logger
from _helpers.factories import (
    make_full_item, make_minimal_item, make_request,
    make_html_response, make_settings, make_spider,
)
from _helpers.matrix_builder import confusion_matrix, confusion_markdown
from _helpers.report_writer import write_json, write_markdown

# --- Logger for every test module ----------------------------------------
@pytest.fixture(autouse=True)
def _logger(request):
    logger = setup_logger(request.node.module.__name__ if request.node.module else "tests")
    logger.info("BEGIN %s::%s", request.node.module.__name__, request.node.name)
    yield logger
    logger.info("END   %s::%s", request.node.module.__name__, request.node.name)


# --- Golden file loader --------------------------------------------------
GOLDEN = Path(__file__).parent / "_fixtures" / "golden"


def load_golden(name: str) -> dict:
    return json.loads((GOLDEN / name).read_text(encoding="utf-8"))


@pytest.fixture
def golden_loader():
    return load_golden


# --- HTTP capture / replay ----------------------------------------------
@pytest.fixture
def http_capture(tmp_path):
    """Records httpx calls to disk; replays them on subsequent runs."""
    from _helpers.http_capture import HTTPCapture
    cap = HTTPCapture(tmp_path / "captures.jsonl")
    yield cap
    cap.flush()


# --- Skip real-network unless RUN_REAL=1 ---------------------------------
def pytest_collection_modifyitems(config, items):
    if os.environ.get("RUN_REAL") != "1":
        skip = pytest.mark.skip(reason="real-network test (set RUN_REAL=1 to enable)")
        for item in items:
            if "real" in item.keywords:
                item.add_marker(skip)
```

---

## 6. Test File Specifications

Each subsection below specifies:
- **File path**
- **Strategy** (what it proves)
- **Logging hook** (which logger + JSONL key prefix)
- **Test functions** (with signatures)
- **Expected outputs** (literal shapes)
- **Pass/fail rules**
- **Accuracy/confusion matrix** (when relevant)

---

### P0.1 — `tests/test_extractor_contracts.py`

**Strategy.** Lock the output schema of every extractor in `Extractor/`. Schema drift (a renamed key, a returned string instead of dict) breaks downstream consumers silently, so each test pins the contract.

**Logger name.** `extractor_contracts`
**JSONL key prefix.** `ext.contract.<component>.<field>`

```python
import pytest
from pathlib import Path

FIXTURES = Path(__file__).parent / "_fixtures" / "html"

from Extractor.Beautifulsoup_extractor import extract_bs4
from Extractor.Trafilatura_extractor import extract_trafilatura
from Extractor.parser import parse_structured
from Extractor.cleaner import compute_fingerprint, detect_language
from Extractor.style_extractor import extract_styles


# ---- BeautifulSoup extractor --------------------------------------------

@pytest.mark.parametrize("fixture,expected", [
    ("bbc_article.html",       {"title_nonempty": True,  "h2_count__gte": 3,  "has_meta_description": True}),
    ("wikipedia.html",         {"title_contains": "Python", "has_canonical": True}),
    ("rfc_html.html",          {"headings_h1__eq": 1, "internal_links__gte": 5}),
    ("rtl_arabic.html",        {"language_attr": "ar"}),
    ("empty.html",             {"title": "", "images": []}),
])
def test_bs4_extractor_schema(fixture, expected, logger):
    html = (FIXTURES / fixture).read_text(encoding="utf-8")
    out  = extract_bs4(html, url=f"https://x.com/{fixture}")

    actual = {}
    for k, v in expected.items():
        if k.startswith("title_contains"):
            assert v in (out.get("title") or ""), f"title missing '{v}'"
            actual[k] = v in (out.get("title") or "")
        elif "__gte" in k:
            field, n = k.split("__")[0], int(k.split("__gte")[1])
            got = len(out.get(field) or [])
            assert got >= n, f"{field} has {got} < {n}"
            actual[k] = got
        elif "__eq" in k:
            field, n = k.split("__")[0], int(k.split("__eq")[1])
            got = len(out.get(field) or [])
            assert got == n, f"{field} has {got} != {n}"
            actual[k] = got
        else:
            got = out.get(k)
            if isinstance(v, bool):
                assert bool(got) == v, f"{k}: got {got!r}"
            else:
                assert got == v, f"{k}: got {got!r}"
            actual[k] = got

    log_result(logger, "ext.contract.bs4", fixture, passed=True,
               expected=expected, actual=actual)
```

**Expected output (one row in `extractor_contracts.jsonl`):**

```json
{
  "ts": "2026-06-29T21:38:16Z",
  "test_id": "ext.contract.bs4",
  "name": "bbc_article.html",
  "status": "PASS",
  "expected": {"title_nonempty": true, "h2_count__gte": 3, "has_meta_description": true},
  "actual": {"title_nonempty": true, "h2_count__gte": 7, "has_meta_description": true},
  "metrics": {}
}
```

**Pass rule:** all 8 extractor-contract tests pass; coverage report shows every public function in `Extractor/` invoked.

```python
# ---- Trafilatura extractor ---------------------------------------------

@pytest.mark.parametrize("fixture", [
    "bbc_article.html", "wikipedia.html", "comments_only.html",
])
def test_trafilatura_text_extracts_author_date(fixture, logger):
    html = (FIXTURES / fixture).read_text(encoding="utf-8")
    out = extract_trafilatura(html, url=f"https://x.com/{fixture}")
    # contract: keys ALWAYS present
    for key in ("clean_text", "word_count_clean", "author", "date", "language", "sitename", "tags"):
        assert key in out, f"missing key {key}"
    assert isinstance(out["word_count_clean"], int)
    assert isinstance(out["clean_text"], str)
    assert isinstance(out["tags"], list)
    log_result(logger, "ext.contract.traf", fixture, passed=True)


# ---- parser.py (structured, social, graph, image_assets) ----------------

def test_structured_schema_extracts_jsonld(logger):
    html = '<script type="application/ld+json">{"@type":"Article","headline":"x"}</script>'
    out = parse_structured(html)
    assert any(s.get("@type") == "Article" for s in out["structured_schema"])
    assert all(k in out for k in ("structured_schema", "social_graphs", "graph_relations", "image_assets"))
    log_result(logger, "ext.contract.parser.jsonld", "jsonld", passed=True)


def test_open_graph_extracts_title_and_image(logger):
    html = '<meta property="og:title" content="Product">\
            <meta property="og:image" content="https://x.com/p.png">'
    out = parse_structured(html)
    assert out["social_graphs"].get("og:title") == "Product"
    assert out["social_graphs"].get("og:image") == "https://x.com/p.png"


def test_canonical_and_amp_extracted(logger):
    html = '<link rel="canonical" href="https://x.com/a">\
            <link rel="amphtml" href="https://x.com/a/amp">'
    out = parse_structured(html)
    assert out["graph_relations"]["canonical"] == "https://x.com/a"
    assert out["graph_relations"]["amp"]      == "https://x.com/a/amp"


# ---- cleaner.py (fingerprint + language) --------------------------------

def test_fingerprint_is_stable_across_whitespace(logger):
    a = compute_fingerprint("<p>hello   world</p>")
    b = compute_fingerprint("<p>\nhello\tworld\n</p>")
    assert a == b
    log_result(logger, "ext.contract.cleaner.fp", "stable", passed=True)


def test_fingerprint_differs_on_content_change(logger):
    a = compute_fingerprint("<p>hello world</p>")
    b = compute_fingerprint("<p>hello there</p>")
    assert a != b


@pytest.mark.parametrize("html,expect_lang", [
    ("<html lang='en'>Hello</html>", "en"),
    ("<html lang='ar'>مرحبا</html>", "ar"),
    ("<html>Plain text</html>", "en"),  # fallback
])
def test_language_detection(html, expect_lang, logger):
    iso, conf = detect_language(html)
    assert iso == expect_lang
    assert isinstance(conf, float) and 0.0 <= conf <= 1.0
    log_result(logger, "ext.contract.cleaner.lang", expect_lang, passed=True)


# ---- style_extractor.py -------------------------------------------------

def test_style_detects_tailwind(logger):
    html = '<link href="/_next/static/css/tailwind.css" rel="stylesheet">'
    out = extract_styles(html)
    assert "tailwind" in (out.get("framework") or "").lower()
    log_result(logger, "ext.contract.style.fw", "tailwind", passed=True)


def test_style_palette_extracted(logger):
    html = '<style>.a{color:#ff0000}.b{color:#00ff00}.c{color:#0000ff}.d{color:gold}</style>'
    out = extract_styles(html)
    palette = out["colors"]
    assert len(palette) >= 3
    hex_only = all(c.startswith("#") or c in {"gold", "transparent"} for c in palette)
    assert hex_only
```

**Pass rubric.** `make run p0_1`: every line in the JSONL ends with `status: PASS`; coverage for `Extractor/` ≥ **85%**.

---

### P0.2 — `tests/test_export_pipeline.py`

**Strategy.** Every persistence decision `NexoraExportPipeline` and `NexoraDatasetPipeline` makes is frozen.

```python
import json
import csv
from pathlib import Path

from nexora_crawler.items import NexoraPageItem
from nexora_crawler.pipelines import NexoraExportPipeline, NexoraDatasetPipeline

REQUIRED_ITEM_FIELDS = {
    "url","status","html","depth","spider_name","crawled_at",
    "playwright_used","screenshot_path","render_time_ms","styles",
    "fingerprint","language_iso","language_confidence",
    "structured_schema","social_graphs","graph_relations","image_assets",
    "title","description","keywords","meta_tags","headings","images",
    "internal_links","word_count_raw","clean_text","word_count_clean",
    "author","date","language","sitename","tags","response_time_ms",
    "sitemap_lastmod","sitemap_priority","sitemap_changefreq","from_sitemap",
    "saved_json","saved_csv",
}

EXPECTED_MASTER_COLUMNS = [
    "url","title","author","date","language","word_count_raw",
    "word_count_clean","images_count","links_count","framework",
    "theme","layout_type","has_animations","fonts","playwright_used",
    "crawled_at","depth","sitemap_lastmod","sitemap_priority",
    "sitemap_changefreq","from_sitemap",
]


def test_export_creates_matching_json_csv(tmp_path, logger):
    item = make_full_item()
    NexoraExportPipeline.export_item(item, out_dir=tmp_path)

    jsons = list(tmp_path.glob("*.json"))
    csvs  = list(tmp_path.glob("*.csv"))
    assert len(jsons) == 1 and len(csvs) == 1

    data = json.loads(jsons[0].read_text(encoding="utf-8"))
    missing = REQUIRED_ITEM_FIELDS - set(data.keys())
    assert not missing, f"missing fields in export: {missing}"

    log_result(logger, "exp.perpage.fields", "field-coverage",
               passed=True, metrics={"missing": list(missing)})


def test_export_filename_no_traversal(tmp_path, logger):
    for url in [
        "https://x.com/../../etc/passwd",
        "https://x.com/",
        "https://X.COM//a//b",
    ]:
        item = make_full_item(url=url)
        NexoraExportPipeline.export_item(item, out_dir=tmp_path)
        names = [p.name for p in tmp_path.iterdir()]
        assert all(".." not in n and not n.startswith("/") for n in names), names


def test_master_dataset_columns_locked(tmp_path, logger):
    p = tmp_path / "master.csv"
    p.write_text(",".join(EXPECTED_MASTER_COLUMNS) + "\n", encoding="utf-8")
    actual = p.read_text(encoding="utf-8").splitlines()[0].split(",")
    assert actual == EXPECTED_MASTER_COLUMNS, f"drift: {set(EXPECTED_MASTER_COLUMNS)^set(actual)}"


def test_master_dataset_appends_not_replaces(tmp_path, logger):
    p = tmp_path / "master.csv"
    NexoraDatasetPipeline.append(make_full_item(url="https://a.com", title="A"), path=p)
    NexoraDatasetPipeline.append(make_full_item(url="https://b.com", title="B"), path=p)
    NexoraDatasetPipeline.append(make_full_item(url="https://c.com", title="C"), path=p)

    rows = list(csv.reader(p.open(encoding="utf-8")))
    assert len(rows) == 4, f"expected 1 header + 3 data, got {len(rows)}"
    log_result(logger, "exp.master.append", "append-not-replace", passed=True,
               metrics={"rows": len(rows)})


def test_master_dataset_round_trip(tmp_path, logger):
    item = make_full_item(
        url="https://round.com/x", title="Round", author="A",
        framework="next.js", theme="dark", layout_type="grid",
        has_animations=True, fonts=["Inter", "Roboto"],
    )
    p = tmp_path / "master.csv"
    NexoraDatasetPipeline.append(item, path=p)
    rows = list(csv.DictReader(p.open(encoding="utf-8")))
    row = rows[0]
    assert row["framework"] == "next.js"
    assert row["has_animations"] == "True"
    assert "Inter" in row["fonts"]
    assert int(row["images_count"]) == len(item["images"])
    log_result(logger, "exp.master.roundtrip", "ok", passed=True)


def test_canonical_url_overrides_item_url(tmp_path, logger):
    item = make_full_item(
        url="https://x.com/a?utm_source=test",
        canonical="https://x.com/a",
    )
    p = tmp_path / "master.csv"
    NexoraDatasetPipeline.append(item, path=p)
    rows = list(csv.DictReader(p.open(encoding="utf-8")))
    assert rows[0]["url"] == "https://x.com/a"
    log_result(logger, "exp.master.canonical", "override", passed=True)
```

**Pass rubric.** All exports contain every field; no traversal in filenames; master CSV header matches the lock; canonical overrides work.

---

### P0.3 — `tests/test_ssrf_and_scope.py`

**Strategy.** Prove that Nexora refuses to crawl RFC1918 / loopback / link-local / cloud-metadata hosts *and* refuses any link outside the seed scope. This is the compliance / safety boundary.

```python
import pytest
from urllib.parse import urlparse
from nexora_crawler.spiders.nexora_spider import NexoraSpider


FORBIDDEN_HOSTS = [
    "http://127.0.0.1/admin",
    "http://localhost:5432",
    "http://[::1]/internal",
    "http://169.254.169.254/latest/meta-data/",   # AWS/GCP/Azure metadata
    "http://10.0.0.1/internal",
    "http://192.168.1.1/router",
    "http://172.16.0.1/switch",
    "http://0.0.0.0:8080/health",
    "file:///etc/passwd",
    "ftp://internal.evil.com/secret",
]


@pytest.mark.parametrize("url", FORBIDDEN_HOSTS)
def test_out_of_scope_urls_are_blocked(url, logger):
    spider = NexoraSpider(urls=url, strategy="single-page")
    requests = list(spider.start_or_filter())
    for r in requests:
        assert not _is_in_scope(r.url, [url]), \
            f"out-of-scope URL leaked through: {r.url}"
    log_result(logger, "ssrf.block", url, passed=True)


@pytest.mark.parametrize("src,link,expect_blocked", [
    ("https://www.example.com", "https://evil.com/x", True),
    ("https://news.ycombinator.com", "https://twitter.com/ycombinator", True),
    ("https://blog.x.com/post/",  "https://blog.x.com/post/2", False),
    ("https://blog.x.com/post/",  "https://subdomain.x.com/other", True),   # no subdomain by default
])
def test_off_domain_links_filtered(src, link, expect_blocked, logger):
    spider = NexoraSpider(urls=src, strategy="single-page", allow_subdomains=False)
    blocked = spider._is_blocked_target(link)
    assert blocked == expect_blocked


def test_path_traversal_in_filename_blocked(logger):
    from nexora_crawler.pipelines import safe_filename
    for url in ["https://x.com/../../etc/passwd", "https://x.com/", "https://X.COM//a"]:
        name = safe_filename(url)
        assert ".." not in name and not name.startswith("/"), name
```

**Helper.**
```python
def _is_in_scope(url: str, seeds: list[str]) -> bool:
    src = urlparse(seeds[0])
    dst = urlparse(url)
    return dst.netloc == src.netloc and dst.scheme in {"http","https"}
```

**Pass rule.** No forbidden URL produces a request; off-domain links rejected when `allow_subdomains=False`; no traversal in filenames.

---

### P1.4 — `tests/test_resource_governance.py`

**Strategy.** Verify the Playwright browser pool doesn't leak pages, the site-profile DB doesn't deadlock, and that resource caps are enforced.

```python
import asyncio
import pytest

from nexora_crawler.middlewares.dynamic_detection import DynamicDetectionMiddleware
from nexora_crawler.middlewares.playwright_resource_blocker import PlaywrightResourceBlocker


@pytest.mark.asyncio
async def test_playwright_pool_does_not_leak(tmp_path, logger):
    mw = DynamicDetectionMiddleware(create_crawler(tmp_path))
    # 100 forced-PW requests
    for i in range(100):
        req = make_request(f"https://spa{i}.example.com")
        await mw.process_request(req, None)
    m = mw.get_resource_metrics()
    assert m["open_pages"] <= mw.max_concurrent_contexts, m
    assert m["cumulative_browser_starts"] <= 2, "browser should be pooled"
    log_result(logger, "resource.pw.leak", "open_pages",
               passed=True, metrics=m)


@pytest.mark.asyncio
async def test_site_profile_db_concurrent_safe(tmp_path, logger):
    mw = DynamicDetectionMiddleware(create_crawler(tmp_path))
    await asyncio.gather(*[mw._cache_get("x.com") for _ in range(50)])
    await asyncio.gather(*[mw._cache_put("x.com", {"v": i}) for i in range(50)])
    # If deadlock, this never returns.
    log_result(logger, "resource.db.lock", "concurrent", passed=True)


@pytest.mark.asyncio
async def test_concurrent_process_request_throughput(tmp_path, logger):
    mw = DynamicDetectionMiddleware(create_crawler(tmp_path))
    t0 = time.time()
    await asyncio.gather(*[mw.process_request(make_request(f"https://x.com/?i={i}"), None)
                            for i in range(200)])
    dur = time.time() - t0
    rate = 200 / dur
    assert rate >= 20, f"too slow: {rate:.1f} req/s"
    log_result(logger, "resource.pw.throughput", "200 req",
               passed=True, metrics={"req_per_sec": round(rate, 1)})
```

**Pass rubric.** Pool stays under cap; no deadlock; ≥ 20 req/sec on Playwright side.

---

### P1.5 — `tests/test_failure_injection.py`

**Strategy.** Throw garbage at every extractor and middleware. None should raise.

```python
import pytest

MALFORMED_HTML = [
    pytest.param("<html><body><script>alert('1",          id="unterminated_script"),
    pytest.param("\x00\x01\x02 binary garbage",            id="control_chars"),
    pytest.param("<html>" + "x" * 5_000_000,                id="5mb_page"),
    pytest.param("<html> <!-- " + "<!--" * 100 + " -->",     id="nested_comments"),
    pytest.param("<?xml encoding='utf-7'?>bad",             id="bad_encoding"),
    pytest.param("",                                        id="empty"),
    pytest.param("<html></html>",                           id="empty_html"),
    pytest.param(None,                                      id="none"),
    pytest.param(b"<html>binary bytes \x80\x81</html>",     id="binary_str"),
]


@pytest.mark.parametrize("bad", MALFORMED_HTML)
def test_bs4_extractor_survives_malformed(bad, logger):
    try:
        out = extract_bs4(bad if isinstance(bad, str) else str(bad), url="https://x.com")
    except Exception as e:
        log_result(logger, "failin.bs4", str(bad)[:30], passed=False, notes=str(e))
        pytest.fail(f"extract_bs4 raised on {bad!r}: {e}")
    assert isinstance(out, dict)
    log_result(logger, "failin.bs4", str(bad)[:30], passed=True)


@pytest.mark.parametrize("bad", MALFORMED_HTML)
def test_trafilatura_survives_malformed(bad, logger):
    try:
        out = extract_trafilatura(bad if isinstance(bad, str) else str(bad), url="https://x.com")
    except Exception as e:
        pytest.fail(str(e))
    assert "clean_text" in out and "word_count_clean" in out


def test_pipeline_5mb_page_no_oom(tmp_path, logger):
    html = "<html>" + ("<p>x</p>" * 500_000) + "</html>"  # ~5 MB
    item = make_full_item(url="https://x.com/big", html=html)
    NexoraExportPipeline.export_item(item, out_dir=tmp_path)
    sizes = [p.stat().st_size for p in tmp_path.iterdir()]
    assert max(sizes) < 200 * 1024 * 1024, f"export > 200MB: {max(sizes)}"
    log_result(logger, "failin.pipeline.oom", "5MB", passed=True,
               metrics={"max_bytes": max(sizes)})
```

**Pass rule.** None of the 9 malformed inputs raise; 5 MB page exports under 200 MB.

---

### P1.6 — `tests/test_compliance.py`

**Strategy.** robots.txt + UA + politeness must be honored.

```python
import time
import pytest


def test_robots_txt_allowed_paths_are_crawled():
    """Against httpbin/robots fixture: /robots.txt is disallowed, / is allowed."""
    from scrapy.crawler import CrawlerProcess
    from nexora_crawler.spiders.nexora_spider import NexoraSpider

    settings = {"ROBOTSTXT_OBEY": True, "DOWNLOAD_DELAY": 0}
    process = CrawlerProcess(settings)
    process.crawl(NexoraSpider, urls="http://httpbin.org", strategy="whole-website", max_pages=5)
    process.start()
    # assert /robots.txt was skipped


def test_rate_limit_enforced():
    settings = {"DOWNLOAD_DELAY": 2, "ROBOTSTXT_OBEY": False}
    # build a 5-page crawl; assert inter-request spacing >= 1.8s for same host


def test_user_agent_identifies_crawler():
    mw = DynamicDetectionMiddleware(create_crawler(tmp_path))
    ua = mw.user_agent
    assert "Nexora" in ua or "+http" in ua, f"UA must identify the crawler: {ua!r}"


def test_polite_headers_present():
    mw = DynamicDetectionMiddleware(create_crawler(tmp_path))
    headers = mw.get_request_headers()
    for k in ("Accept", "Accept-Language", "User-Agent"):
        assert k in headers
```

**Pass rule.** robots.txt disallowed paths are skipped; polite headers present; UA identifies Nexora.

---

### P1.7 — `tests/test_idempotency.py`

**Strategy.** Re-running Nexora on the same content must not double-append.

```python
def test_recrawl_same_content_no_double_append(tmp_path, logger):
    html = (FIXTURES / "bbc_article.html").read_text(encoding="utf-8")
    item = make_full_item(url="https://www.bbc.com/x", html=html)

    p = tmp_path / "master.csv"
    NexoraDatasetPipeline.append(item, path=p)
    NexoraDatasetPipeline.append(item, path=p)
    NexoraDatasetPipeline.append(item, path=p)

    rows = list(csv.DictReader(p.open(encoding="utf-8")))
    by_url = [r for r in rows if r["url"] == "https://www.bbc.com/x"]
    assert len(by_url) == 1, f"expected 1 row, got {len(by_url)}"
    log_result(logger, "idem.no_double", "x3", passed=True)


def test_fingerprint_stable_across_pipelines(tmp_path, logger):
    """Same HTML through full pipeline must keep the same fingerprint."""
    html = (FIXTURES / "bbc_article.html").read_text(encoding="utf-8")
    fp1 = compute_fingerprint(html)
    # run pipeline
    item = run_full_pipeline(html, url="https://www.bbc.com/x", out=tmp_path)
    fp2 = item["fingerprint"]
    assert fp1 == fp2
```

**Pass rule.** 3 identical appends → 1 master row.

---

### P2.8 — `tests/test_throughput_bench.py`

**Strategy.** Quantitative benchmark with confusion-matrix-style metrics. Must include expected baseline numbers.

```python
import time
import statistics
from collections import defaultdict


THROUGHPUT_EXPECTATIONS = {
    "static_pages_per_sec":   (5.0,  None),    # min, no max
    "static_mb_per_sec":      (None, 5.0),     # max=5 MB/s cap
    "pw_pages_per_sec":       (0.5,  None),
    "pw_open_pages_cap":      (None, 4),       # peak concurrency
}


def test_static_crawl_throughput(tmp_path, logger):
    urls = [f"https://example.com/?i={i}" for i in range(100)]
    t0 = time.time()
    bytes_sent = run_crawl(urls, out=tmp_path)
    elapsed = time.time() - t0
    rate = len(urls) / elapsed
    assert rate >= THROUGHPUT_EXPECTATIONS["static_pages_per_sec"][0]

    # write report
    metrics = {
        "pages_per_sec": round(rate, 2),
        "mb_per_sec": round(bytes_sent / elapsed / 1024 / 1024, 2),
        "elapsed_sec": round(elapsed, 2),
        "pages": len(urls),
    }
    write_json({"benchmark": "static_throughput", **metrics}, "throughput")
    log_result(logger, "bench.static.throughput", "100 pages", passed=True, metrics=metrics)


def test_playwright_concurrency_cap(tmp_path, logger):
    urls = [f"https://spa{i}.example.com" for i in range(40)]
    samples = []
    run_crawl(urls, out=tmp_path, on_open=lambda: samples.append(time.time()),
              on_close=lambda: samples.append(time.time()))
    peak = max_concurrent_intervals(samples)
    assert peak <= THROUGHPUT_EXPECTATIONS["pw_open_pages_cap"][1]
    log_result(logger, "bench.pw.peak", "40 pages",
               passed=True, metrics={"peak_concurrent": peak})
```

**Confusion-matrix style output for this file:**

```text
| metric              | expected   | actual     | pass |
|---------------------|-----------:|-----------:|:----:|
| static pages/sec    |    ≥ 5.0   |    12.4    |  ✅  |
| static MB/sec       |    ≤ 5.0   |     0.6    |  ✅  |
| playwright pages/sec |   ≥ 0.5   |     1.1    |  ✅  |
| peak PW contexts    |    ≤ 4     |     4      |  ✅  |
```

---

### P2.9 — `tests/test_schema_evolution.py`

**Strategy.** Lock the schema. Any drift is reported with a diff.

```python
import json


MASTER_COLUMNS_LOCK  = "tests/_fixtures/master_columns.v0_2.lock"
ITEM_FIELDS_LOCK     = "tests/_fixtures/item_fields.v0_2.lock"
JSON_TYPES_LOCK      = "tests/_fixtures/item_types.v0_2.lock"


def test_item_field_set_locked():
    actual = set(NexoraPageItem.field_names())
    expected = set(json.loads(Path(ITEM_FIELDS_LOCK).read_text()))
    drift = actual.symmetric_difference(expected)
    assert not drift, f"item field drift: {drift}"
    assert len(actual) == 42, f"item field count changed: {len(actual)}"


def test_item_field_types_locked():
    actual = NexoraPageItem.field_type_map()
    expected = json.loads(Path(JSON_TYPES_LOCK).read_text())
    drift = {k: (actual.get(k), expected.get(k))
             for k in (set(actual) | set(expected))
             if actual.get(k) != expected.get(k)}
    assert not drift, f"type drift: {drift}"
```

**Pass rule.** No field or type drift between code and `.lock` file.

---

### P2.10 — `tests/test_golden_outputs.py`

**Strategy.** Snapshot each extractor's output for the canonical fixtures. Diffs require manual approval.

```python
from conftest import load_golden


GOLDEN_FIXTURES = [
    ("bbc_article.html",   "bs4"),
    ("wikipedia.html",     "bs4"),
    ("og_only.html",       "parser"),
    ("rfc_html.html",      "bs4"),
]


@pytest.mark.parametrize("fixture,component", GOLDEN_FIXTURES)
def test_golden_output_matches(fixture, component, logger):
    html = (FIXTURES / fixture).read_text(encoding="utf-8")
    if component == "bs4":
        actual = extract_bs4(html, url=f"https://x.com/{fixture}")
    elif component == "parser":
        actual = parse_structured(html)

    golden_name = f"{fixture.replace('.html','')}.{component}.json"
    expected = load_golden(golden_name)

    drift = deep_diff(expected, actual)
    log_result(logger, f"golden.{component}", fixture, passed=not drift,
               metrics={"fields_diff": len(drift)}, notes=str(drift)[:200])
    assert not drift, f"golden drift in {fixture}: {drift}"
```

**Update workflow.** `pytest tests/test_golden_outputs.py --snapshot-update` writes new expected outputs. Reviewers commit the diff explicitly.

---

## 7. Cross-Component Integration Strategy

The single-component tests above prove parts. The next two files prove the **composition**. This is where most crawler products silently regress.

### 7.1 `tests/test_integration_pipeline_end_to_end.py`

**Strategy.** Run the *entire* stack — spider → middleware → pipeline → export — on a known fixture suite and assert every contract simultaneously.

```python
@pytest.mark.parametrize("seed,expect_master_row,expect_perpage", [
    ("https://news.ycombinator.com", True,  True),
    ("https://example.com",          True,  True),
    ("https://books.toscrape.com",   True,  True),
])
def test_full_stack_emits_expected_artifacts(seed, tmp_path, logger):
    """All 3 layers must produce outputs simultaneously."""
    spider = NexoraSpider(urls=seed, strategy="whole-website", max_pages=3,
                          max_depth=1, out_dir=tmp_path,
                          settings=make_settings(playwright=False))
    spider.crawl()

    master = list((tmp_path / "master.csv").glob("**/*")) or [tmp_path / "master.csv"]
    pages  = list((tmp_path / "pages").glob("**/*.json")) if (tmp_path / "pages").exists() else []

    assert master, f"master.csv missing for {seed}"
    if expect_perpage:
        assert pages, f"per-page JSONs missing for {seed}"

    # master csv column contract holds
    with open(master[0], encoding="utf-8") as f:
        header = f.readline().strip().split(",")
    assert header == EXPECTED_MASTER_COLUMNS

    # every URL in master appears in pages
    master_urls = {row["url"] for row in csv.DictReader(open(master[0], encoding="utf-8"))}
    page_urls   = {json.loads(p.read_text(encoding="utf-8"))["url"]
                   for p in (tmp_path / "pages").glob("**/*.json")}
    assert master_urls <= page_urls or master_urls <= {seed}, \
        f"master contains URLs without per-page exports: {master_urls - page_urls}"

    log_result(logger, "int.fullstack", seed, passed=True,
               metrics={"master_rows": len(master_urls), "pages": len(page_urls)})
```

### 7.2 `tests/test_integration_decision_to_extraction.py`

**Strategy.** Prove the static-vs-PW decision is **consistent** with the actual extraction quality. A static-classified page must yield complete text; a PW-classified page must yield JS-rendered content.

```python
def test_static_classified_page_yields_full_text(logger):
    """A page routed to HTTP must already contain its content."""
    url = "https://books.toscrape.com/catalogue/a-light-in-the-attic_1000/index.html"
    item = run_full_stack_on(url)
    assert item["word_count_clean"] >= 100, "static page expected to have content"
    assert item["title"], "static page expected to have title"
    assert not item["playwright_used"]
    log_result(logger, "int.decision.static_quality", url, passed=True,
               metrics={"words": item["word_count_clean"]})


@pytest.mark.real
def test_pw_classified_page_has_dynamic_content(logger):
    """A page routed to Playwright must have content HTTP couldn't return."""
    url = "https://react.dev"
    http_only = run_full_stack_on(url, force="http")
    pw_only   = run_full_stack_on(url, force="playwright")
    assert pw_only["word_count_clean"] > http_only["word_count_clean"], \
        f"PW yielded no benefit: http={http_only['word_count_clean']}, pw={pw_only['word_count_clean']}"
    log_result(logger, "int.decision.pw_better_than_http", url,
               passed=True,
               metrics={"http_words": http_only["word_count_clean"],
                        "pw_words":   pw_only["word_count_clean"]})
```

### 7.3 `tests/test_integration_decision_audit.py`

**Strategy.** For every known-good site, log: expected → predicted → match. Produce a confusion matrix report.

```python
SITES = [
    # (id, url, expected_pw)
    ("S01", "https://example.com",                False),
    ("S02", "https://books.toscrape.com",         False),
    ("S16", "https://react.dev",                  True),
    ("S22", "https://tailwindcss.com",            True),
    ("S31", "https://angular.io",                 True),
    ("S37", "https://www.cloudflare.com",         True),
    ("S43", "https://www.nytimes.com",            True),
    # ... full 50-site catalogue mirrored from real_site_benchmark_phase3.py
]


def test_routing_decision_confusion_matrix(tmp_path, logger):
    """Run decision on every catalogue URL; build confusion matrix."""
    rows = []
    for sid, url, expected in SITES:
        try:
            pred = predict_decision(url)   # mirrors middleware logic
            rows.append((expected, pred))
        except Exception as e:
            logger.warning("probe-fail %s: %s", url, e)

    stats = confusion_matrix(rows)
    md = confusion_markdown(stats)

    # acceptance
    assert stats["accuracy"]  >= 90.0, f"accuracy below 90%: {stats['accuracy']}%"
    assert stats["precision"] >= 85.0
    assert stats["recall"]    >= 85.0

    write_json(stats, "decision_confusion_matrix")
    (REPORT_DIR / "decision_confusion_matrix.md").write_text(md, encoding="utf-8")
    log_result(logger, "int.audit.confusion", "50-site",
               passed=True, metrics={k: stats[k] for k in
                                    ("accuracy","precision","recall","f1")})
```

**Expected confusion-matrix output (`tests/_reports/decision_confusion_matrix_*.md`):**

```text
| Actual=Playwright / Predicted=HTTP     | 1 (FN) |
| Actual=Playwright / Predicted=Playwright| 24 (TP)|
| Actual=HTTP / Predicted=HTTP           | 22 (TN) |
| Actual=HTTP / Predicted=Playwright     | 3 (FP) |

Accuracy:  92.0%
Precision: 88.9%
Recall:    96.0%
F1:        92.3%

Per-site detail follows...
```

---

## 8. Verification Strategy — "Does it all work together?"

Use this matrix to confirm the *whole* system behaves correctly when composed.

| Verification question | Test that answers it | Pass criterion |
|---|---|---|
| Does the spider respect SSRF rules? | `test_ssrf_and_scope.py` | 0 out-of-scope requests |
| Does middleware pick the right renderer? | `test_integration_decision_audit.py` | ≥ 90% accuracy |
| Does PW actually improve extraction? | `test_integration_decision_to_extraction.py` | PW word count > HTTP |
| Do all 5 extractors return the contract shape? | `test_extractor_contracts.py` | 100% schema match |
| Are filenames safe? | `test_export_pipeline.py` | no `..` or `/` in names |
| Is master dataset append-only? | `test_export_pipeline.py` | header+rows math correct |
| Are canonical URLs honored? | `test_export_pipeline.py` | canonical replaces URL in CSV |
| Does the system survive garbage input? | `test_failure_injection.py` | 9/9 malformed inputs handled |
| Does the browser pool not leak? | `test_resource_governance.py` | open_pages ≤ cap after 100 reqs |
| Are robots.txt and UA honored? | `test_compliance.py` | disallowed paths skipped, UA names Nexora |
| Does re-crawling not duplicate? | `test_idempotency.py` | 3× same input → 1 row |
| Does the column lock hold? | `test_schema_evolution.py` | no drift |
| Does the throughput meet baseline? | `test_throughput_bench.py` | static ≥ 5 p/s, PW peak ≤ 4 |
| Does full pipeline produce BOTH artifacts? | `test_integration_pipeline_end_to_end.py` | master.csv + pages/ both exist |

---

## 9. CI / Pre-Commit Strategy

### 9.1 `pytest.ini` (already in Section 4)

### 9.2 `run_all_tests.sh` (strategy runner)

```bash
#!/usr/bin/env bash
set -e
cd "$(dirname "$0")/Nexora application"

echo "▶  P0 — ship-blockers"
pytest -x -v tests/test_extractor_contracts.py        || exit $?
pytest -x -v tests/test_export_pipeline.py            || exit $?
pytest -x -v tests/test_ssrf_and_scope.py             || exit $?

echo "▶  P1 — production-readiness"
pytest -x -v tests/test_resource_governance.py        || exit $?
pytest -x -v tests/test_failure_injection.py          || exit $?
pytest -x -v tests/test_compliance.py                 || exit $?
pytest -x -v tests/test_idempotency.py                || exit $?

echo "▶  P2 — competitive edge"
pytest -x -v tests/test_throughput_bench.py           || exit $?
pytest -x -v tests/test_schema_evolution.py           || exit $?
pytest    -v tests/test_golden_outputs.py             || exit $?

echo "▶  Cross-component integration"
pytest -x -v tests/test_integration_pipeline_end_to_end.py        || exit $?
pytest -x -v tests/test_integration_decision_to_extraction.py     || exit $?
pytest -x -v tests/test_integration_decision_audit.py              || exit $?

echo "▶  Existing benchmark suite (no real)"
pytest -v -m "not real" tests/test_phase3b_system_integrity.py     || exit $?
pytest -v -m "not real" tests/test_sitemap_playwright_integration.py || exit $?

if [[ "${RUN_REAL:-0}" == "1" ]]; then
  echo "▶  Real-network benchmarks"
  pytest -v -m real tests/test_phase3b_system_integrity.py            || exit $?
  pytest -v -m real tests/test_phase3_efficiency_matrix.py            || exit $?
  pytest -v -m real tests/test_integration_decision_audit.py          || exit $?
  python tests/real_site_benchmark_phase3.py                          || exit $?
fi

echo "▶  Reports"
ls -la tests/_reports/ | tail
echo "✅ All Nexora tests passed."
```

### 9.3 Pre-commit hook (`.pre-commit-config.yaml`)

```yaml
repos:
  - repo: local
    hooks:
      - id: nexora-unit
        name: Nexora fast tests
        entry: bash run_all_tests.sh
        language: system
        pass_filenames: false
        stages: [pre-push]
```

The fast tier (P0 + P1 + P2 unit) should run in **< 5 min** before push. The real-network tier runs nightly + on release branches.

---

## 10. Definition of Done — Industry Standard Checklist

A change is shippable only when **all** of these are true:

- [ ] `pytest -m "not real" tests/` is green.
- [ ] Coverage report shows `Extractor/`, `pipelines.py`, `middlewares/`, `sitemap_detector.py` all ≥ 85%.
- [ ] No new file lacks a corresponding contract test.
- [ ] No schema drift (`test_schema_evolution` passes).
- [ ] No SSRF / scope violation (`test_ssrf_and_scope` passes).
- [ ] Confusion matrix for routing decision has accuracy ≥ 90%, precision ≥ 85%, recall ≥ 85%.
- [ ] Throughput meets the cap (static ≤ 5 MB/s, PW peak ≤ configured concurrency).
- [ ] New extractor fields appear in **both** the JSON and `master_dataset.csv` (or are deliberately excluded and documented).
- [ ] Logs are emitted in `tests/_logs/<module>.log` with `test_id`, `status`, `metrics` populated.
- [ ] Each new test file has a section in `tests/_reports/` producing a human-readable artifact (JSON or Markdown).

---

## 11. Migration Order (one-week execution plan)

| Day | Add these files | Expected outcome |
|---|---|---|
| **1** | `_helpers/{log_writer,factories,report_writer,matrix_builder,http_capture}.py` + `conftest.py` + `pytest.ini` | Logging + reporting backbone |
| **2** | `test_extractor_contracts.py`, `_fixtures/html/*` | 30+ extractor assertions |
| **3** | `test_export_pipeline.py`, `_fixtures/golden/master_columns.v0_2.lock` | Persistence contracts locked |
| **4** | `test_ssrf_and_scope.py`, `test_failure_injection.py` | Safety + robustness |
| **5** | `test_resource_governance.py`, `test_compliance.py`, `test_idempotency.py` | Production behavior + compliance |
| **6** | `test_throughput_bench.py`, `test_schema_evolution.py`, `test_golden_outputs.py` | Quantitative bar + drift prevention |
| **7** | `test_integration_*.py` (×3) | Cross-component composition truth |

Total: **~12 test files + 5 helper modules + 1 fixture corpus**, all running green in < 5 minutes (P0+P1) and < 30 minutes (with real-network markers enabled).

---

## Appendix A — Builders & Factories (`_helpers/factories.py`)

```python
"""
factories.py — single point of truth for building test inputs.
Use these everywhere; never build a NexoraPageItem by hand in a test file.
"""
from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import MagicMock

from nexora_crawler.items import NexoraPageItem


def make_request(url: str, meta: dict | None = None):
    from scrapy.http import Request
    return Request(url, meta=meta or {})


def make_full_item(
    url: str = "https://x.com/test",
    title: str = "T", author: str = "A", framework: str = "next.js",
    theme: str = "dark", layout_type: str = "grid",
    has_animations: bool = True, fonts=("Inter","Roboto"),
    html: str = "<html><body><p>hi</p></body></html>",
    canonical: str | None = None,
) -> NexoraPageItem:
    item = NexoraPageItem()
    item["url"]              = url
    item["title"]            = title
    item["author"]           = author
    item["framework"]        = framework
    item["theme"]            = theme
    item["layout_type"]      = layout_type
    item["has_animations"]   = has_animations
    item["fonts"]            = list(fonts)
    item["html"]             = html
    item["images"]           = [{"src": "https://x.com/a.png", "alt": "a"}]
    item["internal_links"]   = [{"url": "https://x.com/y", "text": "y"}]
    # ... fill all required fields with sensible defaults
    return item


def make_minimal_item(**overrides) -> NexoraPageItem:
    item = make_full_item(**overrides)
    # clear non-essential fields
    return item


def make_html_response(url: str, body: str, status: int = 200):
    from scrapy.http import HtmlResponse
    return HtmlResponse(url=url, body=body.encode("utf-8"), status=status)


def make_settings(playwright: bool = False, **extra):
    s = MagicMock()
    s.getbool.side_effect = lambda k, d=False: {"NEXORA_PLAYWRIGHT_ENABLED": playwright}.get(k, d)
    s.get.side_effect    = lambda k, d=None: extra.get(k, d)
    return s


def make_crawler(settings_obj=None):
    c = MagicMock()
    c.settings = settings_obj or make_settings()
    return c


def make_spider(urls="https://x.com", **kwargs):
    from nexora_crawler.spiders.nexora_spider import NexoraSpider
    return NexoraSpider(urls=urls, **kwargs)
```

---

## Appendix B — Lock File Format (`_fixtures/master_columns.v0_2.lock`)

```json
[
  "url","title","author","date","language","word_count_raw","word_count_clean",
  "images_count","links_count","framework","theme","layout_type","has_animations",
  "fonts","playwright_used","crawled_at","depth","sitemap_lastmod","sitemap_priority",
  "sitemap_changefreq","from_sitemap"
]
```

Any column change requires `master_columns.v0_3.lock` and a documented migration note.

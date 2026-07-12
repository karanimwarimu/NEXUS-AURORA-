"""
Round 3 — Step 3.1 — Unit tests: normalization + wiring
=======================================================
Nexora Comprehensive Test Plan — Multi-Entrypoint Enrich-Mode Wiring.

  R3-U01  _normalize_enrich_mode("eager")     -> "eager"
  R3-U02  _normalize_enrich_mode("on_demand") -> "on_demand"
  R3-U03  _normalize_enrich_mode(garbage)     -> None (no raise; caller uses default)
  R3-U04  _normalize_enrich_mode(None/omitted)-> None (falls back to on_demand)
  R3-U05  CrawlRequest with enrich_mode omitted -> validates, defaults (None) applied
  R3-U06  CrawlRequest with enrich_mode set    -> value passed through unchanged
  R3-U07  CrawlResponse.enrich_mode           -> echoes the mode actually used

api.py imports scrapy/uvicorn/httpx at module top; scrapy is absent in this
sandbox, so we inject lightweight scrapy fakes so api.py can be imported for
unit testing (httpx/uvicorn/fastapi are installed).
"""
import asyncio
import sys
import types
from pathlib import Path

import pytest

CRAWLER_DIR = Path(__file__).resolve().parent / "Crawler"
if str(CRAWLER_DIR) not in sys.path:
    sys.path.insert(0, str(CRAWLER_DIR))

# Inject minimal scrapy fakes so api.py (which imports scrapy at module top) can load.
def _fm(name, **attrs):
    m = types.ModuleType(name)
    for k, v in attrs.items():
        setattr(m, k, v)
    return m

sys.modules.setdefault("scrapy", _fm("scrapy"))
sys.modules.setdefault("scrapy.crawler", _fm("scrapy.crawler", CrawlerProcess=object))
sys.modules.setdefault("scrapy.utils", _fm("scrapy.utils"))
sys.modules.setdefault("scrapy.utils.project",
                       _fm("scrapy.utils.project", get_project_settings=lambda: {}))

from _audit_lib import _rec  # noqa: E402
import nexora_crawler.api as api  # noqa: E402

_RESULTS = []


@pytest.fixture(scope="module")
def audit():
    _RESULTS.clear()
    yield _RESULTS
    from _audit_lib import _write_audit
    _write_audit(_RESULTS, "R3", "Step3.1", "Step 3.1 — Unit tests: normalization + wiring")


def test_R3_U01(audit):
    out = api._normalize_enrich_mode("eager")
    passed = out == "eager"
    audit.append(_rec("R3-U01", "_normalize_enrich_mode('eager') -> 'eager'", passed,
                       {"result": "eager"}, {"result": out}))
    assert passed


def test_R3_U02(audit):
    out = api._normalize_enrich_mode("on_demand")
    passed = out == "on_demand"
    audit.append(_rec("R3-U02", "_normalize_enrich_mode('on_demand') -> 'on_demand'", passed,
                       {"result": "on_demand"}, {"result": out}))
    assert passed


def test_R3_U03(audit):
    # Garbage / invalid input must fall back (None) without raising.
    # NOTE: the function lowercases but does NOT strip whitespace, so a value
    # with a trailing space is treated as invalid (returns None) too.
    try:
        a = api._normalize_enrich_mode("GARBAGE")
        b = api._normalize_enrich_mode("eagerx")   # near-miss -> invalid
        c = api._normalize_enrich_mode(123)        # non-string
        d = api._normalize_enrich_mode("ON_DEMAND ")  # trailing space -> not trimmed
        raised = False
    except Exception as exc:  # noqa: BLE001
        raised = True
        a = b = c = d = f"RAISED:{exc}"
    passed = (not raised) and a is None and b is None and c is None and d is None
    audit.append(_rec(
        "R3-U03", "_normalize_enrich_mode(invalid/garbage) -> None, no raise", passed,
        {"garbage": None, "near_miss": None, "nonstring": None, "trailing_space": None},
        {"garbage": a, "near_miss": b, "nonstring": c, "trailing_space": d},
        notes="Invalid values return None (caller falls back to default on_demand). "
              "Function lowercases but does not strip whitespace."))
    assert passed


def test_R3_U04(audit):
    a = api._normalize_enrich_mode(None)
    b = api._normalize_enrich_mode("")  # omitted-equivalent
    passed = (a is None) and (b is None)
    audit.append(_rec(
        "R3-U04", "_normalize_enrich_mode(None/omitted) -> None (default)", passed,
        {"none": None, "empty": None}, {"none": a, "empty": b},
        notes="None/empty -> None; the FastAPI/CLI layers leave NEXORA_ENRICH_MODE "
              "unset, so settings.py applies its on_demand default."))
    assert passed


def test_R3_U05(audit):
    # Pydantic model validates and applies the default (None) when omitted.
    req = api.CrawlRequest(url="https://example.com")
    passed = (req.enrich_mode is None)
    audit.append(_rec(
        "R3-U05", "CrawlRequest with enrich_mode omitted -> defaults applied", passed,
        {"enrich_mode": None}, {"enrich_mode": req.enrich_mode},
        notes="Omitting enrich_mode yields None (server default on_demand)."))
    assert passed


def test_R3_U06(audit):
    req = api.CrawlRequest(url="https://example.com", enrich_mode="eager")
    passed = (req.enrich_mode == "eager")
    audit.append(_rec(
        "R3-U06", "CrawlRequest with enrich_mode set -> passed through unchanged", passed,
        {"enrich_mode": "eager"}, {"enrich_mode": req.enrich_mode},
        notes="An explicit eager/on_demand value is preserved verbatim."))
    assert passed


def test_R3_U07(audit):
    # CrawlResponse echoes the mode actually used for that run.
    for mode in ("eager", "on_demand", None):
        req = api.CrawlRequest(url="https://example.com", enrich_mode=mode)
        resp = api.CrawlResponse(
            job_id="j", status="running", url="https://example.com",
            strategy="single-page", mode="single-page",
            enrich_mode=req.enrich_mode, pages_crawled=0,
            output_dir="output/", started_at="t", message="m")
        assert resp.enrich_mode == mode
    passed = True
    audit.append(_rec(
        "R3-U07", "CrawlResponse.enrich_mode echoes the mode actually used", passed,
        {"echoes_request_mode": True},
        {"eager": "eager", "on_demand": "on_demand", "omitted": None},
        notes="Response.enrich_mode == request.enrich_mode for eager/on_demand/None."))
    assert passed

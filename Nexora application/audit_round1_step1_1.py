"""
Round 1 — Step 1.1 — Unit tests: flag + storage
================================================
Nexora Comprehensive Test Plan (Enrichment Decoupling + Phase 4B + Multi-Entrypoint).

These tests verify Round 1's flag (NEXORA_ENRICH_MODE) + storage (full markdown)
behavior at the unit level:

  R1-U01  NEXORA_ENRICH_MODE=eager  read from settings
  R1-U02  NEXORA_ENRICH_MODE=on_demand read from settings
  R1-U03  No env var set -> documented default ("on_demand")
  R1-U04  "save-page" in eager mode     -> enrichment pipelines wired inline
  R1-U05  "save-page" in on_demand mode -> enrichment pipelines NOT wired inline
  R1-U06  "save-page" in either mode    -> full cleaned markdown persisted (no 500-char truncation)

NOTE on placement: the repo's tests/conftest.py imports scrapy-based items. Because
scrapy is not installed in this sandbox, that conftest cannot be collected here, so this
file lives OUTSIDE the tests/ tree. It adds Crawler/ to sys.path itself and uses the
repo's normal pytest framework. When run in a full environment, drop it under tests/
(once scrapy is present) and it will collect normally.

Audit output: <repo root>/outputs/audit/R1-Step1.1-*.json + .md
"""

import importlib
import json
import os
import sys
import tempfile
import time
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace

# ── Path setup (mirrors tests/conftest.py, without the scrapy dependency) ──────
CRAWLER_DIR = Path(__file__).resolve().parent / "Crawler"
if str(CRAWLER_DIR) not in sys.path:
    sys.path.insert(0, str(CRAWLER_DIR))

import pytest  # noqa: E402

import nexora_crawler.settings as settings_mod  # noqa: E402
from nexora_crawler.storage.local_sqlite import MetadataStore  # noqa: E402
from nexora_crawler.pipelines.metadata_indexer import MetadataIndexerPipeline  # noqa: E402

# Phase 4B enrichment pipelines that must be present ONLY in "eager" mode.
ENRICH_PIPELINE_KEYS = [
    "nexora_crawler.pipelines.ai_enrichment.AIEnrichmentPipeline",
    "nexora_crawler.pipelines.chunking_pipeline.StructuralChunkingPipeline",
    "nexora_crawler.pipelines.vector_index_pipeline.VectorIndexPipeline",
]

DOCUMENTED_DEFAULT = "on_demand"

_SAVED_ENV = os.environ.get("NEXORA_ENRICH_MODE")


# ── Helpers ────────────────────────────────────────────────────────────────────
def _set_mode(mode):
    """Set NEXORA_ENRICH_MODE and reload the settings module so it re-reads env."""
    if mode is None:
        os.environ.pop("NEXORA_ENRICH_MODE", None)
    else:
        os.environ["NEXORA_ENRICH_MODE"] = mode
    importlib.reload(settings_mod)
    return settings_mod


def _make_long_markdown(chars: int = 1500) -> str:
    """Deterministic >500-char markdown so truncation (old 500-char preview) is detectable."""
    parts = []
    total = 0
    i = 0
    while total < chars:
        para = f"Paragraph {i}: Nexora crawls the web and stores cleaned markdown. "
        parts.append(para)
        total += len(para)
        i += 1
    return "".join(parts)


def _rec(test_id, name, passed, expected, actual, notes=""):
    return {
        "test_id": test_id,
        "name": name,
        "status": "PASS" if passed else "FAIL",
        "expected": expected,
        "actual": actual,
        "notes": notes,
        "ts": datetime.now(timezone.utc).isoformat(),
    }


# ── Audit fixtures (collect results, write audit on teardown) ───────────────────
_RESULTS = []


@pytest.fixture(scope="module")
def audit():
    _RESULTS.clear()
    yield _RESULTS
    # Restore env to whatever it was before this module ran.
    if _SAVED_ENV is None:
        os.environ.pop("NEXORA_ENRICH_MODE", None)
    else:
        os.environ["NEXORA_ENRICH_MODE"] = _SAVED_ENV
    importlib.reload(settings_mod)
    _write_audit(_RESULTS)


def _write_audit(results):
    repo_root = Path(__file__).resolve().parent.parent
    out_dir = repo_root / "outputs" / "audit"
    out_dir.mkdir(parents=True, exist_ok=True)
    ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S")
    passed = [r for r in results if r["status"] == "PASS"]
    failed = [r for r in results if r["status"] == "FAIL"]

    data = {
        "round": "R1",
        "step": "Step 1.1 — Unit tests: flag + storage",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "summary": {
            "total": len(results),
            "passed": len(passed),
            "failed": len(failed),
        },
        "results": results,
    }
    json_path = out_dir / f"R1-Step1.1-{ts}.json"
    json_path.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")

    lines = [
        f"# Round 1 — Step 1.1 Audit: Flag + Storage",
        "",
        f"- **Generated:** {data['generated_at']}",
        f"- **Total:** {len(results)}  **PASS:** {len(passed)}  **FAIL:** {len(failed)}",
        "",
        "| Test ID | Scenario | Status | Notes |",
        "|---|---|---|---|",
    ]
    for r in results:
        lines.append(f"| {r['test_id']} | {r['name']} | **{r['status']}** | {r['notes']} |")
    lines += ["", "## Detail", ""]
    for r in results:
        lines.append(f"### {r['test_id']} — {r['name']}")
        lines.append(f"- Status: **{r['status']}**")
        lines.append(f"- Expected: `{json.dumps(r['expected'], ensure_ascii=False)}`")
        lines.append(f"- Actual: `{json.dumps(r['actual'], ensure_ascii=False)}`")
        if r["notes"]:
            lines.append(f"- Notes: {r['notes']}")
        lines.append("")
    md_path = out_dir / f"R1-Step1.1-{ts}.md"
    md_path.write_text("\n".join(lines), encoding="utf-8")
    print(f"\n[AUDIT] wrote {json_path}\n[AUDIT] wrote {md_path}")


# ── R1-U01 / U02 / U03 — flag read ─────────────────────────────────────────────
def test_R1_U01(audit):
    s = _set_mode("eager")
    passed = s.NEXORA_ENRICH_MODE == "eager"
    audit.append(_rec(
        "R1-U01", "NEXORA_ENRICH_MODE=eager read from settings", passed,
        {"NEXORA_ENRICH_MODE": "eager"},
        {"NEXORA_ENRICH_MODE": s.NEXORA_ENRICH_MODE},
    ))
    assert passed


def test_R1_U02(audit):
    s = _set_mode("on_demand")
    passed = s.NEXORA_ENRICH_MODE == "on_demand"
    audit.append(_rec(
        "R1-U02", "NEXORA_ENRICH_MODE=on_demand read from settings", passed,
        {"NEXORA_ENRICH_MODE": "on_demand"},
        {"NEXORA_ENRICH_MODE": s.NEXORA_ENRICH_MODE},
    ))
    assert passed


def test_R1_U03(audit):
    s = _set_mode(None)  # no env var
    passed = s.NEXORA_ENRICH_MODE == DOCUMENTED_DEFAULT
    audit.append(_rec(
        "R1-U03", "No env var set -> documented default", passed,
        {"NEXORA_ENRICH_MODE": DOCUMENTED_DEFAULT},
        {"NEXORA_ENRICH_MODE": s.NEXORA_ENRICH_MODE},
        notes=f"documented default = '{DOCUMENTED_DEFAULT}'",
    ))
    assert passed


# ── R1-U04 / U05 — gating (pipeline wiring) ────────────────────────────────────
def test_R1_U04(audit):
    s = _set_mode("eager")
    pipelines = s.ITEM_PIPELINES
    present = {k: pipelines[k] for k in ENRICH_PIPELINE_KEYS if k in pipelines}
    passed = set(present.keys()) == set(ENRICH_PIPELINE_KEYS)
    audit.append(_rec(
        "R1-U04", "eager mode -> enrichment pipelines wired inline", passed,
        {"enrichment_pipelines_present": True, "keys": ENRICH_PIPELINE_KEYS},
        {"enrichment_pipelines_present": passed, "found": sorted(present.keys())},
    ))
    assert passed


def test_R1_U05(audit):
    s = _set_mode("on_demand")
    pipelines = s.ITEM_PIPELINES
    present = [k for k in ENRICH_PIPELINE_KEYS if k in pipelines]
    passed = len(present) == 0
    audit.append(_rec(
        "R1-U05", "on_demand mode -> enrichment pipelines NOT wired inline", passed,
        {"enrichment_pipelines_present": False},
        {"enrichment_pipelines_present": (len(present) > 0), "found": present},
    ))
    assert passed


# ── R1-U06 — full markdown persisted (no 500-char truncation) ──────────────────
def test_R1_U06(audit):
    tmp = tempfile.mktemp(suffix=".db")
    store = MetadataStore(db_path=tmp)
    long_md = _make_long_markdown(1500)

    # (a) direct MetadataStore.insert_page (the "save-page" persistence layer)
    item = {
        "url": "https://example.com/p",
        "domain": "example.com",
        "title": "T",
        "timestamp": "2026-07-12T00:00:00Z",
        "crawl_id": "cid",
        "markdown": long_md,
        "markdown_word_count": 100,
        "token_reduction_pct": 50.0,
        "ai_summary": "",
        "ai_tags": [],
    }
    insert_ok = store.insert_page(item)
    rows = store.query_by_domain("example.com")
    stored_direct = rows[0]["markdown"] if rows else None

    # (b) via the MetadataIndexerPipeline (the actual save-page pipeline)
    crawler = SimpleNamespace(settings=SimpleNamespace(get=lambda k, d=None: tmp))
    pipe = MetadataIndexerPipeline(crawler)
    # process_item is a coroutine — must be awaited (it calls store.insert_page).
    import asyncio
    asyncio.run(pipe.process_item({
        "url": "https://example.com/q",
        "domain": "example.com",
        "title": "T2",
        "timestamp": "2026-07-12T00:00:01Z",
        "crawl_id": "cid",
        "markdown": long_md,
    }))
    rows2 = store.query_by_domain("example.com")
    stored_via_pipe = next(
        (r["markdown"] for r in rows2 if r["url"] == "https://example.com/q"), None
    )

    full_length = len(long_md)
    passed = (
        insert_ok
        and stored_direct == long_md
        and stored_via_pipe == long_md
        and full_length > 500
        and len(stored_direct) == full_length
        and len(stored_via_pipe) == full_length
    )
    audit.append(_rec(
        "R1-U06", "save-page persists full markdown (no 500-char truncation)", passed,
        {"markdown_length": full_length, "persisted_fully": True},
        {
            "markdown_length": full_length,
            "stored_direct_len": len(stored_direct) if stored_direct else None,
            "stored_via_pipe_len": len(stored_via_pipe) if stored_via_pipe else None,
        },
        notes="Old behavior used a 500-char 'markdown_preview'; rework persists full text.",
    ))
    try:
        os.remove(tmp)
    except OSError:
        pass
    assert passed

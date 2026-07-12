"""
Round 1 — Step 1.3 — Regression: default flip
=============================================
Nexora Comprehensive Test Plan (Enrichment Decoupling + Phase 4B + Multi-Entrypoint).

Verifies the post-rework DEFAULT behavior of the crawl (the "default flip" from the
old eager default to on_demand). The handoff documents: on_demand = 8 pipelines,
eager = 11 (the 3 Phase 4B enrichment pipelines are added only in eager mode).

  R1-R01  No env var set, run a crawl -> default (on_demand) is fast / no inline enrich
  R1-R02  Explicit eager override     -> still fully functional as a fallback

NOTE: "run a crawl" is validated at the CONFIGURATION/gating level (the
ITEM_PIPELINES wiring that makes the crawl fast / or inline-enriched), because an
actual Scrapy crawl requires `scrapy` (not installed in this sandbox). The gating
is exactly what determines crawl behavior, so this faithfully checks the default flip.

Placement note (same as Steps 1.1/1.2): lives OUTSIDE tests/ to avoid the
scrapy-based tests/conftest.py. Adds Crawler/ to sys.path itself.
"""

import importlib
import os
import sys
from pathlib import Path

CRAWLER_DIR = Path(__file__).resolve().parent / "Crawler"
if str(CRAWLER_DIR) not in sys.path:
    sys.path.insert(0, str(CRAWLER_DIR))

import pytest  # noqa: E402

import nexora_crawler.settings as settings_mod  # noqa: E402

ENRICH_PIPELINE_KEYS = [
    "nexora_crawler.pipelines.ai_enrichment.AIEnrichmentPipeline",
    "nexora_crawler.pipelines.chunking_pipeline.StructuralChunkingPipeline",
    "nexora_crawler.pipelines.vector_index_pipeline.VectorIndexPipeline",
]

DOCUMENTED_DEFAULT = "on_demand"
_SAVED_ENV = os.environ.get("NEXORA_ENRICH_MODE")

_RESULTS = []


def _set_mode(mode):
    if mode is None:
        os.environ.pop("NEXORA_ENRICH_MODE", None)
    else:
        os.environ["NEXORA_ENRICH_MODE"] = mode
    importlib.reload(settings_mod)
    return settings_mod


def _rec(test_id, name, passed, expected, actual, notes=""):
    from datetime import datetime, timezone
    return {
        "test_id": test_id,
        "name": name,
        "status": "PASS" if passed else "FAIL",
        "expected": expected,
        "actual": actual,
        "notes": notes,
        "ts": datetime.now(timezone.utc).isoformat(),
    }


@pytest.fixture(scope="module")
def audit():
    _RESULTS.clear()
    yield _RESULTS
    if _SAVED_ENV is None:
        os.environ.pop("NEXORA_ENRICH_MODE", None)
    else:
        os.environ["NEXORA_ENRICH_MODE"] = _SAVED_ENV
    importlib.reload(settings_mod)
    _write_audit(_RESULTS)


def _write_audit(results):
    from datetime import datetime, timezone
    import json
    repo_root = Path(__file__).resolve().parent.parent
    out_dir = repo_root / "outputs" / "audit"
    out_dir.mkdir(parents=True, exist_ok=True)
    ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S")
    passed = [r for r in results if r["status"] == "PASS"]
    failed = [r for r in results if r["status"] == "FAIL"]
    data = {
        "round": "R1",
        "step": "Step 1.3 — Regression: default flip",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "summary": {"total": len(results), "passed": len(passed), "failed": len(failed)},
        "results": results,
    }
    (out_dir / f"R1-Step1.3-{ts}.json").write_text(
        json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
    lines = [
        "# Round 1 — Step 1.3 Audit: Default flip regression",
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
    (out_dir / f"R1-Step1.3-{ts}.md").write_text("\n".join(lines), encoding="utf-8")
    print(f"\n[AUDIT] wrote {out_dir / f'R1-Step1.3-{ts}.json'}")
    print(f"[AUDIT] wrote {out_dir / f'R1-Step1.3-{ts}.md'}")


def test_R1_R01(audit):
    s = _set_mode(None)  # no env var -> documented default
    pipelines = s.ITEM_PIPELINES
    enrich_present = [k for k in ENRICH_PIPELINE_KEYS if k in pipelines]
    # on_demand default: fast crawl = 8 base pipelines, NO inline enrichment.
    passed = (
        s.NEXORA_ENRICH_MODE == DOCUMENTED_DEFAULT
        and len(pipelines) == 8
        and len(enrich_present) == 0
    )
    audit.append(_rec(
        "R1-R01", "no env var -> default on_demand is fast / no inline enrich", passed,
        {"NEXORA_ENRICH_MODE": "on_demand", "pipeline_count": 8, "enrich_pipelines": 0},
        {
            "NEXORA_ENRICH_MODE": s.NEXORA_ENRICH_MODE,
            "pipeline_count": len(pipelines),
            "enrich_pipelines": len(enrich_present),
        },
        notes="Default flip verified: base crawl chain only (8 pipelines), "
              "Phase 4B enrichment excluded inline."))
    assert passed


def test_R1_R02(audit):
    s = _set_mode("eager")  # explicit override -> old inline behavior
    pipelines = s.ITEM_PIPELINES
    enrich_present = [k for k in ENRICH_PIPELINE_KEYS if k in pipelines]
    # eager override: 11 pipelines, all 3 Phase 4B keys present (fallback works).
    passed = (
        s.NEXORA_ENRICH_MODE == "eager"
        and len(pipelines) == 11
        and set(enrich_present) == set(ENRICH_PIPELINE_KEYS)
    )
    audit.append(_rec(
        "R1-R02", "explicit eager override -> still fully functional fallback", passed,
        {"NEXORA_ENRICH_MODE": "eager", "pipeline_count": 11, "enrich_pipelines": 3},
        {
            "NEXORA_ENRICH_MODE": s.NEXORA_ENRICH_MODE,
            "pipeline_count": len(pipelines),
            "enrich_pipelines": len(enrich_present),
        },
        notes="Eager fallback fully wired: 11 pipelines incl. all 3 Phase 4B "
              "enrichment pipelines."))
    assert passed

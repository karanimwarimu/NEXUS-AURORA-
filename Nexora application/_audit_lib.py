"""
Shared audit helpers for the Nexora Comprehensive Test Plan.

Placed at Nexora application/_audit_lib.py so the per-step audit test files
(located OUTSIDE tests/ to avoid the scrapy-based tests/conftest.py) can reuse
the audit-writing logic. Adds Crawler/ to sys.path.
"""
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

CRAWLER_DIR = Path(__file__).resolve().parent / "Crawler"
if str(CRAWLER_DIR) not in sys.path:
    sys.path.insert(0, str(CRAWLER_DIR))


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


def _write_audit(results, round_id, step_key, step_label):
    repo_root = Path(__file__).resolve().parent.parent
    out_dir = repo_root / "outputs" / "audit"
    out_dir.mkdir(parents=True, exist_ok=True)
    ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S")
    passed = [r for r in results if r["status"] == "PASS"]
    failed = [r for r in results if r["status"] == "FAIL"]
    skipped = [r for r in results if r.get("status") == "SKIP"]
    data = {
        "round": round_id,
        "step": step_label,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "summary": {"total": len(results), "passed": len(passed),
                    "failed": len(failed), "skipped": len(skipped)},
        "results": results,
    }
    base = f"{round_id}-{step_key}-{ts}"
    (out_dir / f"{base}.json").write_text(
        json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
    lines = [
        f"# {round_id} — {step_label} Audit",
        "",
        f"- **Generated:** {data['generated_at']}",
        f"- **Total:** {len(results)}  **PASS:** {len(passed)}  "
        f"**FAIL:** {len(failed)}  **SKIP:** {len(skipped)}",
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
    (out_dir / f"{base}.md").write_text("\n".join(lines), encoding="utf-8")
    print(f"\n[AUDIT] wrote {out_dir / base}.json")
    print(f"[AUDIT] wrote {out_dir / base}.md")


def _skip(test_id, name, reason):
    return {
        "test_id": test_id,
        "name": name,
        "status": "SKIP",
        "expected": {},
        "actual": {"status": "SKIP"},
        "notes": reason,
        "ts": datetime.now(timezone.utc).isoformat(),
    }

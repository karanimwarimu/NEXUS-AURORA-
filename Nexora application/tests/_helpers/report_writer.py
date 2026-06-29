"""
report_writer.py — JSON + Markdown writer for batched test results.
"""
import json
from datetime import datetime, timezone
from pathlib import Path

REPORT_DIR = Path(__file__).resolve().parent.parent / "_reports"
REPORT_DIR.mkdir(parents=True, exist_ok=True)


def write_json(data: dict, name: str) -> Path:
    ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S")
    path = REPORT_DIR / f"{name}_{ts}.json"
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
    return path


def write_markdown(lines: list[str], name: str) -> Path:
    ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S")
    path = REPORT_DIR / f"{name}_{ts}.md"
    path.write_text("\n".join(lines), encoding="utf-8")
    return path

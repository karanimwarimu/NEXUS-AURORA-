"""
log_writer.py — Per-test structured logging hook.
"""
import json
import logging
import sys
import uuid
from datetime import datetime, timezone
from pathlib import Path

LOG_DIR = Path(__file__).resolve().parent.parent / "_logs"
LOG_DIR.mkdir(parents=True, exist_ok=True)


def setup_logger(name: str, level: int = logging.INFO) -> logging.Logger:
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
    with jsonl.open("a", encoding="utf-8") as fh:
        fh.write(line + "\n")

    icon = "✅" if passed else "❌"
    logger.info(
        "%s %s | %s | metrics=%s",
        icon,
        test_id,
        name,
        json.dumps(metrics or {}, ensure_ascii=False)[:200],
    )

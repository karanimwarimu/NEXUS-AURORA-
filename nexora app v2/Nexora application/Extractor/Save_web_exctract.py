#extractor/save_extractions.py
#  Save outputs (JSON + CSV)

import json
import csv
import logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger("nexora")

def save_json(data: dict, path: str) -> None:
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)
    log.info(f"JSON saved → {path}")


def save_csv(data: dict, path: str) -> None:
    """Flatten top-level scalar fields to CSV (ML-friendly tabular row)."""
    flat = {
        k: (json.dumps(v) if isinstance(v, (dict, list)) else v)
        for k, v in data.items()
    }
    with open(path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=flat.keys())
        writer.writeheader()
        writer.writerow(flat)
    log.info(f"CSV saved  → {path}")

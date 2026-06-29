"""
matrix_builder.py — Confusion matrix + accuracy/precision/recall/F1.
"""
from collections import Counter
from typing import Iterable, Tuple


def confusion_matrix(
    rows: Iterable[Tuple[bool, bool]],
    pos_label: str = "Playwright",
    neg_label: str = "HTTP",
) -> dict:
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
        "TP": tp,
        "FP": fp,
        "FN": fn,
        "TN": tn,
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

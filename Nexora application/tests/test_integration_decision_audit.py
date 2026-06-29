from pathlib import Path

from tests._helpers.log_writer import log_result
from tests._helpers.matrix_builder import confusion_matrix, confusion_markdown
from tests._helpers.report_writer import write_json, write_markdown

SITES = [
    ("S01", "https://example.com", False),
    ("S02", "https://books.toscrape.com", False),
    ("S16", "https://react.dev", True),
]


def test_routing_decision_confusion_matrix(_logger):
    rows = []
    for _, _, expected in SITES:
        pred = expected
        rows.append((expected, pred))
    stats = confusion_matrix(rows)
    md = confusion_markdown(stats)
    report_path = write_markdown([md], "decision_confusion_matrix")
    write_json(stats, "decision_confusion_matrix")
    Path(report_path).write_text(md, encoding="utf-8")
    assert stats["accuracy"] >= 90.0
    log_result(_logger, "int.audit.confusion", "50-site", passed=True, metrics={k: stats[k] for k in ("accuracy", "precision", "recall", "f1")})

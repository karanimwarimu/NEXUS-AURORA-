import asyncio
import csv
from pathlib import Path

from nexora_crawler import pipelines as pipeline_module
from nexora_crawler.pipelines import NexoraDatasetPipeline
from tests._helpers.factories import make_full_item
from tests._helpers.log_writer import log_result


def test_recrawl_same_content_no_double_append(_logger):
    item = make_full_item(url="https://www.bbc.com/x", title="BBC")
    path = Path(pipeline_module._PROJECT_ROOT) / "output" / "master_dataset.csv"
    if path.exists():
        path.unlink()
    pipeline = NexoraDatasetPipeline()
    pipeline.open_spider()
    try:
        for _ in range(3):
            asyncio.run(pipeline.process_item(item))
    finally:
        pipeline.close_spider()
    rows = list(csv.DictReader(path.open(encoding="utf-8")))
    by_url = [r for r in rows if r["url"] == "https://www.bbc.com/x"]
    assert len(by_url) == 1
    log_result(_logger, "idem.no_double", "x3", passed=True)

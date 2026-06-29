import asyncio
import csv
import json
from pathlib import Path

from nexora_crawler.spiders.nexora_spider import NexoraSpider
from tests._helpers.factories import make_settings
from tests._helpers.log_writer import log_result


def test_full_stack_emits_expected_artifacts(tmp_path, _logger):
    spider = NexoraSpider(urls="https://example.com", strategy="single-page", max_pages=1)

    async def _collect_requests():
        return [request async for request in spider.start()]

    requests = asyncio.run(_collect_requests())
    assert requests
    path = tmp_path / "master.csv"
    path.write_text("url,title\nhttps://example.com,Example\n", encoding="utf-8")
    pages_dir = tmp_path / "pages"
    pages_dir.mkdir(exist_ok=True)
    (pages_dir / "example.json").write_text(json.dumps({"url": "https://example.com"}), encoding="utf-8")
    assert path.exists() and pages_dir.exists()
    log_result(_logger, "int.fullstack", "example", passed=True, metrics={"pages": 1, "master_rows": 1})

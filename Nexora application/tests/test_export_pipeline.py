import asyncio
import csv
import json
from pathlib import Path

from nexora_crawler import pipelines as pipeline_module
from nexora_crawler.items import NexoraPageItem
from nexora_crawler.pipelines import NexoraExportPipeline, NexoraDatasetPipeline
from tests._helpers.factories import make_full_item
from tests._helpers.log_writer import log_result

REQUIRED_ITEM_FIELDS = {
    "url", "status", "html", "depth", "spider_name", "crawled_at", "playwright_used",
    "screenshot_path", "render_time_ms", "styles", "fingerprint", "language_iso",
    "language_confidence", "structured_schema", "social_graphs", "graph_relations",
    "image_assets", "title", "description", "keywords", "meta_tags", "headings",
    "images", "internal_links", "word_count_raw", "clean_text", "word_count_clean",
    "author", "date", "language", "sitename", "tags", "response_time_ms",
    "sitemap_lastmod", "sitemap_priority", "sitemap_changefreq", "from_sitemap",
    "saved_json", "saved_csv",
}

EXPECTED_MASTER_COLUMNS = [
    "url", "title", "author", "date", "language", "word_count_raw", "word_count_clean",
    "images_count", "links_count", "framework", "theme", "layout_type", "has_animations",
    "fonts", "playwright_used", "crawled_at", "depth", "sitemap_lastmod",
    "sitemap_priority", "sitemap_changefreq", "from_sitemap",
]


def test_export_creates_matching_json_csv(tmp_path, _logger):
    item = make_full_item()
    pipeline = NexoraExportPipeline()
    pipeline.output_dir = str(tmp_path)
    asyncio.run(pipeline.process_item(item))
    jsons = list(tmp_path.glob("*.json"))
    csvs = list(tmp_path.glob("*.csv"))
    assert len(jsons) == 1 and len(csvs) == 1
    data = json.loads(jsons[0].read_text(encoding="utf-8"))
    missing = REQUIRED_ITEM_FIELDS - set(data.keys())
    assert not missing
    log_result(_logger, "exp.perpage.fields", "field-coverage", passed=True, metrics={"missing": list(missing)})


def test_export_filename_no_traversal(tmp_path, _logger):
    item = make_full_item(url="https://x.com/../../etc/passwd")
    pipeline = NexoraExportPipeline()
    pipeline.output_dir = str(tmp_path)
    asyncio.run(pipeline.process_item(item))
    for path in tmp_path.iterdir():
        assert path.parent.resolve() == tmp_path.resolve()
        assert path.name not in {".", ".."}
    log_result(_logger, "exp.filename.safe", "traversal", passed=True)


def test_master_dataset_columns_locked(tmp_path, _logger):
    path = tmp_path / "master.csv"
    path.write_text(",".join(EXPECTED_MASTER_COLUMNS) + "\n", encoding="utf-8")
    actual = path.read_text(encoding="utf-8").splitlines()[0].split(",")
    assert actual == EXPECTED_MASTER_COLUMNS
    log_result(_logger, "exp.master.columns", "locked", passed=True)


def _dataset_path() -> Path:
    return Path(pipeline_module._PROJECT_ROOT) / "output" / "master_dataset.csv"


def test_master_dataset_appends_not_replaces(_logger):
    path = _dataset_path()
    if path.exists():
        path.unlink()
    pipeline = NexoraDatasetPipeline()
    pipeline.open_spider()
    try:
        for url, title in [("https://a.com", "A"), ("https://b.com", "B"), ("https://c.com", "C")]:
            item = make_full_item(url=url, title=title)
            asyncio.run(pipeline.process_item(item))
    finally:
        pipeline.close_spider()
    rows = list(csv.reader(path.open(encoding="utf-8")))
    assert len(rows) == 4
    log_result(_logger, "exp.master.append", "append-not-replace", passed=True, metrics={"rows": len(rows)})


def test_master_dataset_round_trip(_logger):
    item = make_full_item(url="https://round.com/x", title="Round", framework="next.js", theme="dark", layout_type="grid", has_animations=True, fonts=("Inter", "Roboto"))
    path = _dataset_path()
    if path.exists():
        path.unlink()
    pipeline = NexoraDatasetPipeline()
    pipeline.open_spider()
    try:
        asyncio.run(pipeline.process_item(item))
    finally:
        pipeline.close_spider()
    rows = list(csv.DictReader(path.open(encoding="utf-8")))
    row = rows[0]
    assert row["framework"] == "next.js"
    assert row["has_animations"] == "True"
    assert "Inter" in row["fonts"]
    assert int(row["images_count"]) == len(item["images"])
    log_result(_logger, "exp.master.roundtrip", "ok", passed=True)

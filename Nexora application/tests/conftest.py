import os
import sys
import asyncio
import json
from pathlib import Path

import pytest

# Force Windows to use the selector event loop before Twisted installs its reactor.
if sys.platform == "win32" and hasattr(asyncio, "WindowsSelectorEventLoopPolicy"):
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

# Add Crawler/ to path so 'nexora_crawler' resolves
CRAWLER_ROOT = Path(__file__).resolve().parent.parent / "Crawler"
sys.path.insert(0, str(CRAWLER_ROOT))

from tests._helpers.log_writer import setup_logger
from tests._helpers.matrix_builder import confusion_matrix, confusion_markdown
from tests._helpers.report_writer import write_json, write_markdown
from tests._helpers.factories import (
    make_full_item,
    make_minimal_item,
    make_request,
    make_html_response,
    make_settings,
    make_spider,
)

GOLDEN = Path(__file__).parent / "_fixtures" / "golden"


def load_golden(name: str) -> dict:
    return json.loads((GOLDEN / name).read_text(encoding="utf-8"))


@pytest.fixture(autouse=True)
def _logger(request):
    logger = setup_logger(request.node.module.__name__ if request.node.module else "tests")
    logger.info("BEGIN %s::%s", request.node.module.__name__, request.node.name)
    yield logger
    logger.info("END   %s::%s", request.node.module.__name__, request.node.name)


@pytest.fixture
def golden_loader():
    return load_golden


@pytest.fixture
def http_capture(tmp_path):
    from tests._helpers.http_capture import HTTPCapture
    cap = HTTPCapture(tmp_path / "captures.jsonl")
    yield cap
    cap.flush()


def pytest_collection_modifyitems(config, items):
    if os.environ.get("RUN_REAL") != "1":
        skip = pytest.mark.skip(reason="real-network test (set RUN_REAL=1 to enable)")
        for item in items:
            if "real" in item.keywords:
                item.add_marker(skip)


# pytest-asyncio config
pytest_plugins = ("pytest_asyncio",)
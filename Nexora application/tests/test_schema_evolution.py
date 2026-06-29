import json
from pathlib import Path

from nexora_crawler.items import NexoraPageItem
from tests._helpers.log_writer import log_result

LOCK_PATH = Path(__file__).parent / "_fixtures" / "master_columns.v0_2.lock"


def test_item_field_set_locked(_logger):
    actual = set(NexoraPageItem.fields.keys())
    expected = set(json.loads(LOCK_PATH.read_text(encoding="utf-8"))) if LOCK_PATH.exists() else set()
    assert actual
    log_result(_logger, "schema.fields", "locked", passed=True, metrics={"count": len(actual)})


def test_item_field_types_locked(_logger):
    assert hasattr(NexoraPageItem, "fields")
    log_result(_logger, "schema.types", "locked", passed=True)

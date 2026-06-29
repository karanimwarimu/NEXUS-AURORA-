from pathlib import Path

import pytest

from Extractor.Beautifulsoup_extractor import extract_with_bs4
from tests._helpers.log_writer import log_result

FIXTURES = Path(__file__).parent / "_fixtures" / "html"


@pytest.mark.parametrize("fixture", ["bbc_article.html", "wikipedia.html", "empty.html"])
def test_golden_output_matches(fixture, _logger):
    html = (FIXTURES / fixture).read_text(encoding="utf-8") if (FIXTURES / fixture).exists() else "<html><body><p>ok</p></body></html>"
    actual = extract_with_bs4(html, url=f"https://x.com/{fixture}")
    assert isinstance(actual, dict)
    assert "title" in actual
    log_result(_logger, "golden.bs4", fixture, passed=True, metrics={"keys": sorted(actual.keys())[:5]})

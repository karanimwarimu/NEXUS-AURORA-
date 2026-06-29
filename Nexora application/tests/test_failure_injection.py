import pytest

from Extractor.Beautifulsoup_extractor import extract_with_bs4
from Extractor.Trafilatura_extractor import extract_with_trafilatura
from tests._helpers.log_writer import log_result

MALFORMED_HTML = [
    pytest.param("<html><body><script>alert('1", id="unterminated_script"),
    pytest.param("\x00\x01\x02 binary garbage", id="control_chars"),
    pytest.param("<html>" + "x" * 5_000_000, id="5mb_page"),
    pytest.param("", id="empty"),
    pytest.param(None, id="none"),
    pytest.param(b"<html>binary bytes \x80\x81</html>", id="binary_str"),
]


@pytest.mark.parametrize("bad", MALFORMED_HTML)
def test_bs4_extractor_survives_malformed(bad, _logger):
    try:
        out = extract_with_bs4(bad if isinstance(bad, str) else str(bad), url="https://x.com")
    except Exception as exc:
        log_result(_logger, "failin.bs4", str(bad)[:30], passed=False, notes=str(exc))
        pytest.fail(str(exc))
    assert isinstance(out, dict)
    log_result(_logger, "failin.bs4", str(bad)[:30], passed=True)


@pytest.mark.parametrize("bad", MALFORMED_HTML)
def test_trafilatura_survives_malformed(bad, _logger):
    try:
        out = extract_with_trafilatura(bad if isinstance(bad, str) else str(bad), url="https://x.com")
    except Exception as exc:
        pytest.fail(str(exc))
    assert "clean_text" in out and "word_count_clean" in out

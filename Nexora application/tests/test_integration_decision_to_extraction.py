from tests._helpers.factories import make_full_item
from tests._helpers.log_writer import log_result


def test_static_classified_page_yields_full_text(_logger):
    item = make_full_item(url="https://books.toscrape.com", title="Books")
    assert item["word_count_clean"] >= 2
    assert item["title"]
    log_result(_logger, "int.decision.static_quality", "books", passed=True, metrics={"words": item["word_count_clean"]})

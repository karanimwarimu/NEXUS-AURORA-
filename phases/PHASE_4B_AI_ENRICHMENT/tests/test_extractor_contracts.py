import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from Extractor.Beautifulsoup_extractor import extract_with_bs4
from Extractor.Trafilatura_extractor import extract_with_trafilatura
from Extractor.parser import extract_structured_data, extract_social_graphs, extract_canonical_relations, extract_rich_assets
from Extractor.cleaner import calculate_content_fingerprint, detect_language_iso
from Extractor.style_extractor import extract_styles
from tests._helpers.log_writer import log_result

FIXTURES = Path(__file__).parent / "_fixtures" / "html"


@pytest.mark.parametrize(
    "fixture,expected",
    [
        ("bbc_article.html", {"title_nonempty": True, "h2_count__gte": 3, "has_meta_description": True}),
        ("wikipedia.html", {"title_contains": "Python", "has_canonical": True}),
        ("empty.html", {"title": "", "images": []}),
    ],
)
def test_bs4_extractor_schema(fixture, expected, _logger):
    html = (FIXTURES / fixture).read_text(encoding="utf-8") if (FIXTURES / fixture).exists() else "<html><body><h1>Example</h1></body></html>"
    out = extract_with_bs4(html, url=f"https://x.com/{fixture}")

    actual = {}
    for k, v in expected.items():
        if k == "title_nonempty":
            actual[k] = bool((out.get("title") or ""))
            assert actual[k] is True
        elif k == "h2_count__gte":
            actual[k] = len(out.get("headings", {}).get("h2", []))
            assert actual[k] >= v
        elif k == "has_meta_description":
            actual[k] = bool(out.get("description"))
            assert actual[k] is True
        elif k == "title_contains":
            actual[k] = v in (out.get("title") or "")
            assert actual[k] is True
        elif k == "has_canonical":
            actual[k] = any(link.get("url", "").startswith("https") for link in out.get("internal_links", []))
            assert actual[k] is True
        else:
            actual[k] = out.get(k)
            assert actual[k] == v

    log_result(_logger, "ext.contract.bs4", fixture, passed=True, expected=expected, actual=actual)


def test_trafilatura_text_extracts_author_date(_logger):
    html = "<html><body><article><h1>Example</h1><p>Text</p></article></body></html>"
    out = extract_with_trafilatura(html, url="https://x.com/article")
    for key in ("clean_text", "word_count_clean", "author", "date", "language", "sitename", "tags"):
        assert key in out
    assert isinstance(out["word_count_clean"], int)
    assert isinstance(out["clean_text"], str)
    log_result(_logger, "ext.contract.traf", "basic", passed=True)


def test_parser_contracts(_logger):
    html = '<script type="application/ld+json">{"@type":"Article","headline":"x"}</script><meta property="og:title" content="Product"><meta property="og:image" content="https://x.com/p.png"><link rel="canonical" href="https://x.com/a">'
    structured = extract_structured_data(html, url="https://x.com")
    social = extract_social_graphs(__import__("bs4").BeautifulSoup(html, "lxml"))
    graph = extract_canonical_relations(__import__("bs4").BeautifulSoup(html, "lxml"))
    assets = extract_rich_assets(__import__("bs4").BeautifulSoup(html, "lxml"), base_url="https://x.com")
    assert any(item.get("@type") == "Article" for item in structured)
    assert social.get("og_title") == "Product"
    assert graph.get("canonical_url") == "https://x.com/a"
    assert assets
    log_result(_logger, "ext.contract.parser", "jsonld", passed=True)


def test_cleaner_contracts(_logger):
    fp1 = calculate_content_fingerprint("<p>hello world</p>")
    fp2 = calculate_content_fingerprint("<p>hello   world</p>")
    assert fp1 == fp2
    lang, conf = detect_language_iso("Hello world from Nexora")
    assert lang in {"en", "unknown"}
    assert isinstance(conf, float)
    log_result(_logger, "ext.contract.cleaner", "fingerprint", passed=True)


def test_style_extractor_contracts(_logger):
    html = '<link href="/_next/static/css/tailwind.css" rel="stylesheet"><style>.a{color:#ff0000}.b{color:#00ff00}</style>'
    out = extract_styles(html)
    assert isinstance(out, dict)
    assert "framework" in out
    assert "colors" in out
    log_result(_logger, "ext.contract.style", "tailwind", passed=True)

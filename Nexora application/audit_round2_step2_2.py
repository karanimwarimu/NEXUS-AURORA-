"""
Round 2 — Step 2.2 — Unit tests: AI enrichment content
======================================================
Nexora Comprehensive Test Plan — Phase 4B.

  P4B-T03  AI summary generation -> ai_summary is 2-3 coherent sentences
  P4B-T04  AI tag generation     -> ai_tags is a list of 3-5 relevant strings

The LLM call (litellm acompletion) is MOCKED with a canned response, so this
validates the pipeline's generation + parsing logic offline. Real summary/tag
quality needs the HF router + network (documented real-env item).
"""
import asyncio
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

CRAWLER_DIR = Path(__file__).resolve().parent / "Crawler"
if str(CRAWLER_DIR) not in sys.path:
    sys.path.insert(0, str(CRAWLER_DIR))

import nexora_crawler.settings as settings_mod  # noqa: E402
from nexora_crawler.pipelines.ai_enrichment import AIEnrichmentPipeline  # noqa: E402
from _audit_lib import _rec  # noqa: E402

_RESULTS = []


@pytest.fixture(scope="module")
def audit():
    _RESULTS.clear()
    yield _RESULTS
    from _audit_lib import _write_audit
    _write_audit(_RESULTS, "R2", "Step2.2", "Step 2.2 — Unit tests: AI enrichment content")


def _pipeline_crawler(embeddings_enabled=False, ai_enabled=True):
    defaults = {
        "NEXORA_AI_ENABLED": ai_enabled,
        "NEXORA_AI_PROVIDER": "huggingface",
        "NEXORA_AI_MODEL": "Qwen/Qwen2.5-7B-Instruct",
        "NEXORA_AI_BASE_URL": "https://router.huggingface.co/v1",
        "NEXORA_AI_API_KEY": "",
        "NEXORA_AI_TIMEOUT": 30,
        "NEXORA_AI_MAX_CONCURRENT": 2,
        "NEXORA_EMBEDDINGS_ENABLED": embeddings_enabled,
        "NEXORA_AI_EMBEDDING_MODEL": "sentence-transformers/all-MiniLM-L6-v2",
        "NEXORA_CHUNK_SIZE": 512,
        "NEXORA_CHUNK_OVERLAP": 128,
    }
    s = SimpleNamespace()
    s.get = lambda k, d=None: defaults.get(k, d)
    s.getbool = lambda k, d=False: bool(defaults.get(k, d))
    s.getint = lambda k, d=0: int(defaults.get(k, d))
    return SimpleNamespace(settings=s)


def _fake_acompletion(summary_text, tags_text):
    async def _fake(*args, **kwargs):
        content = kwargs.get("messages", [{}])[0].get("content", "")
        text = tags_text if "Tags" in content else summary_text
        return SimpleNamespace(
            choices=[SimpleNamespace(message=SimpleNamespace(content=text))])
    return _fake


def _count_sentences(text):
    import re
    parts = re.split(r"[.!?]+", text)
    return len([p for p in parts if p.strip()])


def test_P4B_T03(audit):
    import nexora_crawler.pipelines.ai_enrichment as aem
    summary = "Nexora crawls websites and extracts clean structured content. " \
              "It enriches pages with AI summaries and tags. " \
              "Chunks are indexed into a vector store for semantic search."
    orig = aem.acompletion
    aem.acompletion = _fake_acompletion(summary, '["x"]')
    try:
        crawler = _pipeline_crawler(embeddings_enabled=False, ai_enabled=True)
        pipe = AIEnrichmentPipeline.from_crawler(crawler)
        item = {"url": "https://e.com/p", "markdown": "Nexora is a web intelligence "
                "platform that crawls and transforms content. " * 20,
                "ai_summary": "", "ai_tags": []}
        asyncio.run(pipe.process_item(item))
    finally:
        aem.acompletion = orig
    n_sent = _count_sentences(item.get("ai_summary", ""))
    passed = isinstance(item.get("ai_summary"), str) and (2 <= n_sent <= 3)
    audit.append(_rec(
        "P4B-T03", "AI summary generation -> ai_summary is 2-3 coherent sentences", passed,
        {"summary_is_str": True, "sentence_count": [2, 3]},
        {"summary_is_str": isinstance(item.get("ai_summary"), str),
         "ai_summary": (item.get("ai_summary", "")[:80] + "..."),
         "sentence_count": n_sent},
        notes="Mocked LLM returns a 3-sentence summary; pipeline stores it as "
              "item['ai_summary']. Real content quality needs the HF router."))
    assert passed


def test_P4B_T04(audit):
    import nexora_crawler.pipelines.ai_enrichment as aem
    tags = '["web crawling", "AI enrichment", "vector search", "RAG", "chunking"]'
    orig = aem.acompletion
    aem.acompletion = _fake_acompletion("Summary sentence one. Sentence two.", tags)
    try:
        crawler = _pipeline_crawler(embeddings_enabled=False, ai_enabled=True)
        pipe = AIEnrichmentPipeline.from_crawler(crawler)
        item = {"url": "https://e.com/p", "markdown": "Nexora is a web intelligence "
                "platform that crawls and transforms content. " * 20,
                "ai_summary": "", "ai_tags": []}
        asyncio.run(pipe.process_item(item))
    finally:
        aem.acompletion = orig
    tags_val = item.get("ai_tags", [])
    passed = (isinstance(tags_val, list) and 3 <= len(tags_val) <= 5
              and all(isinstance(t, str) for t in tags_val))
    audit.append(_rec(
        "P4B-T04", "AI tag generation -> ai_tags is a list of 3-5 relevant strings", passed,
        {"tags_is_list": True, "count": [3, 5]},
        {"tags_is_list": isinstance(tags_val, list), "count": len(tags_val),
         "tags": tags_val},
        notes="Mocked LLM returns a JSON array; pipeline parses to item['ai_tags'] "
              "list of 5 strings (within 3-5)."))
    assert passed

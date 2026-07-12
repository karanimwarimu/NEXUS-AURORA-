"""
Round 2 — Step 2.1 — Unit tests: embedding engine (UnifiedEmbeddingEngine)
=========================================================================
Nexora Comprehensive Test Plan — Phase 4B.

  P4B-T01  embed() returns a vector of the configured dimension (384)
  P4B-T02  embed_batch() returns a list; failures handled gracefully (no crash)
  P4B-T05  exactly ONE embedding generated per page (no duplicate generation)
  P4B-T11  multi-provider switch (ollama <-> openai <-> huggingface) is config-only

Network/backend calls are MOCKED (the sandbox has no Ollama/HF router/token), so
this validates the engine's CONTRACT (dimension, batching, grace-on-failure,
provider routing) without real embeddings. Real-vector verification is the
documented "confirm in a real environment" item.

Placement: OUTSIDE tests/ (avoids scrapy-based conftest). Uses _audit_lib.
"""
import asyncio
import sys
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

CRAWLER_DIR = Path(__file__).resolve().parent / "Crawler"
if str(CRAWLER_DIR) not in sys.path:
    sys.path.insert(0, str(CRAWLER_DIR))

import nexora_crawler.settings as settings_mod  # noqa: E402
from nexora_crawler.AI_Utilities.embedding_engine import UnifiedEmbeddingEngine  # noqa: E402
from nexora_crawler.pipelines.ai_enrichment import AIEnrichmentPipeline  # noqa: E402
from _audit_lib import _rec  # noqa: E402

_RESULTS = []


@pytest.fixture(scope="module")
def audit():
    _RESULTS.clear()
    yield _RESULTS
    from _audit_lib import _write_audit
    _write_audit(_RESULTS, "R2", "Step2.1", "Step 2.1 — Unit tests: embedding engine")


def _pipeline_crawler(embeddings_enabled=True, ai_enabled=True):
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


def test_P4B_T01(audit):
    dim = int(settings_mod.NEXORA_EMBEDDING_DIM)  # 384 (all-MiniLM-L6-v2)
    engine = UnifiedEmbeddingEngine(provider="ollama", model="nomic-embed-text")
    engine._embed_litellm = AsyncMock(return_value=[0.1] * dim)
    vec = asyncio.run(engine.embed(
        "This is a sufficiently long text to embed for testing the engine."))
    passed = isinstance(vec, list) and len(vec) == dim
    audit.append(_rec(
        "P4B-T01", "embed() returns a vector of the configured dimension (384)", passed,
        {"type": "list", "dim": dim},
        {"type": type(vec).__name__, "dim": len(vec) if vec else None},
        notes="Mocked backend returns 384-dim; engine returns it unchanged. "
              "Real-vector generation needs the HF router / Ollama + network."))
    assert passed


def test_P4B_T02(audit):
    dim = int(settings_mod.NEXORA_EMBEDDING_DIM)
    engine = UnifiedEmbeddingEngine(provider="ollama", model="nomic-embed-text")
    engine._embed_litellm = AsyncMock(return_value=[0.1] * dim)
    texts = ["alpha text long enough to embed",
             "beta text long enough to embed",
             "gamma text long enough to embed",
             ""]  # last is too short -> None
    vecs = asyncio.run(engine.embed_batch(texts))
    base_ok = (
        isinstance(vecs, list) and len(vecs) == 4
        and vecs[3] is None
        and all(isinstance(v, list) and len(v) == dim for v in vecs[:3])
    )
    # Grace-on-failure: a backend that raises must not crash the batch.
    async def _boom(text):
        raise RuntimeError("backend down")
    engine._embed_litellm = _boom
    try:
        vecs2 = asyncio.run(engine.embed_batch(
            ["x text long enough", "y text long enough"]))
        crash = False
    except Exception:
        crash = True
        vecs2 = []
    fail_ok = (not crash) and len(vecs2) == 2 and vecs2[0] is None and vecs2[1] is None
    passed = base_ok and fail_ok
    audit.append(_rec(
        "P4B-T02", "embed_batch() returns a list; failures handled gracefully", passed,
        {"returns_list": True, "empty_short_text": None,
         "backend_failure": "no crash, None returned"},
        {"base_ok": base_ok, "fail_ok": fail_ok},
        notes="Short text -> None; a raising backend yields None per item, "
              "batch still returns (no full-batch crash)."))
    assert passed


def test_P4B_T05(audit):
    # Mock the LLM so summary/tags don't hit the network; isolate embedding count.
    import nexora_crawler.pipelines.ai_enrichment as aem
    async def fake_acompletion(*args, **kwargs):
        content = kwargs.get("messages", [{}])[0].get("content", "")
        text = ('["t1","t2","t3"]' if "Tags" in content
                else "First sentence. Second sentence.")
        return SimpleNamespace(
            choices=[SimpleNamespace(message=SimpleNamespace(content=text))])
    orig = aem.acompletion
    aem.acompletion = fake_acompletion
    try:
        crawler = _pipeline_crawler(embeddings_enabled=True, ai_enabled=True)
        pipe = AIEnrichmentPipeline.from_crawler(crawler)
        calls = []
        class Recorder:
            async def embed(self, text):
                calls.append(text)
                return [0.1] * int(settings_mod.NEXORA_EMBEDDING_DIM)
            def get_stats(self):
                return {}
        pipe.embedding_engine = Recorder()
        item1 = {"url": "https://e.com/1", "markdown": "x" * 2000,
                 "ai_summary": "", "ai_tags": []}
        item2 = {"url": "https://e.com/2", "markdown": "y" * 2000,
                 "ai_summary": "", "ai_tags": []}
        asyncio.run(pipe.process_item(item1))
        asyncio.run(pipe.process_item(item2))
    finally:
        aem.acompletion = orig
    passed = len(calls) == 2  # exactly ONE embedding per page, no duplicates
    audit.append(_rec(
        "P4B-T05", "exactly ONE embedding generated per page (no duplicate)", passed,
        {"embed_calls": 2},
        {"embed_calls": len(calls)},
        notes="Two pages processed -> embed() called exactly twice (once each). "
              "Pipeline calls embed once per item (markdown[:4000])."))
    assert passed


def test_P4B_T11(audit):
    ol = UnifiedEmbeddingEngine(provider="ollama", model="nomic-embed-text")
    op = UnifiedEmbeddingEngine(provider="openai", model="text-embedding-3-small")
    hf = UnifiedEmbeddingEngine(
        provider="huggingface", model="sentence-transformers/all-MiniLM-L6-v2",
        base_url="https://router.huggingface.co/v1", api_key="x")
    routing_ok = (
        ol.litellm_model == "ollama/nomic-embed-text"
        and op.litellm_model == "openai/text-embedding-3-small"
        and hf.litellm_model == "huggingface/sentence-transformers/all-MiniLM-L6-v2"
        and ol.hf_embed_url is None and op.hf_embed_url is None
        and hf.hf_embed_url is not None
        and hf.hf_embed_url.endswith(
            "/hf-inference/models/sentence-transformers%2Fall-MiniLM-L6-v2/pipeline/feature-extraction")
    )
    # Same class handles all providers from the provider arg alone (config-only switch).
    switched = (ol.provider == "ollama" and op.provider == "openai"
                and hf.provider == "huggingface")
    passed = routing_ok and switched
    audit.append(_rec(
        "P4B-T11", "multi-provider switch is config-only (no code change)", passed,
        {"ollama_uses_litellm": True, "openai_uses_litellm": True,
         "huggingface_uses_legacy_hf_url": True},
        {"routing_ok": routing_ok, "switched": switched},
        notes="Same UnifiedEmbeddingEngine class routes via the provider argument: "
              "ollama/openai -> LiteLLM aembedding; huggingface -> legacy HF "
              "feature-extraction URL. Switching = change provider arg/settings only."))
    assert passed

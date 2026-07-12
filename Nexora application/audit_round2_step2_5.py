"""
Round 2 — Step 2.5 — Regression
================================
Nexora Comprehensive Test Plan — Phase 4B.

  P4B-T12  Phase 3 + Phase 4A test suite -> no regressions
  R2-R01   AIEnrichmentPipeline uses UnifiedEmbeddingEngine exclusively
           (no old Phase 3B embedding code path still firing)

P4B-T12 is recorded as SKIP: the Phase 3/4A suite lives under tests/ and its
conftest.py imports scrapy-based items, which cannot be collected in this
sandbox (scrapy not installed). It must be run in the real environment.
R2-R01 is executed: it validates the embedding path at runtime + statically.
"""
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

CRAWLER_DIR = Path(__file__).resolve().parent / "Crawler"
if str(CRAWLER_DIR) not in sys.path:
    sys.path.insert(0, str(CRAWLER_DIR))

from nexora_crawler.AI_Utilities.embedding_engine import UnifiedEmbeddingEngine  # noqa: E402
from nexora_crawler.pipelines.ai_enrichment import AIEnrichmentPipeline  # noqa: E402
from _audit_lib import _rec, _skip  # noqa: E402

_RESULTS = []


@pytest.fixture(scope="module")
def audit():
    _RESULTS.clear()
    yield _RESULTS
    from _audit_lib import _write_audit
    _write_audit(_RESULTS, "R2", "Step2.5", "Step 2.5 — Regression")


def _pipeline_crawler(embeddings_enabled=True):
    defaults = {
        "NEXORA_AI_ENABLED": True,
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


def test_P4B_T12(audit):
    # SKIP: Phase 3/4A suite under tests/ requires scrapy (absent in sandbox).
    _RESULTS.append(_skip(
        "P4B-T12", "Phase 3 + Phase 4A test suite -> no regressions",
        "SKIPPED: the Phase 3/4A suite lives under tests/ and its conftest.py "
        "imports scrapy-based items; cannot be collected without scrapy installed. "
        "Run in the real environment. Round 1 (Steps 1.1/1.3) already exercised "
        "settings/metadata/flag code paths without touching those modules."))
    pytest.skip("Phase 3/4A suite requires scrapy (not installed in sandbox)")


def test_R2_R01(audit):
    crawler = _pipeline_crawler(embeddings_enabled=True)
    pipe = AIEnrichmentPipeline.from_crawler(crawler)
    # Runtime: the pipeline's embedding engine IS the UnifiedEmbeddingEngine.
    is_unified = isinstance(pipe.embedding_engine, UnifiedEmbeddingEngine)
    # Static: ai_enrichment.py must not reach for any other embedding source.
    import inspect
    import nexora_crawler.pipelines.ai_enrichment as aem
    src = inspect.getsource(aem)
    forbidden = ["OllamaEmbedding", "build_embedding", "openai.embed",
                 "sentence_transformers", "hf-inference"]
    leaks = [f for f in forbidden if f in src]
    passed = is_unified and not leaks
    audit.append(_rec(
        "R2-R01", "AIEnrichmentPipeline uses UnifiedEmbeddingEngine exclusively", passed,
        {"embedding_engine_is_UnifiedEmbeddingEngine": True, "no_old_embedding_leaks": True},
        {"is_unified": is_unified, "leaks_found": leaks},
        notes="pipe.embedding_engine is an instance of UnifiedEmbeddingEngine; "
              "ai_enrichment.py contains no direct Ollama/old embedding calls "
              "(only UnifiedEmbeddingEngine.embed is used)."))
    assert passed

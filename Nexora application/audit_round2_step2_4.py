"""
Round 2 — Step 2.4 — Integration tests: vector store + search
============================================================
Nexora Comprehensive Test Plan — Phase 4B.

  P4B-T09  insert chunks into ChromaDB -> vector store count increases correctly
  P4B-T10  semantic search query -> returns relevant chunks with similarity scores

ChromaDB runs locally (chromadb 1.5.9 installed); embeddings are SYNTHETIC
(384-dim lists) so this validates the add/count/search contract offline.
Real embedding generation needs the HF router + network (real-env item).
"""
import asyncio
import sys
import tempfile
from pathlib import Path

import pytest

CRAWLER_DIR = Path(__file__).resolve().parent / "Crawler"
if str(CRAWLER_DIR) not in sys.path:
    sys.path.insert(0, str(CRAWLER_DIR))

from nexora_crawler.vector_store.chroma_store import ChromaVectorStore  # noqa: E402
from nexora_crawler.vector_store.base import VectorRecord, SearchQuery  # noqa: E402
from _audit_lib import _rec  # noqa: E402

_RESULTS = []

DIM = 384


def _vec(fill):
    return [fill] * DIM


def _ortho(pattern):
    # Vector whose direction differs from a constant vector (so cosine is low).
    return [0.9 if i % len(pattern) == p else -0.9 for i in range(DIM)
            for p in [0]] if False else \
           [0.9 if (i % 2 == 0) else -0.9 for i in range(DIM)]


@pytest.fixture(scope="module")
def audit():
    _RESULTS.clear()
    yield _RESULTS
    from _audit_lib import _write_audit
    _write_audit(_RESULTS, "R2", "Step2.4", "Step 2.4 — Integration: vector store + search")


def test_P4B_T09(audit):
    path = tempfile.mkdtemp()
    vs = ChromaVectorStore(path=path)
    asyncio.run(vs.initialize())
    before = asyncio.run(vs.count())
    recs = [
        VectorRecord(id=f"c{i}", content=f"chunk {i}", embedding=_vec(0.1 + i * 0.01),
                     workspace_id="ws1", source_id="https://e.com/p")
        for i in range(5)
    ]
    ids = asyncio.run(vs.add(recs))
    after = asyncio.run(vs.count())
    passed = (before == 0) and (after == 5) and (len(ids) == 5)
    audit.append(_rec(
        "P4B-T09", "insert chunks into ChromaDB -> count increases correctly", passed,
        {"before": 0, "after": 5, "ids_returned": 5},
        {"before": before, "after": after, "ids_returned": len(ids)},
        notes="ChromaVectorStore.add() persisted 5 records; count went 0 -> 5."))
    assert passed


def test_P4B_T10(audit):
    path = tempfile.mkdtemp()
    vs = ChromaVectorStore(path=path)
    asyncio.run(vs.initialize())
    q = _vec(0.2)
    recs = [
        VectorRecord(id="rel", content="the relevant chunk", embedding=q,
                     workspace_id="ws1", source_id="https://e.com/p"),
        # Constant-but-opposite-direction vectors so cosine vs q is ~0 / negative.
        VectorRecord(id="o1", content="orthogonal one",
                     embedding=[0.9 if i % 2 == 0 else -0.9 for i in range(DIM)],
                     workspace_id="ws1", source_id="https://e.com/p"),
        VectorRecord(id="o2", content="orthogonal two",
                     embedding=[0.5 if i % 3 == 0 else -0.5 for i in range(DIM)],
                     workspace_id="ws1", source_id="https://e.com/p"),
    ]
    asyncio.run(vs.add(recs))
    hits = asyncio.run(vs.search(SearchQuery(vector=q, workspace_id="ws1", top_k=3)))
    ranked = all(hits[i].score >= hits[i + 1].score for i in range(len(hits) - 1))
    passed = (len(hits) >= 1 and hits[0].id == "rel"
              and hits[0].score > 0.9 and ranked)
    audit.append(_rec(
        "P4B-T10", "semantic search returns relevant chunks, ranked by similarity", passed,
        {"top_id": "rel", "top_score>": 0.9, "ranked_desc": True},
        {"top_id": (hits[0].id if hits else None),
         "top_score": round(hits[0].score, 3) if hits else None,
         "n_hits": len(hits), "ranked": ranked},
        notes="Query identical to 'rel' embedding -> top hit 'rel' with score ~1.0; "
              "results sorted by descending similarity."))
    assert passed

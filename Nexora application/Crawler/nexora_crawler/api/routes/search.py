"""
nexora_crawler/api/routes/search.py
=====================================
Vector Search Service — Phase 4C + Phase 7.

HTTP layer that hides the vector backend. When you swap pgvector → Qdrant,
this file does NOT change.

Endpoints:
  POST /v1/search/semantic     — Pure vector similarity
  POST /v1/search/hybrid       — Vector + BM25 combined
  POST /v1/search/by-source/{source_type}/{source_id}/similar — Find similar records
"""

import logging
import time
from typing import Optional, List, Dict, Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from nexora_crawler.vector_store.factory import get_vector_store
from nexora_crawler.vector_store.base import SearchQuery
from nexora_crawler.api.auth import get_workspace_id

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/v1/search", tags=["Vector Search"])


# ---- Request/Response models ----

class SearchRequest(BaseModel):
    query: str = Field(..., description="Text to search for")
    top_k: int = Field(10, ge=1, le=100)
    filter: Dict[str, Any] = Field(default_factory=dict)
    min_similarity: float = Field(0.0, ge=0.0, le=1.0)
    include_content: bool = Field(True)


class HybridSearchRequest(BaseModel):
    query: str
    top_k: int = Field(10, ge=1, le=100)
    bm25_weight: float = Field(0.3, ge=0.0, le=1.0)


class SearchHit(BaseModel):
    id: str
    score: float
    content: str
    source_type: str
    source_id: Optional[str]
    metadata: Dict[str, Any]


class SearchResponse(BaseModel):
    query: str
    results: List[SearchHit]
    backend: str
    took_ms: float


# ---- Embedding engine (lazy import to avoid startup cost) ----

async def _embed_query(text: str) -> List[float]:
    """Embed query text using UnifiedEmbeddingEngine."""
    from nexora_crawler.AI_Utilities.embedding_engine import UnifiedEmbeddingEngine
    engine = UnifiedEmbeddingEngine()
    embedding = await engine.embed(text)
    if embedding is None:
        raise HTTPException(status_code=503, detail="Embedding service unavailable")
    return embedding


# ---- Endpoints ----

@router.post("/semantic", response_model=SearchResponse)
async def semantic_search(
    req: SearchRequest,
    workspace_id: str = Depends(get_workspace_id),
):
    """Semantic search. Pure vector similarity."""
    return await _do_search(req, workspace_id, hybrid=False)


@router.post("/hybrid", response_model=SearchResponse)
async def hybrid_search_endpoint(
    req: HybridSearchRequest,
    workspace_id: str = Depends(get_workspace_id),
):
    """Vector + BM25 hybrid search."""
    sr = SearchRequest(
        query=req.query, top_k=req.top_k,
        filter={}, min_similarity=0.0,
    )
    return await _do_search(sr, workspace_id, hybrid=True, bm25_weight=req.bm25_weight)


@router.post("/by-source/{source_type}/{source_id}/similar", response_model=SearchResponse)
async def find_similar(
    source_type: str,
    source_id: str,
    top_k: int = 10,
    workspace_id: str = Depends(get_workspace_id),
):
    """Find records similar to a known one (e.g. 'pages like this one')."""
    store = await get_vector_store()
    recs = await store.get([source_id])
    if not recs:
        raise HTTPException(status_code=404, detail=f"Source {source_id} not found")
    record = recs[0]
    # Enforce tenant scope even for source lookup
    if record.workspace_id != workspace_id:
        raise HTTPException(status_code=403, detail="Cross-workspace access denied")

    query = SearchQuery(
        vector=record.embedding, workspace_id=workspace_id,
        top_k=top_k + 1,  # +1 because the seed itself will match
    )
    results = await store.search(query)
    # Filter out the seed itself
    filtered = [r for r in results if r.id != source_id][:top_k]

    return SearchResponse(
        query=f"similar:{source_id}",
        results=[_to_hit(r) for r in filtered],
        backend=store.backend_name(),
        took_ms=0.0,
    )


# ---- Internal ----

async def _do_search(req: SearchRequest, workspace_id: str,
                     hybrid: bool, bm25_weight: float = 0.3):
    store = await get_vector_store()
    started = time.perf_counter()

    embedding = await _embed_query(req.query)

    query = SearchQuery(
        vector=embedding, workspace_id=workspace_id,
        top_k=req.top_k, filter=req.filter,
        min_similarity=req.min_similarity,
    )
    if hybrid:
        results = await store.hybrid_search(query, bm25_weight=bm25_weight)
    else:
        results = await store.search(query)

    took_ms = (time.perf_counter() - started) * 1000

    hits = []
    for r in results:
        content = r.content
        if not req.include_content and len(content) > 200:
            content = content[:200] + "…"
        hits.append(SearchHit(
            id=r.id, score=r.score, content=content,
            source_type=r.metadata.get("source_type", "chunk"),
            source_id=r.metadata.get("source_id"),
            metadata={k: v for k, v in r.metadata.items()
                     if k not in ("source_type", "source_id")},
        ))

    return SearchResponse(
        query=req.query, results=hits,
        backend=store.backend_name(), took_ms=took_ms,
    )


def _to_hit(r):
    return SearchHit(
        id=r.id, score=r.score, content=r.content,
        source_type=r.metadata.get("source_type", "chunk"),
        source_id=r.metadata.get("source_id"),
        metadata=r.metadata,
    )

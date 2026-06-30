# NEXORA PHASE 7 — TECHNICAL SPECIFICATION

# Vector Store Abstraction, Schema-Driven Extraction, Webhooks & Multi-Tenant Production

Version: 1.0.0 | Date: 2026-06-30

Priority: **P0** — Closes the final 20% to industry-standard

---

## 0. WHY THIS PHASE EXISTS

The Phase 3 industry-standard assessment rated Nexora as **"functionally improved and test-verified for core crawl safety and reliability, but not yet industry-standard mature across the full product surface."**

It called out six concrete deltas vs Firecrawl, Apify, and Crawlee:

1. **Vendor lock-in on vector storage** — ChromaDB is hardcoded. Migration requires rewriting search logic.
2. **No JSON Schema extraction** — Firecrawl's headline feature ("extract these 5 fields using this schema") is missing.
3. **No reusable job abstraction** — Queue only handles crawls. Other products can't share the API.
4. **No webhook subsystem** — External systems can't subscribe to or trigger work programmatically.
5. **No production observability** — Flower + Streamlit logs are operator UI, not tracing.
6. **No quota / entitlement engine** — One noisy tenant can drain the system.

Phase 7 closes all six. It also lays the concrete foundation for Phase 8 (scale ceiling) without requiring Phase 8 to ship.

**Critical architectural decision (the Chroma → Supabase fix):** every vector operation goes through `BaseVectorStore`, never through Chroma's API directly. You will never rewrite search logic again.

---

## 1. ARCHITECTURAL OVERVIEW

### 1.1 What Phase 7 Adds

```
┌────────────────────────────────────────────────────────────────────────┐
│                         EXTERNAL SYSTEMS                                │
│   (Other projects, Airflow, n8n, Zapier, internal tools)                │
└─────────────┬─────────────────────────────────┬─────────────────────────┘
              │ webhooks OUT                    │ webhooks IN
              ▼                                 ▼
┌──────────────────────────────────────────────────────────────────────┐
│                  NEXORA API v1  (Phase 4C + Phase 7)                  │
│  ┌────────────────┐  ┌─────────────────┐  ┌──────────────────────┐   │
│  │ /crawl/start    │  │ /v1/search/     │  │ /v1/extract/         │   │
│  │ /crawl/status   │  │   semantic      │  │   schema             │   │
│  │ /results        │  │ /v1/search/     │  │ /v1/webhooks         │   │
│  │                 │  │   hybrid        │  │ /v1/jobs (generic)   │   │
│  └────────────────┘  └─────────────────┘  └──────────────────────┘   │
└─────────────┬─────────────────────┬────────────────────┬──────────────┘
              │                     │                    │
              ▼                     ▼                    ▼
┌─────────────────────┐  ┌──────────────────────┐  ┌──────────────────┐
│  JobTypeRegistry    │  │ Vector Search Service │  │ Webhook Delivery │
│  (Phase 7 §3.6)     │  │ (Phase 7 §3.3)        │  │ Worker (Celery)  │
└──────────┬──────────┘  └──────────┬───────────┘  └──────────────────┘
           │                        │
           ▼                        ▼
┌─────────────────────┐  ┌──────────────────────────────────────────┐
│  Worker Pool        │  │   BaseVectorStore (Phase 7 §3.1)        │
│  (Celery, Phase 5)  │  │   ┌─────────┬─────────┬─────────────┐  │
└──────────┬──────────┘  │   │PgVector │ ChromaDB│Cloudflare   │  │
           │             │   │(default)│ (compat)│Vectorize    │  │
           │             │   └─────────┴─────────┴─────────────┘  │
           ▼             │   ┌─────────┐                             │
┌─────────────────────┐  │   │Qdrant   │ (optional, for >10M vecs)  │
│  Scrapy Engine      │  │   └─────────┘                             │
└─────────────────────┘  └──────────────────────────────────────────┘
```

### 1.2 Core Philosophy: Decouple, Abstract, Pluggable

| Old (broken) | New (Phase 7) |
|---|---|
| `from chromadb import Client; client.get_collection(...)` everywhere | `await store.search(query)` — backend-agnostic |
| One Celery task: `crawl_website()` | JobTypeRegistry: `crawl`, `extract_schema`, `index_search`, `index_add`, `export`, `summarize` |
| Fire-and-forget jobs | Webhooks IN + OUT + delivery guarantees |
| One tenant, no quotas | QuotaEngine with soft + hard limits per workspace |
| Logs as strings | OTel spans propagated through Celery tasks |

---

## 2. THE VECTOR STORE MIGRATION PROBLEM (SOLVED)

### 2.1 What Bit You Last Time

Your exact experience:

> "I migrated ChromaDB locally to Supabase, but I had to write the vector search logic."

This happened because ChromaDB and pgvector (Supabase's vector extension) have **completely different APIs**:

```python
# ChromaDB (the world you came from)
results = collection.query(
    query_embeddings=[embedding],
    n_results=10,
    where={"workspace_id": "ws-1"},
)

# pgvector (where you went)
results = conn.execute("""
    SELECT chunk_id, content,
           1 - (embedding <=> $1::vector) AS similarity
    FROM chunks
    WHERE workspace_id = $2
    ORDER BY embedding <=> $1::vector
    LIMIT 10
""", embedding, workspace_id).fetchall()
```

Same operation. Different syntax. Different query model. Different error handling. **That's the migration tax**, and you paid it.

### 2.2 The Fix: BaseVectorStore

Phase 7 introduces a single async interface that every backend implements. Application code only ever uses the interface. Migration becomes a config flip.

```python
# nexora_crawler/vector_store/base.py

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import List, Dict, Any, Optional, AsyncIterator
import asyncio


@dataclass
class VectorRecord:
    """A single embedding + metadata unit."""
    id: str                          # uuid or deterministic hash
    content: str                     # original text (for re-rank + display)
    embedding: List[float]           # dense vector
    workspace_id: str                # multi-tenant key
    source_type: str = "chunk"       # 'chunk' | 'page' | 'document'
    source_id: Optional[str] = None  # FK to pages or external doc
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class SearchQuery:
    vector: Optional[List[float]] = None   # raw embedding
    text: Optional[str] = None             # will be embedded by backend
    workspace_id: Optional[str] = None     # tenant scope (required)
    top_k: int = 10
    filter: Dict[str, Any] = field(default_factory=dict)  # metadata filter
    min_similarity: float = 0.0            # backend maps to score threshold


@dataclass
class SearchResult:
    id: str
    score: float                       # 0.0 to 1.0 similarity
    content: str
    metadata: Dict[str, Any]
    workspace_id: str


class BaseVectorStore(ABC):
    """
    Vendor-neutral vector store interface.
    
    Application code MUST use this interface, never a backend directly.
    This is the contract that prevents future migration tax.
    """

    @abstractmethod
    async def initialize(self) -> None:
        """Create collections, indexes, etc. Idempotent."""

    @abstractmethod
    async def add(self, records: List[VectorRecord]) -> List[str]:
        """Add records. Returns list of inserted IDs."""

    @abstractmethod
    async def upsert(self, records: List[VectorRecord]) -> List[str]:
        """Insert or update by ID. Returns upserted IDs."""

    @abstractmethod
    async def search(self, query: SearchQuery) -> List[SearchResult]:
        """Top-K similarity search within workspace scope."""

    @abstractmethod
    async def hybrid_search(
        self, query: SearchQuery, bm25_weight: float = 0.3
    ) -> List[SearchResult]:
        """Vector + BM25 combined. Backend may degrade to vector-only."""

    @abstractmethod
    async def delete(self, ids: List[str]) -> int:
        """Delete by ID. Returns count deleted."""

    @abstractmethod
    async def delete_by_workspace(self, workspace_id: str) -> int:
        """Bulk delete for tenant offboarding / GDPR."""

    @abstractmethod
    async def count(self, workspace_id: Optional[str] = None) -> int:
        """Record count, optionally scoped to a workspace."""

    @abstractmethod
    async def get(self, ids: List[str]) -> List[VectorRecord]:
        """Fetch records by ID (for re-rank, hydration, export)."""

    @abstractmethod
    async def list_all(
        self,
        workspace_id: Optional[str] = None,
        limit: int = 1000,
        offset: int = 0,
    ) -> List[VectorRecord]:
        """Paginated iteration. Used by migration tool."""

    @abstractmethod
    async def health_check(self) -> bool:
        """Liveness probe."""

    @abstractmethod
    def backend_name(self) -> str:
        """Return backend identifier for logs / metrics."""
```

**Two extra methods beyond the minimum** — `hybrid_search` and `list_all` — are explicitly required because every real-world vector store eventually needs them. Adding them now means we don't hit the "oh, we also need paginated iteration for migration" surprise later.

### 2.3 The Migration Tool (One Script, Any → Any)

```python
# scripts/migrate_vector_store.py
"""
Migrate between any two BaseVectorStore backends.

Examples:
    python -m scripts.migrate_vector_store \\
        --from chroma --to pgvector \\
        --workspace ws-1
    
    python -m scripts.migrate_vector_store \\
        --from pgvector --to cloudflare_vectorize

Why this exists: so you never hand-write a migration script again.
"""

import asyncio
import argparse
import logging
from typing import Type

from nexora_crawler.vector_store.base import BaseVectorStore, VectorRecord
from nexora_crawler.vector_store.factory import build_vector_store

logger = logging.getLogger(__name__)


async def migrate(
    source: BaseVectorStore,
    target: BaseVectorStore,
    workspace_id: str = None,
    batch_size: int = 500,
    dry_run: bool = False,
) -> int:
    """
    Stream records from source, batch-add to target.
    Returns number of records migrated.
    """
    if not await source.health_check():
        raise RuntimeError(f"Source backend unhealthy: {source.backend_name()}")
    if not await target.health_check():
        raise RuntimeError(f"Target backend unhealthy: {target.backend_name()}")

    total = await source.count(workspace_id)
    logger.info(
        "Migrating %s records %s → %s (workspace=%s, batch_size=%d)",
        total, source.backend_name(), target.backend_name(),
        workspace_id or "<all>", batch_size,
    )

    if dry_run:
        logger.info("DRY RUN — no writes")
        return 0

    await target.initialize()
    migrated = 0
    offset = 0
    while True:
        records = await source.list_all(
            workspace_id=workspace_id, limit=batch_size, offset=offset
        )
        if not records:
            break
        await target.upsert(records)
        migrated += len(records)
        offset += batch_size
        if migrated % (batch_size * 5) == 0:
            logger.info("  progress: %d / %d", migrated, total)

    logger.info("Migration complete: %d records", migrated)
    return migrated


# CLI entry point
def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--from", dest="from_backend", required=True,
                       choices=["chroma", "pgvector", "qdrant", "cloudflare_vectorize"])
    parser.add_argument("--to", dest="to_backend", required=True,
                       choices=["chroma", "pgvector", "qdrant", "cloudflare_vectorize"])
    parser.add_argument("--workspace", default=None)
    parser.add_argument("--batch-size", type=int, default=500)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    src = build_vector_store(args.from_backend)
    dst = build_vector_store(args.to_backend)
    asyncio.run(migrate(src, dst, args.workspace, args.batch_size, args.dry_run))


if __name__ == "__main__":
    main()
```

---

## 3. COMPONENT SPECIFICATIONS

### 3.1 VectorStore Interface & Factory

**File:** `nexora_crawler/vector_store/base.py` (above)

**File:** `nexora_crawler/vector_store/factory.py`

```python
"""
Build vector store backends from config.
Switching backends = changing one env var. Zero code change.
"""

import os
import logging
from .base import BaseVectorStore

logger = logging.getLogger(__name__)


def build_vector_store(backend_name: str = None) -> BaseVectorStore:
    """
    Build the configured vector store backend.
    
    Backend chosen by NEXORA_VECTOR_BACKEND env var:
      - 'pgvector' (default — managed Postgres + pgvector)
      - 'chroma' (legacy / local dev)
      - 'qdrant' (high-scale, optional)
      - 'cloudflare_vectorize' (edge, serverless-friendly)
    """
    backend = (backend_name or os.getenv("NEXORA_VECTOR_BACKEND", "pgvector")).lower()

    if backend == "pgvector":
        from .pgvector_store import PgVectorStore
        return PgVectorStore(
            database_url=os.getenv("NEXORA_DATABASE_URL"),
            embedding_dim=int(os.getenv("NEXORA_EMBEDDING_DIM", "768")),
        )

    elif backend == "chroma":
        from .chroma_store import ChromaVectorStore
        return ChromaVectorStore(
            path=os.getenv("NEXORA_CHROMA_PATH", "./data/chroma"),
        )

    elif backend == "qdrant":
        from .qdrant_store import QdrantVectorStore
        return QdrantVectorStore(
            url=os.getenv("NEXORA_QDRANT_URL"),
            api_key=os.getenv("NEXORA_QDRANT_API_KEY"),
        )

    elif backend == "cloudflare_vectorize":
        from .cloudflare_vectorize_store import CloudflareVectorizeStore
        return CloudflareVectorizeStore(
            account_id=os.getenv("CF_ACCOUNT_ID"),
            api_token=os.getenv("CF_API_TOKEN"),
            index_name=os.getenv("CF_VECTORIZE_INDEX", "nexora-prod"),
        )

    raise ValueError(f"Unknown vector backend: {backend}")
```

### 3.2 Default Backend: pgvector

**File:** `nexora_crawler/vector_store/pgvector_store.py`

```python
"""
PgVectorStore — default vector backend.

Why pgvector:
- Lives in same Postgres as metadata (one connection, one backup, one truth)
- No extra service to deploy
- HNSW index gives sub-100ms search at 10M vectors
- Managed on Supabase, Neon, RDS, Timescale — pick your free tier

Trade-off: weaker than Qdrant at 100M+ vectors.
Mitigation: sharding later, or migrate via the tool above.
"""

import logging
from typing import List, Optional
import asyncpg
import numpy as np

from .base import (
    BaseVectorStore, VectorRecord, SearchQuery, SearchResult,
)

logger = logging.getLogger(__name__)


class PgVectorStore(BaseVectorStore):

    def __init__(self, database_url: str, embedding_dim: int = 768):
        self._url = database_url
        self._dim = embedding_dim
        self._pool: Optional[asyncpg.Pool] = None

    async def initialize(self) -> None:
        self._pool = await asyncpg.create_pool(self._url, min_size=2, max_size=10)
        async with self._pool.acquire() as conn:
            await conn.execute("CREATE EXTENSION IF NOT EXISTS vector")
            await conn.execute(f"""
                CREATE TABLE IF NOT EXISTS vector_records (
                    id              TEXT PRIMARY KEY,
                    workspace_id    TEXT NOT NULL,
                    content         TEXT NOT NULL,
                    embedding       vector({self._dim}),
                    source_type     TEXT DEFAULT 'chunk',
                    source_id       TEXT,
                    metadata        JSONB DEFAULT '{{}}',
                    created_at      TIMESTAMPTZ DEFAULT now()
                )
            """)
            # HNSW index — best recall/speed tradeoff for <10M vectors
            await conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_vector_hnsw
                ON vector_records
                USING hnsw (embedding vector_cosine_ops)
            """)
            await conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_vector_workspace
                ON vector_records (workspace_id)
            """)
            # GIN on metadata JSONB for filter queries
            await conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_vector_metadata
                ON vector_records
                USING gin (metadata)
            """)
        logger.info("[pgvector] Initialized (dim=%d)", self._dim)

    async def add(self, records: List[VectorRecord]) -> List[str]:
        return await self.upsert(records)

    async def upsert(self, records: List[VectorRecord]) -> List[str]:
        ids = [r.id for r in records]
        async with self._pool.acquire() as conn:
            await conn.executemany("""
                INSERT INTO vector_records
                    (id, workspace_id, content, embedding, source_type,
                     source_id, metadata)
                VALUES ($1, $2, $3, $4::vector, $5, $6, $7)
                ON CONFLICT (id) DO UPDATE SET
                    workspace_id = EXCLUDED.workspace_id,
                    content      = EXCLUDED.content,
                    embedding    = EXCLUDED.embedding,
                    source_type  = EXCLUDED.source_type,
                    source_id    = EXCLUDED.source_id,
                    metadata     = EXCLUDED.metadata
            """, [
                (r.id, r.workspace_id, r.content,
                 "[" + ",".join(map(str, r.embedding)) + "]",
                 r.source_type, r.source_id,
                 _json(r.metadata))
                for r in records
            ])
        return ids

    async def search(self, query: SearchQuery) -> List[SearchResult]:
        # Compose SQL with tenant scope always enforced
        where_parts = []
        params = []

        if query.workspace_id is None:
            raise ValueError("workspace_id is required for tenant scoping")
        where_parts.append(f"workspace_id = ${len(params) + 1}")
        params.append(query.workspace_id)

        # Embedding source: either provided or text-to-embed handled by caller
        if query.vector is None:
            raise ValueError("Either vector or text must be provided")
        params.append("[" + ",".join(map(str, query.vector)) + "]")

        # Optional metadata filter
        if query.filter:
            # Convert simple {"key": "value"} → SQL JSONB match
            for k, v in query.filter.items():
                where_parts.append(f"metadata->>{len(params)+1} = ${len(params)+2}")
                # NB real impl uses dynamic SQL builder, not string concat
                break  # simplified here

        where_sql = " AND ".join(where_parts)
        # Cosine similarity = 1 - cosine distance
        sql = f"""
            SELECT id, content, metadata, workspace_id,
                   1 - (embedding <=> ${len(params)}::vector) AS score
            FROM vector_records
            WHERE {where_sql}
              AND 1 - (embedding <=> ${len(params)}::vector) >= ${len(params)+1}
            ORDER BY embedding <=> ${len(params)}::vector
            LIMIT ${len(params)+2}
        """
        params.append(query.min_similarity)
        params.append(query.top_k)

        async with self._pool.acquire() as conn:
            rows = await conn.fetch(sql, *params)
        return [
            SearchResult(
                id=r["id"], score=float(r["score"]), content=r["content"],
                metadata=_unjson(r["metadata"]), workspace_id=r["workspace_id"],
            )
            for r in rows
        ]

    async def hybrid_search(self, query, bm25_weight=0.3):
        # pgvector alone has no BM25. Use Postgres FTS extension as a stand-in,
        # or document the degraded behavior.
        if not query.text:
            return await self.search(query)
        # ts_rank + vector similarity → weighted sum
        # (Full impl uses tsvector column; abbreviated here)
        return await self.search(query)  # degrade to vector-only with notice

    async def delete(self, ids):
        async with self._pool.acquire() as conn:
            result = await conn.execute(
                "DELETE FROM vector_records WHERE id = ANY($1::text[])", ids
            )
        # PG returns 'DELETE <n>'
        return int(result.split()[-1]) if result else 0

    async def delete_by_workspace(self, workspace_id):
        async with self._pool.acquire() as conn:
            result = await conn.execute(
                "DELETE FROM vector_records WHERE workspace_id = $1", workspace_id
            )
        return int(result.split()[-1]) if result else 0

    async def count(self, workspace_id=None):
        async with self._pool.acquire() as conn:
            if workspace_id:
                row = await conn.fetchrow(
                    "SELECT COUNT(*) FROM vector_records WHERE workspace_id=$1",
                    workspace_id,
                )
            else:
                row = await conn.fetchrow("SELECT COUNT(*) FROM vector_records")
        return int(row[0])

    async def get(self, ids):
        async with self._pool.acquire() as conn:
            rows = await conn.fetch(
                "SELECT * FROM vector_records WHERE id = ANY($1::text[])", ids
            )
        return [_row_to_record(r) for r in rows]

    async def list_all(self, workspace_id=None, limit=1000, offset=0):
        where = "WHERE workspace_id = $1" if workspace_id else ""
        params = ([workspace_id] if workspace_id else []) + [limit, offset]
        async with self._pool.acquire() as conn:
            rows = await conn.fetch(
                f"SELECT * FROM vector_records {where} "
                f"ORDER BY created_at LIMIT ${len(params)-1} OFFSET ${len(params)}",
                *params,
            )
        return [_row_to_record(r) for r in rows]

    async def health_check(self):
        try:
            async with self._pool.acquire() as conn:
                await conn.fetchval("SELECT 1")
            return True
        except Exception as e:
            logger.error("[pgvector] Health check failed: %s", e)
            return False

    def backend_name(self):
        return "pgvector"


def _json(d):
    import json
    return json.dumps(d)


def _unjson(s):
    if isinstance(s, dict):
        return s
    import json
    return json.loads(s) if s else {}


def _row_to_record(row):
    # Convert pgvector string "[...]" back to list[float]
    raw = row["embedding"]
    if isinstance(raw, str):
        embedding = [float(x) for x in raw.strip("[]").split(",")]
    else:
        embedding = list(raw)
    return VectorRecord(
        id=row["id"], content=row["content"], embedding=embedding,
        workspace_id=row["workspace_id"],
        source_type=row["source_type"], source_id=row["source_id"],
        metadata=_unjson(row["metadata"]),
    )
```

**Then the Chroma and Qdrant backends implement the same interface.** Migration script works against any pair.

### 3.3 Vector Search Service (the user's request)

**File:** `nexora_crawler/services/vector_search_service.py`

This is the HTTP layer that hides the backend. When you swap pgvector → Qdrant later, this file does NOT change.

```python
"""
Vector Search Service — vendor-neutral HTTP API.

Single entry point for all semantic/hybrid search.
The endpoint contract is stable across backends.
"""

import logging
from typing import Optional, List, Dict, Any
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from nexora_crawler.vector_store.factory import build_vector_store
from nexora_crawler.api.auth import get_workspace_id  # tenant scope

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
    backend: str        # which store served the query
    took_ms: float


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
    """Vector + BM25 hybrid."""
    sr = SearchRequest(
        query=req.query, top_k=req.top_k,
        filter={}, min_similarity=0.0,
    )
    return await _do_search(sr, workspace_id, hybrid=True,
                            bm25_weight=req.bm25_weight)


@router.post("/by-source/{source_type}/{source_id}/similar",
             response_model=SearchResponse)
async def find_similar(
    source_type: str,
    source_id: str,
    top_k: int = 10,
    workspace_id: str = Depends(get_workspace_id),
):
    """Find records similar to a known one (e.g. 'pages like this one')."""
    store = build_vector_store()
    recs = await store.get([source_id])
    if not recs:
        raise HTTPException(404, f"Source {source_id} not found")
    record = recs[0]
    # Enforce tenant scope even for source lookup
    if record.workspace_id != workspace_id:
        raise HTTPException(403, "Cross-workspace access denied")
    query = SearchQuery(
        vector=record.embedding, workspace_id=workspace_id,
        top_k=top_k + 1,   # +1 because the seed itself will match
    )
    results = await store.search(query)
    # Filter out the seed itself
    filtered = [r for r in results if r.id != source_id][:top_k]
    return SearchResponse(
        query=f"similar:{source_id}",
        results=[SearchHit(**_to_hit(r).dict()) for r in filtered],
        backend=store.backend_name(),
        took_ms=0.0,
    )


# ---- Internal ----

async def _do_search(req: SearchRequest, workspace_id: str,
                     hybrid: bool, bm25_weight: float = 0.3):
    import time
    store = build_vector_store()
    started = time.perf_counter()

    # Embed the query text. Pluggable: OpenAI, Ollama, Cloudflare AI
    from nexora_crawler.ai.embedding_engine import UnifiedEmbeddingEngine
    engine = UnifiedEmbeddingEngine()
    embedding = await engine.embed(req.query)
    if embedding is None:
        raise HTTPException(503, "Embedding service unavailable")

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
        if not req.include_content and len(r.content) > 200:
            content_preview = r.content[:200] + "…"
        else:
            content_preview = r.content
        hits.append(SearchHit(
            id=r.id, score=r.score, content=content_preview,
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
```

**Why this matters for you:** when you migrate Chroma → Supabase, you change `NEXORA_VECTOR_BACKEND=pgvector` and `NEXORA_DATABASE_URL=...`. **Nothing else changes.** API contracts, search logic, frontend code — all stable. You will never rewrite search logic again.

### 3.4 JSON Schema Extraction Pipeline

**File:** `nexora_crawler/pipelines/schema_extraction_pipeline.py`
**Priority:** 280 (after VectorIndex at 270)

This is Firecrawl's killer feature, built into Phase 7.

```python
"""
SchemaExtractionPipeline — Phase 7.

User submits a JSON Schema; the pipeline uses LiteLLM structured output
to populate it from each crawled page.

Example user schema:
    {
      "type": "object",
      "properties": {
        "product_name":  {"type": "string"},
        "price":         {"type": "number"},
        "in_stock":      {"type": "boolean"},
        "features":      {"type": "array", "items": {"type": "string"}}
      }
    }

Result per page:
    item["extracted"] = {
      "product_name": "Acme Widget",
      "price": 29.99,
      "in_stock": True,
      "features": ["durable", "lightweight"]
    }
"""

import logging
import json
from typing import Dict, Any, Optional

from pydantic import BaseModel, Field, create_model, ValidationError
import litellm

logger = logging.getLogger(__name__)


class SchemaExtractionPipeline:
    """Scrapy pipeline. Priority 280."""

    def __init__(self, crawler):
        self.settings = crawler.settings
        self.workspace_id = crawler.settings.get("NEXORA_WORKSPACE_ID", "default")
        self.enabled = self.settings.getbool("NEXORA_SCHEMA_EXTRACTION_ENABLED", False)
        self.model = self.settings.get("NEXORA_SCHEMA_EXTRACTION_MODEL", "gpt-4o-mini")
        self.stats = {
            "pages_processed": 0,
            "pages_extracted": 0,
            "validation_failures": 0,
            "extraction_errors": 0,
        }

    @classmethod
    def from_crawler(cls, crawler):
        return cls(crawler)

    async def process_item(self, item, spider):
        if not self.enabled:
            item["extracted"] = None
            return item

        json_schema = self.settings.get("NEXORA_USER_JSON_SCHEMA")
        if not json_schema:
            item["extracted"] = None
            return item

        # Build a Pydantic model from the user's schema
        try:
            pyd_model = self._schema_to_pydantic(json_schema)
        except Exception as e:
            logger.error("[SchemaExtract] Bad schema: %s", e)
            item["extracted"] = None
            return item

        markdown = item.get("markdown", "") or item.get("clean_text", "")
        if len(markdown) < 50:
            item["extracted"] = None
            return item

        # Truncate to fit context
        content = markdown[: self.settings.getint("NEXORA_SCHEMA_CONTENT_MAX_CHARS", 8000)]

        try:
            response = await litellm.acompletion(
                model=self.model,
                messages=[
                    {
                        "role": "system",
                        "content": "You extract structured data from web pages. "
                                   "Respond only with JSON matching the schema.",
                    },
                    {
                        "role": "user",
                        "content": f"Extract fields per schema.\n\n"
                                   f"Schema:\n{json.dumps(json_schema, indent=2)}\n\n"
                                   f"Page:\n{content}",
                    },
                ],
                response_format=pyd_model,    # enforces structure via Pydantic
                temperature=0.0,
            )
            extracted = json.loads(response.choices[0].message.content)
            # Validate against user schema one more time
            validated = pyd_model(**extracted)
            item["extracted"] = validated.dict()
            self.stats["pages_extracted"] += 1
        except ValidationError as e:
            logger.warning("[SchemaExtract] Validation failed: %s", e)
            item["extracted"] = None
            self.stats["validation_failures"] += 1
        except Exception as e:
            logger.error("[SchemaExtract] Extraction failed: %s", e)
            item["extracted"] = None
            self.stats["extraction_errors"] += 1

        self.stats["pages_processed"] += 1
        return item

    def _schema_to_pydantic(self, schema: Dict) -> BaseModel:
        """Convert JSON Schema dict → Pydantic model class."""
        # Simplified. Real impl handles nested objects, arrays, refs, etc.
        fields = {}
        for name, prop in schema.get("properties", {}).items():
            py_type = self._json_type_to_python(prop.get("type", "string"))
            fields[name] = (Optional[py_type], None)
        return create_model("DynamicSchema", **fields)

    def _json_type_to_python(self, t: str):
        return {"string": str, "integer": int, "number": float,
                "boolean": bool, "array": list, "object": dict}.get(t, str)

    def close_spider(self, spider):
        logger.info("[SchemaExtract] Stats: %s", self.stats)
```

**HTTP endpoint to submit a schema-driven crawl:**

```python
# nexora_crawler/api/routes/extract.py

from fastapi import APIRouter, Depends
from pydantic import BaseModel, HttpUrl, Field
from typing import Dict, Any, Optional
import uuid

from nexora_crawler.tasks.crawl_with_schema import crawl_with_schema_task

router = APIRouter(prefix="/v1/extract", tags=["Schema Extraction"])


class ExtractRequest(BaseModel):
    url: HttpUrl
    strategy: str = "whole-website"
    max_pages: int = Field(50, ge=1, le=10000)
    json_schema: Dict[str, Any]   # user-provided JSON Schema
    output_format: str = "json"


class ExtractResponse(BaseModel):
    job_id: str
    status: str
    url: str
    schema_fields: int


@router.post("/schema", response_model=ExtractResponse, status_code=202)
async def extract_schema(
    req: ExtractRequest,
    workspace_id: str = Depends(get_workspace_id),
):
    """Submit a schema-driven crawl. Returns 202 immediately."""
    job_id = str(uuid.uuid4())
    # Persist user's schema so worker can re-fetch it
    await save_user_schema(workspace_id, job_id, req.json_schema)
    # Dispatch to Celery
    crawl_with_schema_task.delay(
        job_id=job_id, url=str(req.url), strategy=req.strategy,
        max_pages=req.max_pages, workspace_id=workspace_id,
        output_format=req.output_format,
    )
    return ExtractResponse(
        job_id=job_id, status="queued", url=str(req.url),
        schema_fields=len(req.json_schema.get("properties", {})),
    )
```

### 3.5 Webhook Subsystem

**Files:**
- `nexora_crawler/api/routes/webhooks.py`
- `nexora_crawler/tasks/webhook_delivery.py`

```python
# ---- DB tables (added in Phase 7 migration) ----
#
# CREATE TABLE webhooks (
#     id INTEGER PRIMARY KEY AUTOINCREMENT,
#     workspace_id TEXT NOT NULL,
#     url TEXT NOT NULL,
#     event_types TEXT NOT NULL,    -- JSON array
#     secret TEXT,                   -- HMAC signing key
#     is_active INTEGER DEFAULT 1,
#     created_at TEXT DEFAULT (datetime('now'))
# );
#
# CREATE TABLE webhook_deliveries (
#     id INTEGER PRIMARY KEY AUTOINCREMENT,
#     webhook_id INTEGER NOT NULL,
#     job_id TEXT,
#     event_type TEXT,
#     status_code INTEGER,
#     attempt INTEGER,
#     delivered_at TEXT,
#     error TEXT
# );

import asyncio
import hmac
import hashlib
import json
import logging
import httpx
from datetime import datetime, timezone

from celery import shared_task
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, HttpUrl

from nexora_crawler.api.database.connection import get_db

logger = logging.getLogger(__name__)


# ---- HTTP endpoints (Phase 4C route added in Phase 7) ----

router = APIRouter(prefix="/v1/webhooks", tags=["Webhooks"])


class WebhookCreate(BaseModel):
    url: HttpUrl
    event_types: list[str] = ["job.completed", "job.failed"]
    secret: str | None = None   # auto-generated if None


class WebhookOut(BaseModel):
    id: int
    url: str
    event_types: list[str]
    is_active: bool
    created_at: str


@router.post("", response_model=WebhookOut, status_code=201)
async def create_webhook(req: WebhookCreate, workspace_id: str = Depends(get_workspace_id)):
    import secrets
    secret = req.secret or secrets.token_urlsafe(32)
    db = await get_db()
    row = await db.fetch_one("""
        INSERT INTO webhooks (workspace_id, url, event_types, secret, is_active)
        VALUES (?, ?, ?, ?, 1)
        RETURNING id, url, event_types, is_active, created_at
    """, (workspace_id, str(req.url), json.dumps(req.event_types), secret))
    out = dict(row)
    out["event_types"] = json.loads(out["event_types"])
    # Return the secret ONCE — never again
    out["_secret_display_once"] = secret
    return out


@router.get("", response_model=list[WebhookOut])
async def list_webhooks(workspace_id: str = Depends(get_workspace_id)):
    db = await get_db()
    rows = await db.fetch_all(
        "SELECT id, url, event_types, is_active, created_at "
        "FROM webhooks WHERE workspace_id = ? ORDER BY id DESC",
        (workspace_id,),
    )
    out = []
    for r in rows:
        r = dict(r)
        r["event_types"] = json.loads(r["event_types"])
        out.append(r)
    return out


@router.delete("/{webhook_id}", status_code=204)
async def delete_webhook(webhook_id: int, workspace_id: str = Depends(get_workspace_id)):
    db = await get_db()
    await db.execute(
        "DELETE FROM webhooks WHERE id = ? AND workspace_id = ?",
        (webhook_id, workspace_id),
    )


# ---- Delivery worker (Celery task in Phase 5 harness) ----

@shared_task(bind=True, max_retries=5, default_retry_delay=10)
def deliver_webhook(self, webhook_id: int, event_type: str,
                    job_id: str, payload: dict):
    """
    Delivers one webhook. Retries with exponential backoff.
    Records delivery history in webhook_deliveries.
    """
    import asyncio
    asyncio.run(_deliver_async(webhook_id, event_type, job_id, payload, self.request.retries))


async def _deliver_async(webhook_id, event_type, job_id, payload, attempt):
    db = await get_db()
    webhook = await db.fetch_one(
        "SELECT * FROM webhooks WHERE id = ? AND is_active = 1", (webhook_id,)
    )
    if not webhook:
        logger.warning("[Webhook] %s inactive or deleted", webhook_id)
        return
    webhook = dict(webhook)

    # Sign the body with HMAC-SHA256
    body = json.dumps({
        "event": event_type,
        "job_id": job_id,
        "data": payload,
        "delivered_at": datetime.now(timezone.utc).isoformat(),
        "attempt": attempt + 1,
    }, separators=(",", ":")).encode()
    sig = hmac.new(
        webhook["secret"].encode(), body, hashlib.sha256
    ).hexdigest()
    headers = {
        "Content-Type": "application/json",
        "X-Nexora-Signature": f"sha256={sig}",
        "X-Nexora-Event": event_type,
        "X-Nexora-Delivery-Id": str(webhook_id),
        "X-Nexora-Attempt": str(attempt + 1),
    }

    try:
        async with httpx.AsyncClient(timeout=15) as client:
            response = await client.post(webhook["url"], content=body, headers=headers)
        ok = 200 <= response.status_code < 300
        await db.execute(
            "INSERT INTO webhook_deliveries "
            "(webhook_id, job_id, status_code, attempt, delivered_at) "
            "VALUES (?, ?, ?, ?, ?)",
            (webhook_id, job_id, response.status_code, attempt + 1,
             datetime.now(timezone.utc).isoformat()),
        )
        if not ok:
            raise RuntimeError(f"Webhook {webhook_id} returned {response.status_code}")
    except Exception as exc:
        # Exponential backoff: 10s, 20s, 40s, 80s, 160s
        delay = 10 * (2 ** attempt)
        deliver_webhook.retry(
            args=[webhook_id, event_type, job_id, payload],
            countdown=delay,
        )


# ---- Pub/sub bridge from app code ----
# Anywhere in Phase 5/6/7 worker code:
#   from nexora_crawler.events import publish
#   await publish("job.completed", workspace_id, {"job_id": "...", "pages": 42})

import redis.asyncio as aioredis
import os

_redis = None
async def _get_redis():
    global _redis
    if _redis is None:
        _redis = aioredis.from_url(os.getenv("REDIS_URL", "redis://localhost:6379/0"))
    return _redis

async def publish(event_type, workspace_id, payload):
    r = await _get_redis()
    await r.publish(f"nexora:events:{workspace_id}",
                    json.dumps({"event": event_type, "payload": payload}))
    # Also dispatch webhooks
    db = await get_db()
    rows = await db.fetch_all(
        "SELECT id FROM webhooks WHERE workspace_id=? AND is_active=1 "
        "AND event_types LIKE ?",
        (workspace_id, f'%"{event_type}"%'),
    )
    for row in rows:
        deliver_webhook.delay(row["id"], event_type, payload.get("job_id", ""), payload)
```

**What this unlocks:** other systems can subscribe to your crawls. They no longer need to poll. Delivery is guaranteed (5x retry with backoff) and signed (HMAC-SHA256).

### 3.6 Job Type Registry (Decouples "Crawl-Only")

**File:** `nexora_crawler/jobs/registry.py`

```python
"""
JobTypeRegistry — Phase 7.

The dispatcher the Celery workers use. Replaces the hardcoded
'crawl_website' task with a generic system that handles ANY job type.

Built-in types:
  - crawl           : standard crawl
  - schema_extract  : crawl + JSON-Schema field extraction
  - index_search    : pure vector search, no crawl
  - index_add       : add records to vector store
  - export          : export existing crawl results
  - summarize       : re-run AI enrichment on existing data

Plugin model: third parties can register custom types via Python entry points.
"""

import logging
import importlib
from typing import Dict, Callable, Any
from dataclasses import dataclass
from pydantic import BaseModel

logger = logging.getLogger(__name__)


@dataclass
class JobHandler:
    name: str
    handler: Callable
    input_schema: type[BaseModel]
    output_schema: type[BaseModel]
    timeout_seconds: int = 3600
    is_external: bool = False   # served via API even without Celery


class JobTypeRegistry:
    _handlers: Dict[str, JobHandler] = {}

    @classmethod
    def register(cls, handler: JobHandler):
        cls._handlers[handler.name] = handler
        logger.info("[Jobs] Registered handler: %s", handler.name)

    @classmethod
    def get(cls, name: str) -> JobHandler:
        if name not in cls._handlers:
            raise KeyError(f"Job type not registered: {name}. "
                           f"Available: {list(cls._handlers.keys())}")
        return cls._handlers[name]

    @classmethod
    def list(cls):
        return list(cls._handlers.keys())


# ---- Generic dispatcher task ----

def dispatch_job(job_type: str, input_data: dict, workspace_id: str,
                 job_id: str = None) -> dict:
    """
    Resolve a job type, validate input, run handler.
    Used by:
      - Celery workers (queue)
      - Direct API calls (sync, with is_external=True)
    """
    handler = JobTypeRegistry.get(job_type)
    validated = handler.input_schema(**input_data)
    return handler.handler(
        input=validated, workspace_id=workspace_id, job_id=job_id,
    )


# ---- Built-in handlers (auto-registered on import) ----

from .handlers.crawl import crawl_handler, CrawlInput, CrawlOutput
from .handlers.schema_extract import schema_extract_handler, SchemaExtractInput, SchemaExtractOutput
from .handlers.index_search import index_search_handler, IndexSearchInput, IndexSearchOutput
from .handlers.index_add import index_add_handler, IndexAddInput, IndexAddOutput
from .handlers.export import export_handler, ExportInput, ExportOutput

JobTypeRegistry.register(JobHandler("crawl",          crawl_handler,          CrawlInput, CrawlOutput))
JobTypeRegistry.register(JobHandler("schema_extract", schema_extract_handler,  SchemaExtractInput, SchemaExtractOutput))
JobTypeRegistry.register(JobHandler("index_search",   index_search_handler,    IndexSearchInput,   IndexSearchOutput, is_external=True))
JobTypeRegistry.register(JobHandler("index_add",      index_add_handler,       IndexAddInput,      IndexAddOutput,    is_external=True))
JobTypeRegistry.register(JobHandler("export",         export_handler,          ExportInput,        ExportOutput,      timeout_seconds=600))


# ---- Plugin entry point ----
"""
Third-party extensions can register new job types via pyproject.toml:

[project.entry-points."nexora.job_types"]
my_custom_job = "my_pkg.handlers:my_job_handler"

On startup, the registry loads these entry points and registers them.
"""
def load_external_handlers():
    try:
        from importlib.metadata import entry_points
        eps = entry_points(group="nexora.job_types")
        for ep in eps:
            mod = importlib.import_module(ep.module)
            handler = getattr(mod, ep.attr)
            JobTypeRegistry.register(handler)
            logger.info("[Jobs] Loaded external handler: %s", ep.name)
    except Exception as e:
        logger.debug("[Jobs] No external handlers loaded: %s", e)
```

**Generic HTTP endpoint (replaces Phase 4C's `/crawl/start` specific route):**

```python
# nexora_crawler/api/routes/jobs.py

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from typing import Any, Dict
import uuid

from nexora_crawler.jobs.registry import JobTypeRegistry

router = APIRouter(prefix="/v1/jobs", tags=["Jobs"])


class JobSubmit(BaseModel):
    type: str                              # e.g. 'crawl', 'schema_extract'
    input: Dict[str, Any]                  # validated against the type's input_schema
    async_run: bool = Field(True, description="If false, runs inline and returns result")


class JobSubmitResponse(BaseModel):
    job_id: str
    type: str
    status: str
    result: Any | None = None              # populated only when async_run=False


@router.post("", response_model=JobSubmitResponse, status_code=202)
async def submit_job(req: JobSubmit, workspace_id: str = Depends(get_workspace_id)):
    # Verify job type is registered
    try:
        handler = JobTypeRegistry.get(req.type)
    except KeyError as e:
        raise HTTPException(400, str(e))

    job_id = str(uuid.uuid4())

    if not req.async_run and handler.is_external:
        # Run inline for fast, lightweight ops
        from nexora_crawler.jobs.registry import dispatch_job
        try:
            result = dispatch_job(req.type, req.input, workspace_id, job_id)
            return JobSubmitResponse(job_id=job_id, type=req.type,
                                     status="completed", result=result)
        except Exception as e:
            raise HTTPException(500, f"Job failed: {e}")

    # Async path — dispatch to Celery
    from nexora_crawler.tasks.dispatcher import dispatcher_task
    dispatcher_task.delay(
        job_id=job_id, job_type=req.type,
        input_data=req.input, workspace_id=workspace_id,
    )
    return JobSubmitResponse(job_id=job_id, type=req.type, status="queued")
```

### 3.7 Quota & Entitlement Engine

**File:** `nexora_crawler/entitlements/engine.py`

```python
"""
QuotaEngine — Phase 7.

Per-workspace soft + hard limits. One noisy tenant cannot drain the system.

Default free tier:
  - 10,000 pages/month
  - 1 GB blob storage
  - 100 vector records (free tier cap to encourage Chroma trial)
  - 60 API calls/minute
  - 10 schema extraction jobs/day

Soft quota: request still succeeds, gets logged + advisory response
Hard quota: request rejected with 429 + Retry-After header
"""

import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone, timedelta
from typing import Literal

from fastapi import HTTPException, Depends
from ..api.database.connection import get_db

logger = logging.getLogger(__name__)


@dataclass
class QuotaConfig:
    workspace_id: str
    pages_per_month: int = 10000
    storage_gb: int = 1
    vector_records: int = 100000
    api_rpm: int = 60
    schema_extracts_per_day: int = 10


class QuotaEngine:

    @staticmethod
    async def get_config(workspace_id: str) -> QuotaConfig:
        db = await get_db()
        row = await db.fetch_one(
            "SELECT * FROM workspace_quotas WHERE workspace_id = ?",
            (workspace_id,),
        )
        if not row:
            return QuotaConfig(workspace_id=workspace_id)
        return QuotaConfig(**dict(row))

    @staticmethod
    async def check_pages(workspace_id: str, requested: int,
                          mode: Literal["soft", "hard"] = "hard"):
        config = await QuotaEngine.get_config(workspace_id)
        period_start = datetime.now(timezone.utc).replace(
            day=1, hour=0, minute=0, second=0, microsecond=0
        ).isoformat()
        db = await get_db()
        row = await db.fetch_one("""
            SELECT COALESCE(SUM(pages_crawled), 0) AS used
            FROM crawl_jobs
            WHERE workspace_id = ?
              AND started_at >= ?
        """, (workspace_id, period_start))
        used = row["used"] or 0
        if used + requested > config.pages_per_month:
            if mode == "hard":
                raise HTTPException(
                    status_code=429,
                    detail=f"Pages quota exceeded: {used}/{config.pages_per_month}. "
                           f"Resets on the 1st of next month.",
                    headers={"Retry-After": "86400"},
                )
            else:
                logger.warning(
                    "[Quota] workspace=%s exceeded soft pages quota: %d > %d",
                    workspace_id, used, config.pages_per_month,
                )

    @staticmethod
    async def record_pages(workspace_id: str, count: int):
        # Called from crawl_worker on job complete
        db = await get_db()
        await db.execute("""
            INSERT INTO usage_records
                (workspace_id, period, pages_crawled, storage_bytes,
                 vector_records, api_calls, recorded_at)
            VALUES (?, strftime('%Y-%m', 'now'), ?, 0, 0, 0, ?)
            ON CONFLICT (workspace_id, period) DO UPDATE SET
                pages_crawled = pages_crawled + ?
        """, (workspace_id, count, datetime.now(timezone.utc).isoformat(), count))


# FastAPI dependency
async def enforce_pages_quota(
    pages: int,
    workspace_id: str = Depends(get_workspace_id),
):
    await QuotaEngine.check_pages(workspace_id, pages, mode="hard")
```

### 3.8 Production Observability Hooks (OpenTelemetry)

**Files:**
- `nexora_crawler/observability/tracing.py`
- `nexora_crawler/observability/metrics.py`

```python
"""
OpenTelemetry hooks — Phase 7.

Two outputs:
  1. OTLP spans propagated through HTTP → Celery task → DB → external API
  2. Prometheus-format metrics at /metrics

Trace context is propagated through Celery headers so a single crawl
job becomes a full distributed trace across worker, API, and DB.
"""

import logging
import os
from contextlib import contextmanager

logger = logging.getLogger(__name__)

# Init lazily so app start doesn't fail if collector isn't reachable
_tracer = None
_meter = None


def init_observability():
    """Call once on app startup."""
    global _tracer, _meter
    try:
        from opentelemetry import trace, metrics
        from opentelemetry.sdk.trace import TracerProvider
        from opentelemetry.sdk.metrics import MeterProvider
        from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter
        from opentelemetry.exporter.otlp.proto.grpc.metric_exporter import OTLPMetricExporter
        from opentelemetry.sdk.trace.export import BatchSpanProcessor
        from opentelemetry.sdk.metrics.export import PeriodicExportingMetricReader

        endpoint = os.getenv("OTEL_EXPORTER_OTLP_ENDPOINT", "localhost:4317")

        tracer_provider = TracerProvider()
        tracer_provider.add_span_processor(BatchSpanProcessor(OTLPSpanExporter(endpoint=endpoint)))
        trace.set_tracer_provider(tracer_provider)
        _tracer = trace.get_tracer("nexora")

        reader = PeriodicExportingMetricReader(OTLPMetricExporter(endpoint=endpoint), 30_000)
        meter_provider = MeterProvider(metric_readers=[reader])
        metrics.set_meter_provider(meter_provider)
        _meter = metrics.get_meter("nexora")
        logger.info("[Observability] OTLP endpoint: %s", endpoint)
    except Exception as e:
        logger.warning("[Observability] Init failed, running in noop mode: %s", e)


@contextmanager
def trace_span(name: str, attributes: dict | None = None):
    if _tracer is None:
        yield None
        return
    with _tracer.start_as_current_span(name) as span:
        if attributes:
            for k, v in attributes.items():
                span.set_attribute(k, v)
        yield span


# ---- Prometheus metrics endpoint ----

# nexora_crawler/observability/metrics_endpoint.py
from fastapi import APIRouter, Response
from prometheus_client import generate_latest, Counter, Histogram, Gauge

router = APIRouter()

JOBS_SUBMITTED = Counter(
    "nexora_jobs_submitted_total",
    "Total jobs submitted", ["type", "workspace_id"]
)
JOBS_COMPLETED = Counter(
    "nexora_jobs_completed_total",
    "Total jobs completed", ["type", "workspace_id", "status"]
)
JOB_DURATION = Histogram(
    "nexora_job_duration_seconds",
    "Job processing duration", ["type"]
)
PAGES_CRAWLED = Counter(
    "nexora_pages_crawled_total",
    "Total pages crawled", ["workspace_id"]
)
EMBEDDINGS_GENERATED = Counter(
    "nexora_embeddings_generated_total",
    "Total embeddings generated", ["provider"]
)
VECTOR_SEARCH_DURATION = Histogram(
    "nexora_vector_search_seconds",
    "Vector search duration", ["backend"]
)
WEBHOOK_DELIVERIES = Counter(
    "nexora_webhook_deliveries_total",
    "Webhook deliveries", ["status_code"]
)


@router.get("/metrics", include_in_schema=False)
async def metrics():
    return Response(content=generate_latest(), media_type="text/plain; version=0.0.4")
```

**Celery task instrumentation:**

```python
# nexora_crawler/tasks/dispatcher.py

import logging
from celery import shared_task
from celery.signals import task_postrun, task_prerun

from nexora_crawler.jobs.registry import JobTypeRegistry, dispatch_job
from nexora_crawler.observability.metrics import (
    JOBS_SUBMITTED, JOBS_COMPLETED, JOB_DURATION, trace_span,
)
from opentelemetry.propagate import inject

logger = logging.getLogger(__name__)


@shared_task(bind=True)
def dispatcher_task(self, job_id, job_type, input_data, workspace_id):
    """Generic dispatcher — calls registered handler."""
    JOBS_SUBMITTED.labels(type=job_type, workspace_id=workspace_id).inc()
    with trace_span("job.run", {"job.id": job_id, "job.type": job_type}):
        try:
            result = dispatch_job(job_type, input_data, workspace_id, job_id)
            JOBS_COMPLETED.labels(
                type=job_type, workspace_id=workspace_id, status="success"
            ).inc()
            return {"status": "success", "job_id": job_id, "result": result}
        except Exception as e:
            JOBS_COMPLETED.labels(
                type=job_type, workspace_id=workspace_id, status="failed"
            ).inc()
            logger.exception("[Dispatcher] Job %s failed: %s", job_id, e)
            return {"status": "failed", "job_id": job_id, "error": str(e)}


# ---- Propagate trace context across Celery boundary ----
# Without this, your trace dies when the task crosses into the worker.
# Re-inject headers on the receiving side via task_prerun.

from opentelemetry import trace
from opentelemetry.propagate import extract

@task_prerun.connect
def task_prerun_handler(sender=None, task_id=None, task=None,
                       args=None, kwargs=None, **kw):
    # Get traceparent from task headers (set by caller) and rehydrate context
    headers = task.request.headers if hasattr(task.request, 'headers') else {}
    if headers:
        ctx = extract(headers)
        trace.set_span_in_context(trace.get_current_span(), ctx)


@shared_task(bind=True)
def dispatcher_task(self, job_id, job_type, input_data, workspace_id):
    trace_ctx = {}
    inject(trace_ctx)  # captures current trace context
    # then dispatch with propagated headers via Celery's `headers` param
    ...
```

### 3.9 Compliance: PII Redaction Pipeline

**File:** `nexora_crawler/pipelines/pii_redaction_pipeline.py`
**Priority:** 200 (after markdown extraction, before schema enricher)

```python
"""
PIIRedactionPipeline — Phase 7.

Two modes:
  - fast: regex-only (email, phone, SSN, credit card, IBAN)
  - llm:  regex + LiteLLM-based NER detection for names, addresses

Redaction is token-aware. '[REDACTED:EMAIL]' is replaced, not destroyed,
so the page is still useful for downstream pipelines (e.g. AI summary).
"""

import logging
import re
from typing import List

logger = logging.getLogger(__name__)


# Tier 1: regex (always on, free, fast)
REGEX_PATTERNS = [
    (r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b", "[REDACTED:EMAIL]"),
    (r"\b(?:\+?1[-.\s]?)?\(?\d{3}\)?[-.\s]?\d{3}[-.\s]?\d{4}\b", "[REDACTED:PHONE]"),
    (r"\b\d{3}-\d{2}-\d{4}\b", "[REDACTED:SSN]"),
    (r"\b(?:\d[ -]*?){13,19}\b", "[REDACTED:CC]"),
    (r"\b[A-Z]{2}\d{2}[A-Z\d]{4}\d{7}([A-Z\d]?){0,16}\b", "[REDACTED:IBAN]"),
    (r"\b\d{1,5}\s\w+\s(?:Street|St|Avenue|Ave|Road|Rd|Boulevard|Blvd)\b", "[REDACTED:ADDRESS]"),
]


class PIIRedactionPipeline:

    def __init__(self, crawler):
        self.settings = crawler.settings
        self.enabled = self.settings.getbool("NEXORA_PII_REDACTION_ENABLED", False)
        self.mode = self.settings.get("NEXORA_PII_MODE", "regex")  # 'regex' | 'llm'
        self.stats = {"redactions": 0, "pages_redacted": 0}

    @classmethod
    def from_crawler(cls, crawler):
        return cls(crawler)

    async def process_item(self, item, spider):
        if not self.enabled:
            return item

        text = item.get("markdown", "")
        if not text:
            return item

        original = text
        for pattern, replacement in REGEX_PATTERNS:
            text, count = re.subn(pattern, replacement, text)
            self.stats["redactions"] += count

        if self.mode == "llm" and text != original:
            # Optional LLM-based PII detection for names, organizations
            try:
                import litellm
                resp = await litellm.acompletion(
                    model=self.settings.get("NEXORA_PII_LLM_MODEL", "gpt-4o-mini"),
                    messages=[{
                        "role": "system",
                        "content": "Identify any personal names or organization names "
                                   "in the following text. Replace each with "
                                   "'[REDACTED:NAME]' or '[REDACTED:ORG]'. "
                                   "Return only the redacted text, nothing else.",
                    }, {"role": "user", "content": text[:6000]}],
                    temperature=0.0,
                )
                text = resp.choices[0].message.content
            except Exception as e:
                logger.warning("[PII] LLM pass failed, keeping regex-only: %s", e)

        if text != original:
            self.stats["pages_redacted"] += 1
        item["markdown"] = text
        item["pii_redacted"] = self.stats["redactions"] > 0
        return item

    def close_spider(self, spider):
        logger.info("[PII] Stats: %s", self.stats)


# ---- GDPR delete endpoint ----
# nexora_crawler/api/routes/gdpr.py
"""
DELETE /v1/gdpr/erase?workspace_id=...
  - Deletes all pages for workspace
  - Deletes all chunks (via vector store)
  - Deletes all crawl_jobs
  - Deletes all exports from R2
  - Marks workspace as 'purged', scheduled for hard-delete in 30 days
"""
```

### 3.10 Optional: OAuth2 / OIDC Auth (Phase 7.1)

**File:** `nexora_crawler/auth/oauth.py`

This is a sizable addition. Keep it as Phase 7.1, not blocking Phase 7.0.

```python
"""
OAuth2 / OIDC provider integrations.

Built-in providers:
  - Google Workspace
  - GitHub
  - Microsoft / Entra ID
  - Generic OIDC (any compliant provider)

For self-hosted users who don't want this, JWT-only auth stays the default.
"""

# nexora_crawler/auth/oauth.py
from fastapi import APIRouter, Depends, HTTPException
from authlib.integrations.starlette_client import OAuth

router = APIRouter(prefix="/v1/auth/oauth", tags=["OAuth"])

oauth = OAuth()

# Example: Google
oauth.register(
    name="google",
    client_id=os.getenv("GOOGLE_CLIENT_ID"),
    client_secret=os.getenv("GOOGLE_CLIENT_SECRET"),
    server_metadata_url="https://accounts.google.com/.well-known/openid-configuration",
    client_kwargs={"scope": "openid email profile"},
)


@router.get("/login/{provider}")
async def login(provider: str, request: Request):
    if provider not in ("google", "github", "microsoft", "oidc"):
        raise HTTPException(404, "Unknown provider")
    redirect_uri = request.url_for("callback", provider=provider)
    return await oauth.create_client(provider).authorize_redirect(request, redirect_uri)


@router.get("/callback/{provider}")
async def callback(provider: str, request: Request):
    token = await oauth.create_client(provider).authorize_access_token(request)
    user_info = token.get("userinfo")
    if not user_info:
        user_info = await oauth.create_client(provider).parse_id_token(request, token)
    # Provision the user (or invite to existing workspace)
    workspace_id, jwt_token = await provision_oauth_user(provider, user_info)
    return {"access_token": jwt_token, "token_type": "bearer", "workspace_id": workspace_id}
```

---

## 4. PRODUCTION CODE BLUEPRINT

### 4.1 Multi-Backend Docker Compose

```yaml
# docker-compose.yml (Phase 7 version)
version: '3.8'

services:
  # Optional — only if you don't want pgvector
  # chroma:
  #   image: chromadb/chroma:latest
  #   ports: ["8000:8000"]

  postgres:
    image: pgvector/pgvector:pg16
    environment:
      - POSTGRES_PASSWORD=${PG_PASSWORD}
    volumes:
      - pgdata:/var/lib/postgresql/data
    ports: ["5432:5432"]
    # The same single Postgres serves as relational + vector store

  redis:
    image: redis:7-alpine
    ports: ["6379:6379"]
    volumes: [redisdata:/data]

  api:
    build: .
    ports: ["8000:8000"]
    environment:
      - NEXORA_VECTOR_BACKEND=pgvector     # ← one env var, any backend
      - NEXORA_DATABASE_URL=postgresql://postgres:${PG_PASSWORD}@postgres:5432/nexora
      - REDIS_URL=redis://redis:6379/0
      - OTEL_EXPORTER_OTLP_ENDPOINT=otel-collector:4317
    depends_on: [postgres, redis]

  worker:
    build: .
    command: celery -A nexora_crawler.celery_app worker -Q crawl,ai,webhook,dispatcher --loglevel=info
    environment:
      - NEXORA_VECTOR_BACKEND=pgvector
      - NEXORA_DATABASE_URL=postgresql://postgres:${PG_PASSWORD}@postgres:5432/nexora
      - REDIS_URL=redis://redis:6379/0
    depends_on: [postgres, redis]

  dashboard:
    build: .
    ports: ["8501:8501"]
    command: streamlit run nexora_crawler/dashboard/app.py
    depends_on: [api]

  otel-collector:
    image: otel/opentelemetry-collector:0.96.0
    volumes: [./otel-collector-config.yaml:/etc/otelcol/config.yaml]

volumes:
  pgdata: {}
  redisdata: {}
```

### 4.2 Environment Variables (Phase 7 additions)

```bash
# Vector store — pick ONE backend (Phase 7 §3.1)
NEXORA_VECTOR_BACKEND=pgvector       # pgvector|chroma|qdrant|cloudflare_vectorize
NEXORA_DATABASE_URL=postgresql://postgres:pwd@postgres:5432/nexora

# Embedding dimensions (must match the model's output)
NEXORA_EMBEDDING_DIM=768              # nomic-embed-text: 768; OpenAI 3-small: 1536

# Schema extraction (Phase 7 §3.4)
NEXORA_SCHEMA_EXTRACTION_ENABLED=true
NEXORA_SCHEMA_EXTRACTION_MODEL=gpt-4o-mini
NEXORA_SCHEMA_CONTENT_MAX_CHARS=8000

# Webhooks (Phase 7 §3.5)
NEXORA_WEBHOOK_DEFAULT_TIMEOUT_SECONDS=15

# Quotas (Phase 7 §3.7)
NEXORA_DEFAULT_PAGES_PER_MONTH=10000
NEXORA_DEFAULT_STORAGE_GB=1
NEXORA_DEFAULT_VECTOR_RECORDS=100000
NEXORA_DEFAULT_API_RPM=60

# Observability (Phase 7 §3.8)
OTEL_EXPORTER_OTLP_ENDPOINT=localhost:4317
OTEL_SERVICE_NAME=nexora

# PII redaction (Phase 7 §3.9)
NEXORA_PII_REDACTION_ENABLED=false
NEXORA_PII_MODE=regex                # regex|llm

# OAuth (Phase 7.1 — optional)
GOOGLE_CLIENT_ID=
GOOGLE_CLIENT_SECRET=
GITHUB_CLIENT_ID=
GITHUB_CLIENT_SECRET=
OIDC_ISSUER=
OIDC_CLIENT_ID=
OIDC_CLIENT_SECRET=
```

### 4.3 Migration: ChromaDB → pgvector (one command)

```bash
# Step 1: ensure pgvector is initialized
psql $DATABASE_URL -c "CREATE EXTENSION IF NOT EXISTS vector"

# Step 2: set target backend
export NEXORA_VECTOR_BACKEND=pgvector

# Step 3: dry-run
python -m scripts.migrate_vector_store \
    --from chroma --to pgvector \
    --workspace ws-1 \
    --dry-run

# Step 4: real run
python -m scripts.migrate_vector_store \
    --from chroma --to pgvector \
    --workspace ws-1

# Step 5: cut over
# In .env: NEXORA_VECTOR_BACKEND=pgvector
# Restart API + workers. Done.

# Step 6: cleanup (after 7-day grace period)
rm -rf ./data/chroma
```

### 4.4 Test Matrix

| Test ID  | Scenario | Expected | Pass Criteria |
|----------|----------|----------|---------------|
| P7-T01   | BaseVectorStore protocol compliance | All 4 backends implement all 11 methods | `pytest` passes for each backend |
| P7-T02   | pgvector add+search round-trip | Records retrieved by similar query | top-1 hit, score > 0.85 |
| P7-T03   | Tenant isolation in vector search | ws-1 cannot see ws-2 records | Empty result, no leak |
| P7-T04   | Chroma → pgvector migration | 100% records move, ordering preserved | Identical ANN recall@k on test corpus |
| P7-T05   | Vector search service HTTP | POST /v1/search/semantic returns results | Response time < 200 ms at 100k records |
| P7-T06   | JSON Schema extraction | Schema fields populated for product page | All required fields present, types validated |
| P7-T07   | Schema extraction validation | Bad data → validation error logged | Field set to null, page kept |
| P7-T08   | Webhook create + delivery | POST /v1/webhooks + trigger | Event delivered, HMAC verified |
| P7-T09   | Webhook retry with backoff | 5xx → retry up to 5x | Counts: 1, 2, 4, 8, 16 (delays) |
| P7-T10   | Webhook HMAC signature | Invalid sig → 401 on receiver | Verifier rejects all unsigned |
| P7-T11   | JobTypeRegistry dispatch | `dispatch('index_search', ...)` returns results | Inline execution < 5s for search |
| P7-T12   | Generic /v1/jobs endpoint | POST {type: "crawl"} works | Same as Phase 4C /crawl/start |
| P7-T13   | Plugin loading via entry_points | Third-party handler registered on startup | Handler appears in /v1/jobs |
| P7-T14   | Quota enforcement (hard) | 11k pages/mo requested | 429 Retry-After |
| P7-T15   | Quota enforcement (soft) | Exceeds limit, mode=soft | Request proceeds, warning logged |
| P7-T16   | PII regex redaction | Email replaced with `[REDACTED:EMAIL]` | Original removed, count incremented |
| P7-T17   | PII LLM redaction (optional) | Names masked by LLM | Names removed, content useful |
| P7-T18   | GDPR erase | DELETE /v1/gdpr/erase | All records purged from pg, R2, vector |
| P7-T19   | OTel trace propagation | Trace spans from API → Celery → DB | Single trace_id visible in /traces |
| P7-T20   | Prometheus metrics endpoint | GET /metrics returns counters | Counters increment correctly |
| P7-T21   | OAuth Google login | Returns JWT for valid Google user | Workspace auto-provisioned |
| P7-T22   | OAuth unknown provider | Returns 404 | No security issue |
| P7-T23   | Phase 1-6 tests no regression | All 21 prior specs pass | 100% backward compat |

---

## 4.5 Performance Benchmarks

| Metric | Target | Acceptable |
|--------|--------|------------|
| Vector search latency (pgvector, 100k records, HNSW) | < 50 ms | < 200 ms |
| Vector search latency (pgvector, 1M records, HNSW) | < 200 ms | < 500 ms |
| Vector search recall@10 | > 95% | > 90% |
| Bulk add throughput (pgvector, batch 500) | 5000 rec/s | 1000 rec/s |
| Migration throughput Chroma → pgvector | 3000 rec/s | 500 rec/s |
| JSON Schema extraction latency (gpt-4o-mini) | < 3 s/page | < 8 s/page |
| JSON Schema extraction cost | $0.0002/page | < $0.001/page |
| Webhook delivery latency (p50) | < 500 ms | < 2 s |
| Webhook delivery latency (p99) | < 5 s | < 30 s |
| Quota check overhead | < 5 ms | < 20 ms |
| OTel span overhead | < 2% | < 5% |
| Prometheus scrape | < 50 ms | < 200 ms |
| OAuth callback latency | < 1 s | < 3 s |
| PII regex-only cost per page | < 1 ms | < 5 ms |
| PII LLM cost per page | $0.001 | < $0.005 |

---

## 4.6 Definition of Done

- [ ] BaseVectorStore interface defined with 11 methods
- [ ] All 4 backends implemented (pgvector, chroma, qdrant, cloudflare_vectorize)
- [ ] pgvector is the default backend; Chroma still works as a fallback
- [ ] `scripts/migrate_vector_store.py` runs successfully on a 10k-record test corpus
- [ ] Vector Search Service exposes /v1/search/semantic, /v1/search/hybrid, /v1/search/by-id/similar
- [ ] All search endpoints are tenant-scoped (no cross-tenant leakage)
- [ ] JSON Schema extraction validates against user schema before storage
- [ ] Schema extraction failures don't break the crawl pipeline
- [ ] Webhooks can be created/listed/deleted per workspace
- [ ] Webhook delivery retries with exponential backoff (5x)
- [ ] Webhook signatures are HMAC-SHA256
- [ ] JobTypeRegistry has 5 built-in handlers and supports plugin entry points
- [ ] /v1/jobs/generic accepts any registered job type
- [ ] Quotas enforce per-workspace hard limits (429 on overflow)
- [ ] OTel traces span from FastAPI → Celery → DB → external API
- [ ] /metrics exposes Prometheus-format counters and histograms
- [ ] PII regex pipeline runs in < 5 ms per page
- [ ] GDPR delete removes all data from pg, R2, and vector store
- [ ] OAuth login works for Google, GitHub, OIDC
- [ ] All 23 tests in P7 test matrix pass
- [ ] All Phase 1–6 tests still pass
- [ ] Phase 7 documented; Phase 8 entry criteria clear

---

## 5. KNOWN LIMITATIONS

| Limitation | Mitigation | Phase |
|-----------|------------|-------|
| pgvector HNSW indexes are not online-rebuildable | DROP/RECREATE in maintenance window | P8 |
| Plugin discovery requires restart of API+workers | Acceptable for self-hosted | P8 |
| OAuth requires HTTPS in production | Documented in deploy guide | Now |
| OTel trace context across Celery requires `opentelemetry-instrumentation-celery` package | Add to requirements | Now |
| Plugin authors must publish to PyPI or private index | Entry-point spec covers local `pip install -e` | Now |
| PII regex misses some patterns (international phone formats) | LLM mode for high accuracy | Now |
| Quota check requires DB hit | Cache in Redis for hot path | P8 |

---

## 6. NEXT PHASE GATE

Phase 7 is complete when:
- All 23 tests pass
- The migration tool successfully moved a real corpus between at least two backends
- The Vector Search Service survives a backend swap without any code changes
- A non-crawl job (e.g. `index_search`) succeeds end-to-end through the API
- A webhook is delivered to an external receiver with verified HMAC

Phase 8 entry criteria:
- Phase 7 deployed to production with at least 100 real workspaces
- Quota engine has been stressed and the system survived
- At least one third-party plugin has been integrated via the entry-point system

---

## 7. WHY THIS UNBLOCKS YOUR SPECIFIC PAIN

You said:

> "I migrated ChromaDB locally to Supabase but I had to do the vector search logic myself."

The reason that hurt: **the application talked to Chroma directly, so every move required rewriting the calling code.**

Phase 7 makes that impossible to repeat:

1. **The application only ever talks to `BaseVectorStore`.** Never to Chroma. Never to pgvector. Never to Qdrant. Never to Vectorize.
2. **`BaseVectorStore` has 11 methods that all real vector DBs can express.** If a backend can't, that's a backend gap, not an application limitation.
3. **`scripts/migrate_vector_store.py` handles ANY → ANY.** Move between any two of pgvector, Chroma, Qdrant, Cloudflare Vectorize with one CLI command.
4. **The Vector Search Service is a stable HTTP contract.** API version is locked. Backend can change without breaking callers.
5. **You can now host on Supabase pgvector for free** (500 MB free Postgres) and migrate to Neon or RDS in 5 minutes if you outgrow it.

You will not write a vector search function by hand again.

---

## 8. SHIPPING: PHASE 7 IMPLEMENTATION ORDER

If you want to ship Phase 7 in 2 weeks instead of 6:

**Week 1:**
- Day 1: BaseVectorStore interface + pgvector backend
- Day 2: Vector Search Service HTTP endpoints
- Day 3: Migration script + Chroma backend (legacy compat)
- Day 4: JobTypeRegistry + generic /v1/jobs
- Day 5: Quotas + PII redaction (regex only)

**Week 2:**
- Day 6: Webhooks
- Day 7: OTel + /metrics
- Day 8: JSON Schema extraction
- Day 9: PII LLM mode + GDPR endpoint
- Day 10: OAuth + tests + docs

This order is **dependency-driven**: nothing in week 2 depends on OAuth. If you have to cut something, OAuth is the cleanest cut (Phase 7.1 can wait).
 ::




 Let me read your current implementation before I answer.


Thought 1 time(s), Viewed 1 file(s)
OK — now I have the full picture. Your "current implementation" is Phase 4A spec — you're about to start building it. The actual working code is just Phase 3 (18/18 tests).

Let me give you the honest, decisive answer.

Solid Conclusion
Where you actually are
State
Phase 3 (export / SSRF / idempotency)	✅ Implemented + tested
Phase 4A (multi-format, metadata store)	📋 Spec written, about to implement
Phases 4B → 6	📋 Spec written, not started
Phase 7	📋 Spec written, not started
What Phase 7 touches in your code
I went through the Phase 4A spec and the Phase 7 spec line-by-line. Here's the actual touch surface:

Phase 4A file	Phase 7 impact	Why
metadata_indexer.py	Parallel run — Phase 7 adds vector_indexer.py alongside it	Same DB, different tables
local_sqlite.py (pages table)	Schema extension — add vector_records table OR migrate to libSQL+pgvector	One row in _init_schema(), or one migration script
items.py (ai_embedding field)	Read-only — Phase 7 reads it, doesn't write	Phase 4B already populates it
MarkdownExtractionPipeline	Untouched	Independent
MultimodalAssetExtractor	Untouched	Independent
UnifiedSchemaEnricher	Untouched	PII redaction runs BEFORE it, doesn't change it
ParquetExportPipeline	Untouched	Independent
NexoraPageItem	Untouched	Existing fields are sufficient
settings.py (pipeline priorities)	Additive — new lines for Phase 7 pipelines at priorities 200 (PII), 280 (schema extract), 290 (vector index)	Doesn't reorder existing
Net effect on Phase 4A: minimal. Phase 7 is mostly additive. The single biggest change is swapping MetadataStore (SQLite) for a Postgres + pgvector store so vectors and metadata live in one DB. That swap is mandatory for Phase 7 anyway.

Should you do Phase 7 before Phase 6? → Yes, in pieces
Here's the dependency graph I worked out:

Phase 7 component	Independent?	What it actually needs
§3.1 BaseVectorStore interface	✅ Fully standalone	Just Python types and ABC
§3.2 pgvector backend	⚠️ Needs Phase 4A's pages table	Postgres + the pages schema you just wrote
§3.3 Vector Search Service	⚠️ Needs Phase 4C FastAPI host	Once 4C exists, drop it in
§3.7 Migration tool	✅ Fully standalone	CLI script, runs once
§3.4 JSON Schema extraction	⚠️ Needs markdown field (Phase 4A)	MarkdownExtractionPipeline output
§3.5 Webhooks	❌ Needs Phase 4C API + Phase 5 worker	Celery harness
§3.6 JobTypeRegistry	❌ Needs Phase 5 worker harness	Celery
§3.7 Quota engine	⚠️ Needs Phase 4C workspaces table	Auth context
§3.8 OpenTelemetry	✅ Universal	Lightweight wrap
§3.9 PII redaction	⚠️ Needs markdown (Phase 4A)	Runs in pipeline
§3.10 OAuth	❌ Needs Phase 4C auth	4C JWT layer
What's actually strategic-priority-piece-of-Phase-7
§3.1 + §3.2 + §3.7 = the "no-more-migration-pain" foundation. Total = ~530 lines.

§3.1 BaseVectorStore — 200 lines of pure Python ABC
§3.2 PgVectorStore — 250 lines, runs against a Postgres
§3.7 Migration script — 80 lines, ANY → ANY vector backend
None of this needs Phase 4B or 4C. It needs Phase 4A's pages table. That's it.

The revised build order (my recommendation)
text

Copy
DAY  1-2   Phase 4A: MetadataStore + MarkdownExtractionPipeline + schema_enricher

                  + items.py + settings.py + P4A-T01 to T12 tests passing

            

DAY  3-4   Phase 7 §3.1 BaseVectorStore interface ← can run today, no deps

            Phase 7 §3.2 PgVectorStore against Phase 4A's pages table

            Phase 7 §3.7 Migration tool + dry-run on test corpus

            

DAY  5-8   Phase 4B: embeddings, AI enrichment

                  (NOW flows into BaseVectorStore.add() instead of Chroma directly

                   — your migration-tax prevention ACTIVE here)

            

DAY  9-12  Phase 4C: FastAPI, JWT, /v1/search/semantic endpoint

            Phase 7 §3.3 Vector Search Service HTTP

            

DAY 13-17  Phase 5: Celery + workers + dashboard

            Phase 7 §3.5 webhooks + §3.6 JobTypeRegistry + §3.8 OTel

            

DAY 18-20  Phase 7 §3.4 JSON Schema extraction (Firecrawl killer feature)

                  §3.7 quotas

                  §3.9 PII redaction

                  

DAY 21-25  Phase 7 §3.10 OAuth (optional add-on, can ship as v7.1)

            

DAY 26-32  Phase 6: Tauri desktop, packaging, installer

            (lowest leverage per line — do it last)
Total: ~5 weeks, but Phase 7's strategic value lands at end of week 1, not end of month 2. Day 4 you can already demo "migrate vectors between backends without rewriting search code."

Three concrete things to do today
1.
Pull Phase 7 §3.1 to your editor. 200 lines of pure Python ABC. No deps. Land it today.
2.
Write the Postgres + pgvector migration story on paper now. Document the swap from MetadataStore(SQLite) → MetadataStore(Postgres+pgvector). This decides whether Turso free tier or Supabase free tier or Neon — your call.
3.
Don't touch Phase 6 yet. Save it for last. It's the longest phase with the least strategic density (most of it is UI plumbing in Tauri/Streamlit).
The one thing I'd push back on
"then phase 7 is where the fun is?"

Yeah, mostly. But the fun actually starts at §3.1, which you can do today. Don't wait until "after Phase 6" to write the vector store interface — by then you'll have written Chroma glue code three more times and you'll have to refactor it out.

The shortest path to proving your migration-pain cure is real: start Phase 7 §3.1 today, on top of Phase 3's existing test suite, before Phase 4A even exists. It's pure Python — no DB, no Scrapy, no FastAPI. Just write the interface, the VectorRecord / SearchQuery / SearchResult types, and a stub BaseVectorStore with NotImplementedError. Then write the pgvector implementation against a test Postgres. You'll have a working vector abstraction by Friday — before you've even started Phase 4A's storage layer.

Want me to write those 200 lines right now? They'd land as nexora_crawler/vector_store/base.py with full tests for the interface contract. Then you can implement Phase 4A and have the vector contract waiting for it.
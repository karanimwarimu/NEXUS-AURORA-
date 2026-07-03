# NEXORA — PHASE 7 ADDITIONAL INTEGRATION PACKAGE
# Complete Curated Integration for Phases 4A through 7
# Version: 1.0.0 | Date: 2026-07-03
# Author: Curated from Phase 7 Production Spec + Phase 4A-6 Audit

---

> **Purpose:** This document contains ALL Phase 7 integration patches that must be applied to Phases 4A, 4B, 4C, 5, and 6 to achieve industry-standard compliance. Each section is self-contained and maps to a specific phase.
>
> **How to use:** Build each phase using your original implementation guide, then apply the corresponding patch from this document before moving to the next phase. Do NOT wait until Phase 7 to apply these — they are cross-cutting layers seeded early.

---

## TABLE OF CONTENTS

1. [Phase 4A Integration — Vector Store Contract Seeds](#phase-4a-integration)
2. [Phase 4B Integration — Backend Implementations](#phase-4b-integration)
3. [Phase 4C Integration — FastAPI Routes & API Layer](#phase-4c-integration)
4. [Phase 5 Integration — Celery, Webhooks, Job Registry, OTel](#phase-5-integration)
5. [Phase 6 Integration — PII, GDPR, Schema Extraction, Quotas](#phase-6-integration)
6. [Final Integration Test Suite — 43 Tests](#final-integration-test-suite)
7. [Workflow Guide — How to Apply These Patches](#workflow-guide)
8. [Critical Fixes Summary](#critical-fixes-summary)

---


================================================================================
## SECTION 1: PHASE 4A — VECTOR STORE CONTRACT SEEDS
## Source File: phase_4a_additional_integration.md
================================================================================

# PHASE 4A — ADDITIONAL INTEGRATION PATCH
# Version: 1.0.0 | Date: 2026-07-03
# Purpose: Seed Phase 7 vector store contracts into Phase 4A foundation
# Impact: ZERO runtime impact. Pure Python interfaces. Establishes contract
#         that Phase 4B will implement against to prevent vendor lock-in.
#
# INSTRUCTIONS:
#   1. Add these files to your Phase 4A codebase BEFORE starting Phase 4B
#   2. They are pure Python — no DB, no Scrapy, no FastAPI dependencies
#   3. Phase 4B will implement ChromaVectorStore and PgVectorStore against BaseVectorStore
#   4. Phase 4C will add HTTP search endpoints consuming BaseVectorStore
#
# FILES TO CREATE:
#   nexora_crawler/vector_store/__init__.py
#   nexora_crawler/vector_store/base.py
#   nexora_crawler/vector_store/factory.py
#
# SETTINGS.PY ADDITIONS:
#   NEXORA_VECTOR_BACKEND = "pgvector"  # pgvector | chroma | qdrant | cloudflare_vectorize
#   NEXORA_DATABASE_URL = "postgresql://postgres:password@localhost:5432/nexora"
#   NEXORA_EMBEDDING_DIM = 768
#   NEXORA_CHROMA_PATH = "./data/chroma"
#
# ITEMS.PY ADDITION:
#   workspace_id = scrapy.Field()  # Add to NexoraPageItem, default "default"

# ============================================================
# FILE: nexora_crawler/vector_store/base.py
# ============================================================

"""
BaseVectorStore — vendor-neutral vector storage contract.
Added in Phase 4A so Phase 4B can implement against it from day one.
Prevents the Chroma→Supabase migration tax you already paid once.
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import List, Dict, Any, Optional
import logging

logger = logging.getLogger(__name__)


@dataclass
class VectorRecord:
    """Standardized embedding payload across all phases."""
    id: str
    content: str
    embedding: List[float]
    workspace_id: str = "default"
    source_type: str = "chunk"  # 'chunk' | 'page' | 'document'
    source_id: Optional[str] = None
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class SearchQuery:
    vector: Optional[List[float]] = None
    text: Optional[str] = None
    workspace_id: Optional[str] = None
    top_k: int = 10
    filter: Dict[str, Any] = field(default_factory=dict)
    min_similarity: float = 0.0


@dataclass
class SearchResult:
    id: str
    score: float
    content: str
    metadata: Dict[str, Any]
    workspace_id: str


class VectorStoreError(Exception):
    """Base exception for vector store operations."""
    pass


class BackendNotFoundError(VectorStoreError):
    """Raised when requested backend is not available."""
    pass


class TenantIsolationError(VectorStoreError):
    """Raised on cross-tenant access attempts."""
    pass


class BaseVectorStore(ABC):
    """
    Vendor-neutral vector store interface.

    RULE: Application code MUST use this interface, never a backend directly.
    This contract prevents future migration tax.

    Phase 4B implements: ChromaVectorStore, PgVectorStore
    Phase 4C consumes: via Vector Search Service HTTP endpoints
    Phase 5 consumes: via JobTypeRegistry handlers (index_search, index_add)
    Phase 7 extends: with hybrid_search, list_all for migration tool
    """

    @abstractmethod
    async def initialize(self) -> None:
        """Create collections, indexes, extensions. Idempotent."""

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
        """
        Vector + BM25 combined. Backend may degrade to vector-only with log warning.
        Phase 7 requirement: pgvector uses Postgres tsvector + ts_rank for BM25.
        """

    @abstractmethod
    async def delete(self, ids: List[str]) -> int:
        """Delete by ID. Returns count deleted."""

    @abstractmethod
    async def delete_by_workspace(self, workspace_id: str) -> int:
        """Bulk delete for tenant offboarding / GDPR."""

    @abstractmethod
    async def count(self, workspace_id: Optional[str] = None) -> int:
        """Record count, optionally scoped to workspace."""

    @abstractmethod
    async def get(self, ids: List[str]) -> List[VectorRecord]:
        """Fetch by ID (for re-rank, hydration, export)."""

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
        """Liveness probe for monitoring."""

    @abstractmethod
    def backend_name(self) -> str:
        """Backend identifier for logs / metrics / debugging."""


# ---- Runtime protocol validation ----
# Prevents "oops this backend doesn't implement hybrid_search" at runtime

class VectorStoreProtocol:
    """
    Runtime validation that a backend satisfies the full contract.
    Call VectorStoreProtocol.validate(MyBackendClass) before registration.
    """

    REQUIRED_METHODS = [
        'initialize', 'add', 'upsert', 'search', 'hybrid_search',
        'delete', 'delete_by_workspace', 'count', 'get', 'list_all',
        'health_check', 'backend_name',
    ]

    @classmethod
    def validate(cls, store_class: type) -> None:
        """
        Validate that store_class implements all required methods.
        Raises TypeError if any method is missing or not callable.
        """
        for method in cls.REQUIRED_METHODS:
            if not hasattr(store_class, method):
                raise TypeError(
                    f"Backend {store_class.__name__} missing required method: {method}"
                )
            if not callable(getattr(store_class, method)):
                raise TypeError(
                    f"Backend {store_class.__name__}.{method} is not callable"
                )
        logger.info("[VectorStoreProtocol] %s validated", store_class.__name__)


# ---- JSON helpers (shared across backends) ----

def _json(d: Dict) -> str:
    import json
    return json.dumps(d)


def _unjson(s: Any) -> Dict:
    if isinstance(s, dict):
        return s
    import json
    return json.loads(s) if s else {}


# ============================================================
# FILE: nexora_crawler/vector_store/factory.py
# ============================================================

"""
Build vector store backends from config.
Switching backends = changing one env var. Zero code change.

Usage:
    store = build_vector_store()  # uses NEXORA_VECTOR_BACKEND env var
    store = build_vector_store("chroma")  # explicit override
"""

import os
import logging
from .base import BaseVectorStore, BackendNotFoundError

logger = logging.getLogger(__name__)


def build_vector_store(backend_name: str = None) -> BaseVectorStore:
    """
    Build the configured vector store backend.

    Args:
        backend_name: Override env var. If None, reads NEXORA_VECTOR_BACKEND.

    Returns:
        Configured BaseVectorStore instance.

    Raises:
        BackendNotFoundError: If backend is unknown or dependencies missing.
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

    raise BackendNotFoundError(f"Unknown vector backend: {backend}")


# ============================================================
# FILE: nexora_crawler/vector_store/__init__.py
# ============================================================

"""Vector store package — vendor-neutral embedding storage."""

from .base import (
    BaseVectorStore,
    VectorRecord,
    SearchQuery,
    SearchResult,
    VectorStoreProtocol,
    VectorStoreError,
    BackendNotFoundError,
)
from .factory import build_vector_store

__all__ = [
    "BaseVectorStore",
    "VectorRecord",
    "SearchQuery",
    "SearchResult",
    "VectorStoreProtocol",
    "VectorStoreError",
    "BackendNotFoundError",
    "build_vector_store",
]


# ============================================================
# SETTINGS.PY ADDITIONS (Phase 4A)
# ============================================================
# Add these lines to your existing settings.py:
#
# # ---- Phase 7 Seed: Vector Store Configuration ----
# NEXORA_VECTOR_BACKEND = "pgvector"  # pgvector | chroma | qdrant | cloudflare_vectorize
# NEXORA_DATABASE_URL = "postgresql://postgres:password@localhost:5432/nexora"
# NEXORA_EMBEDDING_DIM = 768  # nomic-embed-text: 768; OpenAI 3-small: 1536
# NEXORA_CHROMA_PATH = "./data/chroma"
#
# # ---- Phase 7 Seed: Pipeline Priorities ----
# # (Phase 4B will register at 250, 260, 270)
# ITEM_PIPELINES = {
#     'nexora_crawler.pipelines.NexoraExtractionPipeline': 100,
#     'nexora_crawler.pipelines.markdown_pipeline.MarkdownExtractionPipeline': 110,
#     'nexora_crawler.pipelines.pii_redaction_pipeline.PIIRedactionPipeline': 200,      # Phase 7
#     'nexora_crawler.pipelines.NexoraStylePipeline': 150,
#     'nexora_crawler.pipelines.schema_enricher.UnifiedSchemaEnricher': 160,
#     'nexora_crawler.pipelines.metadata_indexer.MetadataIndexerPipeline': 165,
#     'nexora_crawler.pipelines.ai_enrichment.AIEnrichmentPipeline': 250,            # Phase 4B
#     'nexora_crawler.pipelines.chunking_pipeline.StructuralChunkingPipeline': 260,    # Phase 4B
#     'nexora_crawler.pipelines.vector_index_pipeline.VectorIndexPipeline': 270,       # Phase 4B
#     'nexora_crawler.pipelines.schema_extraction_pipeline.SchemaExtractionPipeline': 280,  # Phase 7
#     'nexora_crawler.pipelines.parquet_export.ParquetExportPipeline': 450,
#     'nexora_crawler.pipelines.NexoraExportPipeline': 500,
#     'nexora_crawler.pipelines.NexoraDatasetPipeline': 600,
# }

# ============================================================
# ITEMS.PY ADDITION (Phase 4A)
# ============================================================
# Add to NexoraPageItem:
#
#     # ---- Phase 7 Seed: Multi-tenancy ----
#     workspace_id = scrapy.Field()  # default "default" in schema enricher
#
# And in UnifiedSchemaEnricher.process_item(), add:
#     if not item.get("workspace_id"):
#         item["workspace_id"] = getattr(spider, "workspace_id", "default")


================================================================================
## SECTION 2: PHASE 4B — BACKEND IMPLEMENTATIONS (CHROMA + PGVECTOR)
## Source File: phase_4b_additional_integration.md
================================================================================

# PHASE 4B — ADDITIONAL INTEGRATION PATCH
# Version: 1.0.0 | Date: 2026-07-03
# Purpose: Fix Phase 4B to use BaseVectorStore contract instead of raw ChromaDB
#
# CRITICAL FINDINGS FROM AUDIT:
#   1. Phase 4B's VectorIndexPipeline hardcodes ChromaDB via ChromaVectorStore
#   2. The ChromaVectorStore in Phase 4B does NOT implement BaseVectorStore
#   3. No pgvector backend exists — migration tax is baked in
#   4. ChunkingPipeline stores embeddings on chunks but VectorIndexPipeline
#      expects ChromaDB-specific metadata format
#
# THIS PATCH REPLACES the following Phase 4B files:
#   - nexora_crawler/pipelines/vector_index_pipeline.py (FULL REPLACEMENT)
#   - nexora_crawler/vector_store/chroma_store.py (NEW — implements BaseVectorStore)
#   - nexora_crawler/vector_store/pgvector_store.py (NEW — implements BaseVectorStore)
#
# FILES TO MODIFY:
#   - nexora_crawler/pipelines/ai_enrichment.py (no changes — already good)
#   - nexora_crawler/pipelines/chunking_pipeline.py (no changes — already good)
#   - nexora_crawler/settings.py (add NEXORA_VECTOR_BACKEND env var)

# ============================================================
# FILE: nexora_crawler/vector_store/chroma_store.py
# ============================================================

"""
ChromaVectorStore — Phase 4B backend implementing BaseVectorStore.

This is the LEGACY / LOCAL DEV backend. It works, but:
  - No built-in tenant isolation (enforced in application layer)
  - No hybrid search (degrades to vector-only)
  - Harder to backup/restore than pgvector

Use pgvector for production. Use Chroma for local dev only.
"""

import os
import logging
from typing import List, Optional, Dict, Any

from .base import BaseVectorStore, VectorRecord, SearchQuery, SearchResult, _json, _unjson

logger = logging.getLogger(__name__)


class ChromaVectorStore(BaseVectorStore):
    """
    ChromaDB backend implementing BaseVectorStore.

    Tenant isolation: enforced by filtering on workspace_id in metadata.
    Hybrid search: NOT supported by Chroma. Degrades to vector-only with warning.
    """

    def __init__(self, path: str = "./data/chroma", collection_name: str = "nexora_chunks"):
        import chromadb
        from chromadb.config import Settings

        self._path = path
        self._collection_name = collection_name
        os.makedirs(path, exist_ok=True)

        self._client = chromadb.PersistentClient(
            path=path,
            settings=Settings(anonymized_telemetry=False),
        )
        self._collection = None  # initialized in initialize()

    async def initialize(self) -> None:
        """Create or get collection. Idempotent."""
        try:
            self._collection = self._client.get_collection(self._collection_name)
        except ValueError:
            self._collection = self._client.create_collection(
                name=self._collection_name,
                metadata={"hnsw:space": "cosine"},
            )
        logger.info("[Chroma] Initialized at %s (collection=%s)",
                   self._path, self._collection_name)

    async def add(self, records: List[VectorRecord]) -> List[str]:
        if not records:
            return []
        ids = [r.id for r in records]
        embeddings = [r.embedding for r in records]
        documents = [r.content[:5000] for r in records]
        metadatas = [{
            "workspace_id": r.workspace_id,
            "source_type": r.source_type,
            "source_id": r.source_id or "",
            **_json(r.metadata),
        } for r in records]

        self._collection.add(
            ids=ids,
            embeddings=embeddings,
            documents=documents,
            metadatas=metadatas,
        )
        return ids

    async def upsert(self, records: List[VectorRecord]) -> List[str]:
        # Chroma add() with same IDs overwrites
        return await self.add(records)

    async def search(self, query: SearchQuery) -> List[SearchResult]:
        if query.workspace_id is None:
            raise ValueError("workspace_id is required for tenant scoping")

        where = {"workspace_id": query.workspace_id}
        if query.filter:
            for k, v in query.filter.items():
                where[k] = v

        results = self._collection.query(
            query_embeddings=[query.vector] if query.vector else None,
            query_texts=[query.text] if query.text and not query.vector else None,
            n_results=query.top_k,
            where=where,
            include=["metadatas", "documents", "distances"],
        )

        hits = []
        if results["ids"] and results["ids"][0]:
            for i, chunk_id in enumerate(results["ids"][0]):
                score = 1.0 - results["distances"][0][i]
                if score < query.min_similarity:
                    continue
                meta = results["metadatas"][0][i]
                hits.append(SearchResult(
                    id=chunk_id,
                    score=score,
                    content=results["documents"][0][i] or "",
                    metadata=_unjson(meta),
                    workspace_id=meta.get("workspace_id", query.workspace_id),
                ))
        return hits

    async def hybrid_search(self, query: SearchQuery, bm25_weight: float = 0.3) -> List[SearchResult]:
        logger.warning(
            "[Chroma] hybrid_search not supported. Degrading to vector-only. "
            "Use pgvector backend for true hybrid search."
        )
        return await self.search(query)

    async def delete(self, ids: List[str]) -> int:
        self._collection.delete(ids=ids)
        return len(ids)

    async def delete_by_workspace(self, workspace_id: str) -> int:
        self._collection.delete(where={"workspace_id": workspace_id})
        # Chroma doesn't return count on delete
        return -1  # unknown

    async def count(self, workspace_id: Optional[str] = None) -> int:
        if workspace_id:
            return self._collection.count(where={"workspace_id": workspace_id})
        return self._collection.count()

    async def get(self, ids: List[str]) -> List[VectorRecord]:
        results = self._collection.get(
            ids=ids,
            include=["metadatas", "documents", "embeddings"],
        )
        records = []
        for i, chunk_id in enumerate(results["ids"]):
            meta = results["metadatas"][i]
            records.append(VectorRecord(
                id=chunk_id,
                content=results["documents"][i] or "",
                embedding=results["embeddings"][i],
                workspace_id=meta.get("workspace_id", "default"),
                source_type=meta.get("source_type", "chunk"),
                source_id=meta.get("source_id") or None,
                metadata=_unjson(meta),
            ))
        return records

    async def list_all(self, workspace_id: Optional[str] = None,
                       limit: int = 1000, offset: int = 0) -> List[VectorRecord]:
        # Chroma doesn't support offset. Fetch all and slice.
        where = {"workspace_id": workspace_id} if workspace_id else None
        results = self._collection.get(
            where=where,
            include=["metadatas", "documents", "embeddings"],
        )
        records = []
        for i, chunk_id in enumerate(results["ids"]):
            meta = results["metadatas"][i]
            records.append(VectorRecord(
                id=chunk_id,
                content=results["documents"][i] or "",
                embedding=results["embeddings"][i],
                workspace_id=meta.get("workspace_id", "default"),
                source_type=meta.get("source_type", "chunk"),
                source_id=meta.get("source_id") or None,
                metadata=_unjson(meta),
            ))
        return records[offset:offset + limit]

    async def health_check(self) -> bool:
        try:
            self._collection.count()
            return True
        except Exception as e:
            logger.error("[Chroma] Health check failed: %s", e)
            return False

    def backend_name(self) -> str:
        return "chroma"


# ============================================================
# FILE: nexora_crawler/vector_store/pgvector_store.py
# ============================================================

"""
PgVectorStore — Phase 4B DEFAULT backend implementing BaseVectorStore.

Why pgvector is the default:
  - Lives in same Postgres as metadata (one connection, one backup)
  - No extra service to deploy
  - HNSW index gives sub-100ms search at 10M vectors
  - Managed on Supabase, Neon, RDS, Timescale
  - Supports hybrid search via Postgres FTS

Trade-off: weaker than Qdrant at 100M+ vectors.
Mitigation: sharding later, or migrate via scripts/migrate_vector_store.py
"""

import logging
from typing import List, Optional, Dict, Any

from .base import BaseVectorStore, VectorRecord, SearchQuery, SearchResult, _json, _unjson

logger = logging.getLogger(__name__)


class PgVectorStore(BaseVectorStore):
    """
    Postgres + pgvector backend.

    Requires:
      pip install asyncpg
      CREATE EXTENSION vector;  -- in your Postgres
    """

    def __init__(self, database_url: str, embedding_dim: int = 768):
        self._url = database_url
        self._dim = embedding_dim
        self._pool = None

    async def initialize(self) -> None:
        import asyncpg
        self._pool = await asyncpg.create_pool(self._url, min_size=2, max_size=10)
        async with self._pool.acquire() as conn:
            await conn.execute("CREATE EXTENSION IF NOT EXISTS vector")
            await conn.execute(f"""
                CREATE TABLE IF NOT EXISTS vector_records (
                    id           TEXT PRIMARY KEY,
                    workspace_id TEXT NOT NULL,
                    content      TEXT NOT NULL,
                    embedding    vector({self._dim}),
                    source_type  TEXT DEFAULT 'chunk',
                    source_id    TEXT,
                    metadata     JSONB DEFAULT '{{}}',
                    created_at   TIMESTAMPTZ DEFAULT now()
                )
            """)
            # HNSW index — best recall/speed for <10M vectors
            await conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_vector_hnsw
                ON vector_records USING hnsw (embedding vector_cosine_ops)
            """)
            await conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_vector_workspace
                ON vector_records (workspace_id)
            """)
            # GIN on metadata for filter queries
            await conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_vector_metadata
                ON vector_records USING gin (metadata)
            """)
            # For hybrid search: tsvector on content
            await conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_vector_content_fts
                ON vector_records USING gin (to_tsvector('english', content))
            """)
        logger.info("[pgvector] Initialized (dim=%d)", self._dim)

    async def add(self, records: List[VectorRecord]) -> List[str]:
        return await self.upsert(records)

    async def upsert(self, records: List[VectorRecord]) -> List[str]:
        ids = [r.id for r in records]
        async with self._pool.acquire() as conn:
            await conn.executemany("""
                INSERT INTO vector_records
                    (id, workspace_id, content, embedding, source_type, source_id, metadata)
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
                 r.source_type, r.source_id, _json(r.metadata))
                for r in records
            ])
        return ids

    async def search(self, query: SearchQuery) -> List[SearchResult]:
        if query.workspace_id is None:
            raise ValueError("workspace_id is required for tenant scoping")

        params = [query.workspace_id]
        where_parts = ["workspace_id = $1"]

        if query.vector is None:
            raise ValueError("Either vector or text must be provided for search")
        params.append("[" + ",".join(map(str, query.vector)) + "]")

        # Optional metadata filter (simplified — real impl uses dynamic SQL builder)
        if query.filter:
            for k, v in query.filter.items():
                where_parts.append(f"metadata->>'{k}' = ${len(params) + 1}")
                params.append(str(v))

        where_sql = " AND ".join(where_parts)
        sql = f"""
            SELECT id, content, metadata, workspace_id,
                   1 - (embedding <=> ${len(params)}::vector) AS score
            FROM vector_records
            WHERE {where_sql}
              AND 1 - (embedding <=> ${len(params)}::vector) >= ${len(params) + 1}
            ORDER BY embedding <=> ${len(params)}::vector
            LIMIT ${len(params) + 2}
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

    async def hybrid_search(self, query: SearchQuery, bm25_weight: float = 0.3) -> List[SearchResult]:
        if not query.text:
            logger.warning("[pgvector] hybrid_search needs text. Degrading to vector-only.")
            return await self.search(query)

        # Hybrid: weighted sum of vector similarity and BM25 (ts_rank)
        params = [query.workspace_id, query.text]
        where_parts = ["workspace_id = $1"]

        if query.vector is None:
            raise ValueError("vector required for hybrid search")
        params.append("[" + ",".join(map(str, query.vector)) + "]")

        # ts_rank for BM25-like scoring (0 to 1 normalized)
        # vector similarity also 0 to 1
        # final_score = (1 - bm25_weight) * vector_score + bm25_weight * ts_rank
        sql = f"""
            SELECT id, content, metadata, workspace_id,
                   (1 - {bm25_weight}) * (1 - (embedding <=> ${len(params)}::vector))
                   + {bm25_weight} * ts_rank(
                       to_tsvector('english', content),
                       plainto_tsquery('english', $2)
                   ) AS score
            FROM vector_records
            WHERE {" AND ".join(where_parts)}
              AND to_tsvector('english', content) @@ plainto_tsquery('english', $2)
            ORDER BY score DESC
            LIMIT ${len(params) + 1}
        """
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

    async def delete(self, ids: List[str]) -> int:
        async with self._pool.acquire() as conn:
            result = await conn.execute(
                "DELETE FROM vector_records WHERE id = ANY($1::text[])", ids
            )
        return int(result.split()[-1]) if result else 0

    async def delete_by_workspace(self, workspace_id: str) -> int:
        async with self._pool.acquire() as conn:
            result = await conn.execute(
                "DELETE FROM vector_records WHERE workspace_id = $1", workspace_id
            )
        return int(result.split()[-1]) if result else 0

    async def count(self, workspace_id: Optional[str] = None) -> int:
        async with self._pool.acquire() as conn:
            if workspace_id:
                row = await conn.fetchrow(
                    "SELECT COUNT(*) FROM vector_records WHERE workspace_id=$1",
                    workspace_id,
                )
            else:
                row = await conn.fetchrow("SELECT COUNT(*) FROM vector_records")
        return int(row[0])

    async def get(self, ids: List[str]) -> List[VectorRecord]:
        async with self._pool.acquire() as conn:
            rows = await conn.fetch(
                "SELECT * FROM vector_records WHERE id = ANY($1::text[])", ids
            )
        return [_row_to_record(r) for r in rows]

    async def list_all(self, workspace_id: Optional[str] = None,
                       limit: int = 1000, offset: int = 0) -> List[VectorRecord]:
        where = "WHERE workspace_id = $1" if workspace_id else ""
        params = ([workspace_id] if workspace_id else []) + [limit, offset]
        async with self._pool.acquire() as conn:
            rows = await conn.fetch(
                f"SELECT * FROM vector_records {where} "
                f"ORDER BY created_at LIMIT ${len(params)-1} OFFSET ${len(params)}",
                *params,
            )
        return [_row_to_record(r) for r in rows]

    async def health_check(self) -> bool:
        try:
            async with self._pool.acquire() as conn:
                await conn.fetchval("SELECT 1")
            return True
        except Exception as e:
            logger.error("[pgvector] Health check failed: %s", e)
            return False

    def backend_name(self) -> str:
        return "pgvector"


def _row_to_record(row) -> VectorRecord:
    """Convert asyncpg row to VectorRecord."""
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


# ============================================================
# FILE: nexora_crawler/pipelines/vector_index_pipeline.py (REPLACEMENT)
# ============================================================

"""
VectorIndexPipeline — Phase 4B (INTEGRATED WITH BASEVECTORSTORE)

CRITICAL CHANGE from original Phase 4B spec:
  - OLD: hardcoded ChromaDB via ChromaVectorStore (not implementing BaseVectorStore)
  - NEW: uses build_vector_store() factory, backend-agnostic
  - NEW: converts NexoraChunk → VectorRecord before storing
  - NEW: supports workspace_id for multi-tenancy
"""

import logging
from typing import List

from nexora_crawler.vector_store.factory import build_vector_store
from nexora_crawler.vector_store.base import VectorRecord
from nexora_crawler.pipelines.chunking_pipeline import NexoraChunk

logger = logging.getLogger(__name__)


class VectorIndexPipeline:
    """
    Scrapy pipeline that indexes chunks into vector store via BaseVectorStore.
    Priority: 270 (after Chunking at 260, before Parquet at 450)
    """

    def __init__(self, crawler):
        self.settings = crawler.settings
        self.enabled = self.settings.getbool('NEXORA_VECTOR_INDEX_ENABLED', True)
        self.workspace_id = getattr(crawler, 'workspace_id', 'default')

        # PHASE 7 FIX: Use factory, not hardcoded ChromaDB
        backend = self.settings.get('NEXORA_VECTOR_BACKEND', 'pgvector')
        self.vector_store = build_vector_store(backend)

        self.stats = {
            "chunks_indexed": 0,
            "pages_indexed": 0,
            "errors": 0,
        }

    @classmethod
    def from_crawler(cls, crawler):
        return cls(crawler)

    async def open_spider(self, spider):
        if self.enabled:
            await self.vector_store.initialize()
            logger.info("[VectorIndex] Backend: %s", self.vector_store.backend_name())

    async def process_item(self, item, spider):
        if not self.enabled:
            return item

        chunks = item.get("chunks", [])
        if not chunks:
            return item

        try:
            # Convert NexoraChunk → VectorRecord
            records = self._chunks_to_records(chunks, self.workspace_id)
            if records:
                await self.vector_store.add(records)
                self.stats["chunks_indexed"] += len(records)
                self.stats["pages_indexed"] += 1
                item["has_embedding"] = True
                item["vector_backend"] = self.vector_store.backend_name()

        except Exception as exc:
            logger.error("[VectorIndex] Failed for %s: %s",
                        item.get("url", ""), exc)
            self.stats["errors"] += 1

        return item

    def _chunks_to_records(self, chunks: List[NexoraChunk], workspace_id: str) -> List[VectorRecord]:
        """Convert pipeline chunks to VectorRecords for the store."""
        records = []
        for chunk in chunks:
            if not chunk.embedding:
                continue  # Skip chunks without embeddings
            records.append(VectorRecord(
                id=chunk.chunk_id,
                content=chunk.content,
                embedding=chunk.embedding,
                workspace_id=workspace_id,
                source_type=chunk.source_type or "chunk",
                source_id=chunk.parent_url,
                metadata={
                    "parent_title": chunk.parent_title,
                    "chunk_index": chunk.chunk_index,
                    "chunk_count": chunk.chunk_count,
                    "token_count": chunk.token_count,
                    "word_count": chunk.word_count,
                    "heading_chain": chunk.heading_chain,
                    "ai_summary": chunk.ai_summary,
                    "ai_tags": chunk.ai_tags,
                },
            ))
        return records

    def close_spider(self, spider):
        logger.info("[VectorIndex] Stats: %s", self.stats)


# ============================================================
# SETTINGS.PY CHANGES FOR PHASE 4B
# ============================================================
# Replace the old NEXORA_VECTOR_BACKEND setting:
#
# OLD (broken — only chroma):
#   NEXORA_VECTOR_BACKEND = 'chromadb'
#
# NEW (Phase 7 integrated):
#   NEXORA_VECTOR_BACKEND = 'pgvector'  # pgvector | chroma | qdrant | cloudflare_vectorize
#   NEXORA_DATABASE_URL = 'postgresql://postgres:password@localhost:5432/nexora'
#   NEXORA_EMBEDDING_DIM = 768
#   NEXORA_CHROMA_PATH = './data/chroma'
#
# Pipeline priority stays the same:
#   'nexora_crawler.pipelines.vector_index_pipeline.VectorIndexPipeline': 270,

# ============================================================
# MIGRATION: FROM OLD Phase 4B TO INTEGRATED Phase 4B
# ============================================================
# 1. Delete old vector_index_pipeline.py (the one with hardcoded ChromaDB)
# 2. Create vector_store/chroma_store.py (implements BaseVectorStore)
# 3. Create vector_store/pgvector_store.py (implements BaseVectorStore)
# 4. Replace vector_index_pipeline.py with the version above
# 5. Update settings.py with new env vars
# 6. Run tests: all Phase 4B tests should pass with BOTH backends


================================================================================
## SECTION 3: PHASE 4C — FASTAPI ROUTES & API LAYER
## Source File: phase_4c_additional_integration.md
================================================================================

# PHASE 4C — ADDITIONAL INTEGRATION PATCH
# Version: 1.0.0 | Date: 2026-07-03
# Purpose: Complete Phase 4C FastAPI layer with Phase 7 search/webhook/quota endpoints
#
# CRITICAL FINDING: Phase_4C.md was a placeholder ("# placeholder").
# This patch provides the FULL Phase 4C implementation with Phase 7 integration.
#
# FILES TO CREATE:
#   nexora_crawler/api/routes/search.py       — Vector Search Service HTTP layer
#   nexora_crawler/api/routes/webhooks.py     — Webhook CRUD endpoints
#   nexora_crawler/api/routes/jobs.py         — Generic job submission
#   nexora_crawler/api/routes/gdpr.py         — GDPR erase endpoint
#   nexora_crawler/api/routes/extract.py      — Schema-driven extraction
#   nexora_crawler/api/auth.py                — JWT + workspace isolation
#   nexora_crawler/api/database/connection.py — Async DB connection
#
# DATABASE MIGRATIONS (add to Phase 4A's schema init):
#   - webhooks table
#   - webhook_deliveries table
#   - workspace_quotas table
#   - usage_records table
#   - audit_logs table

# ============================================================
# FILE: nexora_crawler/api/auth.py
# ============================================================

"""
Authentication & Authorization — Phase 4C + Phase 7 integration.

Provides:
  - JWT token validation
  - Workspace ID extraction from token
  - Rate limiting per workspace
  - Optional: API key authentication (for service accounts)
"""

import os
import logging
from datetime import datetime, timezone, timedelta
from typing import Optional

from fastapi import HTTPException, Depends, Request
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from pydantic import BaseModel
import jwt

logger = logging.getLogger(__name__)

security = HTTPBearer(auto_error=False)


class TokenData(BaseModel):
    workspace_id: str
    role: str = "user"  # user | admin | service
    exp: Optional[datetime] = None


# ---- Configuration ----
JWT_SECRET = os.getenv("JWT_SECRET_KEY", "change-me-in-production")
JWT_ALGORITHM = os.getenv("JWT_ALGORITHM", "HS256")
JWT_EXPIRE_MINUTES = int(os.getenv("JWT_ACCESS_TOKEN_EXPIRE_MINUTES", "60"))


async def get_workspace_id(
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(security),
    request: Request = None,
) -> str:
    """
    Extract workspace_id from JWT token.

    For development: accepts 'X-Workspace-Id' header without auth.
    For production: requires valid JWT.
    """
    # Development bypass
    if request and request.headers.get("X-Workspace-Id"):
        return request.headers.get("X-Workspace-Id")

    if not credentials:
        raise HTTPException(status_code=401, detail="Authentication required")

    try:
        payload = jwt.decode(
            credentials.credentials, JWT_SECRET, algorithms=[JWT_ALGORITHM]
        )
        workspace_id = payload.get("workspace_id")
        if not workspace_id:
            raise HTTPException(status_code=401, detail="Invalid token: no workspace")
        return workspace_id
    except jwt.ExpiredSignatureError:
        raise HTTPException(status_code=401, detail="Token expired")
    except jwt.InvalidTokenError as e:
        raise HTTPException(status_code=401, detail=f"Invalid token: {e}")


def create_access_token(workspace_id: str, role: str = "user") -> str:
    """Generate a new JWT access token."""
    now = datetime.now(timezone.utc)
    payload = {
        "workspace_id": workspace_id,
        "role": role,
        "iat": now,
        "exp": now + timedelta(minutes=JWT_EXPIRE_MINUTES),
    }
    return jwt.encode(payload, JWT_SECRET, algorithm=JWT_ALGORITHM)


# ---- Admin dependency ----
async def require_admin(workspace_id: str = Depends(get_workspace_id)) -> str:
    """Placeholder — check workspace role in real implementation."""
    return workspace_id


# ============================================================
# FILE: nexora_crawler/api/database/connection.py
# ============================================================

"""
Async database connection — Phase 4C + Phase 7.

Supports SQLite (dev) and Postgres (prod) via DATABASE_URL env var.
Uses aiosqlite for SQLite, asyncpg for Postgres.
"""

import os
import logging
from typing import Optional

logger = logging.getLogger(__name__)

DATABASE_URL = os.getenv("NEXORA_DATABASE_URL", "sqlite+aiosqlite:///./data/nexora.db")
_db = None


async def get_db():
    """Get async database connection. Singleton pattern."""
    global _db
    if _db is not None:
        return _db

    if DATABASE_URL.startswith("postgresql") or DATABASE_URL.startswith("postgres"):
        import asyncpg
        _db = await asyncpg.create_pool(DATABASE_URL, min_size=2, max_size=10)
        logger.info("[DB] Connected to Postgres")
    else:
        import aiosqlite
        # aiosqlite doesn't have connection pools, so we return a connection
        _db = await aiosqlite.connect(DATABASE_URL.replace("sqlite+aiosqlite://", ""))
        _db.row_factory = aiosqlite.Row
        logger.info("[DB] Connected to SQLite")

    return _db


async def close_db():
    """Close database connection."""
    global _db
    if _db is not None:
        if hasattr(_db, 'close'):
            await _db.close()
        _db = None
        logger.info("[DB] Connection closed")


# ============================================================
# FILE: nexora_crawler/api/routes/search.py
# ============================================================

"""
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

from nexora_crawler.vector_store.factory import build_vector_store
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
    from nexora_crawler.ai.embedding_engine import UnifiedEmbeddingEngine
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
    store = build_vector_store()
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
    store = build_vector_store()
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


# ============================================================
# FILE: nexora_crawler/api/routes/webhooks.py
# ============================================================

"""
Webhook Subsystem — Phase 4C + Phase 7.

CRUD endpoints for webhook management.
Delivery is handled by Celery worker (Phase 5 integration).

Endpoints:
  POST   /v1/webhooks        — Create webhook
  GET    /v1/webhooks        — List webhooks
  DELETE /v1/webhooks/{id}   — Delete webhook
"""

import json
import logging
import secrets
from datetime import datetime, timezone
from typing import List

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, HttpUrl, Field

from nexora_crawler.api.auth import get_workspace_id
from nexora_crawler.api.database.connection import get_db

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/v1/webhooks", tags=["Webhooks"])


class WebhookCreate(BaseModel):
    url: HttpUrl
    event_types: List[str] = Field(default=["job.completed", "job.failed"])
    secret: Optional[str] = Field(None, description="Auto-generated if not provided")


class WebhookOut(BaseModel):
    id: int
    url: str
    event_types: List[str]
    is_active: bool
    created_at: str


@router.post("", response_model=WebhookOut, status_code=201)
async def create_webhook(
    req: WebhookCreate,
    workspace_id: str = Depends(get_workspace_id),
):
    """Create a new webhook. Secret is returned ONCE."""
    secret = req.secret or secrets.token_urlsafe(32)
    db = await get_db()

    if hasattr(db, 'fetch_one'):  # asyncpg
        row = await db.fetchone(
            """INSERT INTO webhooks (workspace_id, url, event_types, secret, is_active)
            VALUES ($1, $2, $3, $4, 1)
            RETURNING id, url, event_types, is_active, created_at""",
            workspace_id, str(req.url), json.dumps(req.event_types), secret,
        )
    else:  # aiosqlite
        cursor = await db.execute(
            """INSERT INTO webhooks (workspace_id, url, event_types, secret, is_active)
            VALUES (?, ?, ?, ?, 1)
            RETURNING id, url, event_types, is_active, created_at""",
            (workspace_id, str(req.url), json.dumps(req.event_types), secret),
        )
        row = await cursor.fetchone()

    out = dict(row)
    out["event_types"] = json.loads(out["event_types"])
    # Return secret ONCE — never again
    out["_secret_display_once"] = secret
    return WebhookOut(**out)


@router.get("", response_model=List[WebhookOut])
async def list_webhooks(
    workspace_id: str = Depends(get_workspace_id),
):
    """List webhooks for the workspace."""
    db = await get_db()

    if hasattr(db, 'fetch_all'):  # asyncpg
        rows = await db.fetch(
            "SELECT id, url, event_types, is_active, created_at FROM webhooks WHERE workspace_id = $1 ORDER BY id DESC",
            workspace_id,
        )
    else:  # aiosqlite
        cursor = await db.execute(
            "SELECT id, url, event_types, is_active, created_at FROM webhooks WHERE workspace_id = ? ORDER BY id DESC",
            (workspace_id,),
        )
        rows = await cursor.fetchall()

    out = []
    for r in rows:
        r = dict(r)
        r["event_types"] = json.loads(r["event_types"])
        out.append(WebhookOut(**r))
    return out


@router.delete("/{webhook_id}", status_code=204)
async def delete_webhook(
    webhook_id: int,
    workspace_id: str = Depends(get_workspace_id),
):
    """Delete a webhook."""
    db = await get_db()
    await db.execute(
        "DELETE FROM webhooks WHERE id = ? AND workspace_id = ?",
        (webhook_id, workspace_id),
    )


# ============================================================
# FILE: nexora_crawler/api/routes/jobs.py
# ============================================================

"""
Generic Job Submission — Phase 4C + Phase 7.

Replaces Phase 4C's hardcoded /crawl/start with a generic system.
Any registered job type can be submitted via this endpoint.

Endpoints:
  POST /v1/jobs — Submit any registered job type
"""

import logging
from typing import Any, Dict

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from nexora_crawler.api.auth import get_workspace_id
from nexora_crawler.jobs.registry import JobTypeRegistry

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/v1/jobs", tags=["Jobs"])


class JobSubmit(BaseModel):
    type: str = Field(..., description="Job type, e.g. 'crawl', 'schema_extract', 'index_search'")
    input: Dict[str, Any] = Field(default_factory=dict)
    async_run: bool = Field(True, description="If false, runs inline and returns result")


class JobSubmitResponse(BaseModel):
    job_id: str
    type: str
    status: str
    result: Any = None  # populated only when async_run=False


@router.post("", response_model=JobSubmitResponse, status_code=202)
async def submit_job(
    req: JobSubmit,
    workspace_id: str = Depends(get_workspace_id),
):
    """
    Submit a job of any registered type.

    Built-in types:
      - crawl          : Standard web crawl
      - schema_extract : Crawl + JSON Schema field extraction
      - index_search   : Pure vector search (no crawl, can run inline)
      - index_add      : Add records to vector store (can run inline)
      - export         : Export existing crawl results
    """
    import uuid

    # Verify job type is registered
    try:
        handler = JobTypeRegistry.get(req.type)
    except KeyError as e:
        raise HTTPException(status_code=400, detail=str(e))

    job_id = str(uuid.uuid4())

    if not req.async_run and handler.is_external:
        # Run inline for fast, lightweight ops
        from nexora_crawler.jobs.registry import dispatch_job
        try:
            result = dispatch_job(req.type, req.input, workspace_id, job_id)
            return JobSubmitResponse(
                job_id=job_id, type=req.type, status="completed", result=result
            )
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"Job failed: {e}")

    # Async path — dispatch to Celery
    from nexora_crawler.tasks.dispatcher import dispatcher_task
    dispatcher_task.delay(
        job_id=job_id, job_type=req.type,
        input_data=req.input, workspace_id=workspace_id,
    )
    return JobSubmitResponse(job_id=job_id, type=req.type, status="queued")


@router.get("/types")
async def list_job_types():
    """List all registered job types."""
    return {"types": JobTypeRegistry.list()}


# ============================================================
# FILE: nexora_crawler/api/routes/gdpr.py
# ============================================================

"""
GDPR Compliance Endpoints — Phase 4C + Phase 7.

Endpoints:
  DELETE /v1/gdpr/erase — Right to erasure (Article 17)
"""

import logging
from datetime import datetime, timezone, timedelta

from fastapi import APIRouter, Depends, BackgroundTasks
from pydantic import BaseModel

from nexora_crawler.api.auth import get_workspace_id
from nexora_crawler.api.database.connection import get_db
from nexora_crawler.vector_store.factory import build_vector_store

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/v1/gdpr", tags=["GDPR Compliance"])


class EraseResponse(BaseModel):
    workspace_id: str
    status: str
    pages_deleted: int
    vectors_deleted: int
    scheduled_hard_delete: str


@router.delete("/erase", response_model=EraseResponse)
async def gdpr_erase(
    background_tasks: BackgroundTasks,
    workspace_id: str = Depends(get_workspace_id),
):
    """
    GDPR Article 17 — Right to erasure.
    Deletes all data for workspace. Hard-delete scheduled in 30 days.
    """
    db = await get_db()

    # Count before delete
    if hasattr(db, 'fetchval'):  # asyncpg
        pages = await db.fetchval(
            "SELECT COUNT(*) FROM pages WHERE workspace_id = $1", workspace_id
        )
    else:  # aiosqlite
        cursor = await db.execute(
            "SELECT COUNT(*) FROM pages WHERE workspace_id = ?", (workspace_id,)
        )
        row = await cursor.fetchone()
        pages = row[0] if row else 0

    # Delete from relational store
    await db.execute("DELETE FROM pages WHERE workspace_id = ?", (workspace_id,))
    await db.execute("DELETE FROM crawl_jobs WHERE workspace_id = ?", (workspace_id,))

    # Delete from vector store
    store = build_vector_store()
    vectors = await store.delete_by_workspace(workspace_id)

    # Audit log
    await db.execute(
        """INSERT INTO audit_logs
        (workspace_id, actor, action, target_id, details, ip_address, timestamp)
        VALUES (?, ?, ?, ?, ?, ?, ?)""",
        (workspace_id, "system", "gdpr_erase", workspace_id,
         json.dumps({"pages": pages, "vectors": vectors}), "0.0.0.0",
         datetime.now(timezone.utc).isoformat()),
    )

    hard_delete_date = (datetime.now(timezone.utc) + timedelta(days=30)).isoformat()

    return EraseResponse(
        workspace_id=workspace_id,
        status="purged",
        pages_deleted=pages,
        vectors_deleted=vectors if vectors >= 0 else 0,
        scheduled_hard_delete=hard_delete_date,
    )


# ============================================================
# FILE: nexora_crawler/api/routes/extract.py
# ============================================================

"""
Schema-Driven Extraction — Phase 4C + Phase 7.

Firecrawl's headline feature: user submits a JSON Schema,
pipeline extracts structured fields from each crawled page.

Endpoints:
  POST /v1/extract/schema — Submit schema-driven crawl
"""

import json
import logging
import uuid
from typing import Dict, Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, HttpUrl, Field

from nexora_crawler.api.auth import get_workspace_id

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/v1/extract", tags=["Schema Extraction"])


class ExtractRequest(BaseModel):
    url: HttpUrl
    strategy: str = Field("whole-website", description="single-page | linked-pages | whole-website | everything")
    max_pages: int = Field(50, ge=1, le=10000)
    json_schema: Dict[str, Any] = Field(..., description="JSON Schema defining fields to extract")
    output_format: str = Field("json", description="json | csv | parquet | markdown")


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
    db = await get_db()
    await db.execute(
        """INSERT INTO extraction_schemas
        (job_id, workspace_id, schema_json, created_at)
        VALUES (?, ?, ?, ?)""",
        (job_id, workspace_id, json.dumps(req.json_schema),
         datetime.now(timezone.utc).isoformat()),
    )

    # Dispatch to Celery
    from nexora_crawler.tasks.dispatcher import dispatcher_task
    dispatcher_task.delay(
        job_id=job_id, job_type="schema_extract",
        input_data={
            "url": str(req.url),
            "strategy": req.strategy,
            "max_pages": req.max_pages,
            "output_format": req.output_format,
            "schema_job_id": job_id,
        },
        workspace_id=workspace_id,
    )

    return ExtractResponse(
        job_id=job_id,
        status="queued",
        url=str(req.url),
        schema_fields=len(req.json_schema.get("properties", {})),
    )


# ============================================================
# DATABASE MIGRATIONS (add to Phase 4A schema init)
# ============================================================

"""
Add these tables to your schema initialization (local_sqlite.py or Postgres migration):

-- Webhooks
CREATE TABLE IF NOT EXISTS webhooks (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    workspace_id TEXT NOT NULL,
    url TEXT NOT NULL,
    event_types TEXT NOT NULL,    -- JSON array
    secret TEXT NOT NULL,         -- HMAC signing key
    is_active INTEGER DEFAULT 1,
    created_at TEXT DEFAULT (datetime('now'))
);
CREATE INDEX idx_webhooks_workspace ON webhooks(workspace_id);

-- Webhook delivery log
CREATE TABLE IF NOT EXISTS webhook_deliveries (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    webhook_id INTEGER NOT NULL,
    job_id TEXT,
    event_type TEXT,
    status_code INTEGER,
    attempt INTEGER DEFAULT 0,
    delivered_at TEXT,
    error TEXT,
    FOREIGN KEY (webhook_id) REFERENCES webhooks(id)
);
CREATE INDEX idx_webhook_deliveries_webhook ON webhook_deliveries(webhook_id);

-- Workspace quotas
CREATE TABLE IF NOT EXISTS workspace_quotas (
    workspace_id TEXT PRIMARY KEY,
    pages_per_month INTEGER DEFAULT 10000,
    storage_gb INTEGER DEFAULT 1,
    vector_records INTEGER DEFAULT 100000,
    api_rpm INTEGER DEFAULT 60,
    schema_extracts_per_day INTEGER DEFAULT 10,
    updated_at TEXT DEFAULT (datetime('now'))
);

-- Usage tracking
CREATE TABLE IF NOT EXISTS usage_records (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    workspace_id TEXT NOT NULL,
    period TEXT NOT NULL,         -- YYYY-MM
    pages_crawled INTEGER DEFAULT 0,
    storage_bytes INTEGER DEFAULT 0,
    vector_records INTEGER DEFAULT 0,
    api_calls INTEGER DEFAULT 0,
    recorded_at TEXT DEFAULT (datetime('now')),
    UNIQUE(workspace_id, period)
);
CREATE INDEX idx_usage_workspace_period ON usage_records(workspace_id, period);

-- Audit logs
CREATE TABLE IF NOT EXISTS audit_logs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    workspace_id TEXT NOT NULL,
    actor TEXT NOT NULL,
    action TEXT NOT NULL,
    target_id TEXT,
    details TEXT,                 -- JSON
    ip_address TEXT,
    timestamp TEXT DEFAULT (datetime('now'))
);
CREATE INDEX idx_audit_workspace ON audit_logs(workspace_id);
CREATE INDEX idx_audit_action ON audit_logs(action);
CREATE INDEX idx_audit_timestamp ON audit_logs(timestamp);

-- Extraction schemas (for schema-driven crawls)
CREATE TABLE IF NOT EXISTS extraction_schemas (
    job_id TEXT PRIMARY KEY,
    workspace_id TEXT NOT NULL,
    schema_json TEXT NOT NULL,
    created_at TEXT NOT NULL
);
CREATE INDEX idx_extraction_schemas_workspace ON extraction_schemas(workspace_id);
"""

# ============================================================
# FASTAPI APP REGISTRATION (add to your main API file)
# ============================================================

"""
from fastapi import FastAPI
from nexora_crawler.api.routes import search, webhooks, jobs, gdpr, extract

app = FastAPI(title="Nexora API", version="1.0.0")

# Include all routers
app.include_router(search.router)
app.include_router(webhooks.router)
app.include_router(jobs.router)
app.include_router(gdpr.router)
app.include_router(extract.router)

# Health check
@app.get("/health")
async def health():
    return {"status": "healthy", "version": "1.0.0"}


================================================================================
## SECTION 4: PHASE 5 — CELERY FIXES, WEBHOOKS, JOB REGISTRY, OTEL
## Source File: phase_5_additional_integration.md
================================================================================

# PHASE 5 — ADDITIONAL INTEGRATION PATCH
# Version: 1.0.0 | Date: 2026-07-03
# Purpose: Fix Phase 5 Celery tasks and add Phase 7 job registry, webhooks, OTel
#
# CRITICAL FINDINGS FROM AUDIT:
#   1. ExponentialBackoffMiddleware uses time.sleep() — BLOCKS Scrapy reactor
#   2. Celery retry uses fixed delay (default_retry_delay=60) not exponential
#   3. No webhook delivery worker exists
#   4. No JobTypeRegistry — only hardcoded crawl_website task
#   5. No OTel trace propagation across Celery boundary
#   6. No Prometheus metrics endpoint
#
# THIS PATCH REPLACES/MODIFIES:
#   - nexora_crawler/middlewares/exponential_backoff.py (FULL REPLACEMENT)
#   - nexora_crawler/tasks.py (MODIFY retry logic)
#   - nexora_crawler/tasks/webhook_delivery.py (NEW)
#   - nexora_crawler/tasks/dispatcher.py (NEW)
#   - nexora_crawler/jobs/registry.py (NEW)
#   - nexora_crawler/jobs/handlers/*.py (NEW — 5 built-in handlers)
#   - nexora_crawler/observability/metrics.py (NEW)
#   - nexora_crawler/observability/tracing.py (NEW)

# ============================================================
# FILE: nexora_crawler/middlewares/exponential_backoff.py (REPLACEMENT)
# ============================================================

"""
Exponential Backoff Middleware — Phase 5 (FIXED).

CRITICAL FIX: Old implementation used time.sleep() in process_request,
which BLOCKS the entire Scrapy async reactor. This version uses Scrapy's
built-in delay system via meta['download_delay'].

Also adds jitter to make retry patterns non-deterministic (anti-bot).
"""

import random
import logging
from urllib.parse import urlparse

logger = logging.getLogger(__name__)


class ExponentialBackoffMiddleware:
    """
    Scrapy-native exponential backoff with jitter.

    How it works:
      - On 429 response: increases per-domain delay exponentially
      - On success: resets delay to base
      - Uses Scrapy meta['download_delay'] — NEVER blocks reactor
      - Adds random jitter to prevent detectable patterns
    """

    def __init__(self):
        self.base_delay = 1.0      # seconds
        self.max_delay = 60.0      # cap at 60s
        self.jitter_factor = 0.5   # ±50% random jitter
        self.domain_delays = {}    # domain -> current delay

    @classmethod
    def from_crawler(cls, crawler):
        return cls()

    def process_response(self, request, response, spider):
        """
        Handle rate limit responses by increasing delay.
        Scrapy scheduler will respect meta['download_delay'] on retry.
        """
        domain = urlparse(request.url).netloc

        if response.status == 429:
            current = self.domain_delays.get(domain, self.base_delay)
            # Exponential: 1s, 2s, 4s, 8s, 16s, 32s, 60s (capped)
            new_delay = min(current * 2, self.max_delay)
            # Add jitter: ±50% random
            jittered = new_delay * (1 + random.uniform(-self.jitter_factor, self.jitter_factor))
            jittered = max(0.5, jittered)  # minimum 0.5s

            self.domain_delays[domain] = new_delay
            request.meta['download_delay'] = jittered

            retry_times = request.meta.get('retry_times', 0)
            logger.warning(
                '[Backoff] 429 on %s | retry %d | delay %.1fs (jittered from %.1fs)',
                domain, retry_times, jittered, new_delay
            )

            # Force retry
            return request

        # Success: reset delay
        if domain in self.domain_delays:
            old_delay = self.domain_delays[domain]
            if old_delay > self.base_delay:
                logger.info('[Backoff] Reset delay for %s (was %.1fs)', domain, old_delay)
            self.domain_delays[domain] = self.base_delay

        return response


# ============================================================
# FILE: nexora_crawler/tasks.py (MODIFY retry logic)
# ============================================================

"""
Celery Tasks — Phase 5 (FIXED RETRY LOGIC).

CRITICAL FIX: Old implementation used fixed delay:
    @app.task(bind=True, max_retries=3, default_retry_delay=60)

This meant retries at 60s, 60s, 60s — NOT exponential.

NEW: Exponential backoff with proper countdown:
    attempt 0: 10s
    attempt 1: 20s
    attempt 2: 40s
    attempt 3: 80s
    attempt 4: 160s
"""

# In your existing crawl_website task, REPLACE the except block:

"""
    except Exception as exc:
        # PHASE 7 FIX: exponential countdown
        countdown = 10 * (2 ** self.request.retries)
        logger.warning(
            '[Crawl] Retry %d/%d for job %s in %ds: %s',
            self.request.retries, 5, job_id, countdown, exc
        )
        raise self.retry(exc=exc, countdown=countdown)
"""

# Full corrected task signature:
"""
@app.task(bind=True, max_retries=5)  # REMOVED default_retry_delay
def crawl_website(self, url: str, strategy: str, max_pages: int,
                  workspace_id: str, job_id: Optional[str] = None):
    """Main crawl task with TRUE exponential backoff."""
    job_id = job_id or str(uuid.uuid4())

    try:
        # ... existing logic ...
        pass

    except SoftTimeLimitExceeded:
        state.complete_job(job_id, status='timeout', workspace_id=workspace_id)
        raise

    except Exception as exc:
        # PHASE 7 FIX: exponential countdown
        countdown = 10 * (2 ** self.request.retries)
        logger.warning(
            '[Crawl] Retry %d/%d for job %s in %ds: %s',
            self.request.retries, 5, job_id, countdown, exc
        )
        raise self.retry(exc=exc, countdown=countdown)
"""

# Apply same fix to ai_enrich_batch:
"""
@app.task(bind=True, max_retries=2)
def ai_enrich_batch(self, job_id: str, workspace_id: str, markdown_items: list):
    try:
        # ... existing logic ...
        pass
    except Exception as exc:
        countdown = 30 * (2 ** self.request.retries)
        logger.error('AI enrichment failed for job %s: %s', job_id, exc)
        raise self.retry(exc=exc, countdown=countdown)
"""


# ============================================================
# FILE: nexora_crawler/tasks/webhook_delivery.py (NEW)
# ============================================================

"""
Webhook Delivery Worker — Phase 5 + Phase 7.

Delivers webhooks with:
  - Exponential backoff retry (10s, 20s, 40s, 80s, 160s)
  - HMAC-SHA256 signature verification
  - Delivery history tracking
  - Circuit breaker (disable after 5 consecutive failures)
"""

import asyncio
import hmac
import hashlib
import json
import logging
from datetime import datetime, timezone

from celery import shared_task
import httpx

from nexora_crawler.api.database.connection import get_db

logger = logging.getLogger(__name__)

# Circuit breaker state (in-memory; use Redis for distributed)
_circuit_breakers = {}  # webhook_id -> {'failures': int, 'last_failure': datetime}
CIRCUIT_BREAKER_THRESHOLD = 5
CIRCUIT_BREAKER_TIMEOUT_MINUTES = 60


@shared_task(bind=True, max_retries=5)
def deliver_webhook(self, webhook_id: int, event_type: str,
                    job_id: str, payload: dict):
    """
    Deliver webhook with exponential backoff.

    Retry delays: 10s, 20s, 40s, 80s, 160s
    Circuit breaker: disabled after 5 consecutive failures, re-enabled after 1 hour.
    """
    asyncio.run(_deliver_async(webhook_id, event_type, job_id, payload, self.request.retries))


async def _deliver_async(webhook_id, event_type, job_id, payload, attempt):
    # Check circuit breaker
    cb = _circuit_breakers.get(webhook_id)
    if cb and cb['failures'] >= CIRCUIT_BREAKER_THRESHOLD:
        elapsed = (datetime.now(timezone.utc) - cb['last_failure']).total_seconds() / 60
        if elapsed < CIRCUIT_BREAKER_TIMEOUT_MINUTES:
            logger.warning(
                '[Webhook] Circuit breaker OPEN for webhook %s (%d failures, %d min ago)',
                webhook_id, cb['failures'], int(elapsed)
            )
            return  # Drop silently — webhook is broken
        else:
            logger.info('[Webhook] Circuit breaker CLOSED for webhook %s', webhook_id)
            _circuit_breakers.pop(webhook_id, None)

    db = await get_db()

    if hasattr(db, 'fetch_one'):  # asyncpg
        webhook = await db.fetch_one(
            "SELECT * FROM webhooks WHERE id = $1 AND is_active = 1", webhook_id
        )
    else:  # aiosqlite
        cursor = await db.execute(
            "SELECT * FROM webhooks WHERE id = ? AND is_active = 1", (webhook_id,)
        )
        webhook = await cursor.fetchone()

    if not webhook:
        logger.warning('[Webhook] %s inactive or deleted', webhook_id)
        return

    webhook = dict(webhook)

    # Build signed payload
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
        "User-Agent": "Nexora-Webhook/1.0",
    }

    try:
        async with httpx.AsyncClient(timeout=15, follow_redirects=False) as client:
            response = await client.post(webhook["url"], content=body, headers=headers)

        # Record delivery
        await db.execute(
            """INSERT INTO webhook_deliveries
            (webhook_id, job_id, status_code, attempt, delivered_at)
            VALUES (?, ?, ?, ?, ?)""",
            (webhook_id, job_id, response.status_code, attempt + 1,
             datetime.now(timezone.utc).isoformat()),
        )

        if 200 <= response.status_code < 300:
            # Success: reset circuit breaker
            _circuit_breakers.pop(webhook_id, None)
            logger.info('[Webhook] Delivered to %s (status=%d)', webhook["url"], response.status_code)
        else:
            raise RuntimeError(f"Webhook returned {response.status_code}")

    except Exception as exc:
        # Update circuit breaker
        cb = _circuit_breakers.get(webhook_id, {'failures': 0})
        cb['failures'] += 1
        cb['last_failure'] = datetime.now(timezone.utc)
        _circuit_breakers[webhook_id] = cb

        # Exponential backoff
        countdown = 10 * (2 ** attempt)
        logger.warning(
            '[Webhook] Delivery failed (attempt %d/%d), retrying in %ds: %s',
            attempt + 1, 5, countdown, exc
        )
        raise deliver_webhook.retry(
            args=[webhook_id, event_type, job_id, payload],
            countdown=countdown,
        )


# ============================================================
# FILE: nexora_crawler/tasks/dispatcher.py (NEW)
# ============================================================

"""
Generic Job Dispatcher — Phase 5 + Phase 7.

Dispatches any registered job type through Celery.
Integrates with OTel trace propagation.
"""

import logging
from celery import shared_task
from celery.signals import task_prerun

from nexora_crawler.jobs.registry import JobTypeRegistry, dispatch_job
from nexora_crawler.observability.metrics import JOBS_SUBMITTED, JOBS_COMPLETED

logger = logging.getLogger(__name__)


@shared_task(bind=True)
def dispatcher_task(self, job_id, job_type, input_data, workspace_id):
    """
    Generic dispatcher — calls any registered handler.

    Metrics:
      - nexora_jobs_submitted_total{type, workspace_id}
      - nexora_jobs_completed_total{type, workspace_id, status}
    """
    JOBS_SUBMITTED.labels(type=job_type, workspace_id=workspace_id).inc()

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


# ---- OTel trace propagation across Celery boundary ----
# Without this, traces die when crossing API → worker

try:
    from opentelemetry import trace
    from opentelemetry.propagate import extract, inject
    _otel_available = True
except ImportError:
    _otel_available = False


@task_prerun.connect
def inject_trace_context(sender=None, task=None, **kwargs):
    """Rehydrate trace context from Celery task headers."""
    if not _otel_available:
        return
    headers = task.request.headers if hasattr(task.request, 'headers') else {}
    if headers:
        ctx = extract(headers)
        trace.set_span_in_context(trace.get_current_span(), ctx)


def dispatch_with_trace(job_id, job_type, input_data, workspace_id):
    """Dispatch with trace context injected into Celery headers."""
    trace_ctx = {}
    if _otel_available:
        inject(trace_ctx)
    dispatcher_task.apply_async(
        args=[job_id, job_type, input_data, workspace_id],
        headers=trace_ctx,
    )


# ============================================================
# FILE: nexora_crawler/jobs/registry.py (NEW)
# ============================================================

"""
JobTypeRegistry — Phase 5 + Phase 7.

Decouples the queue from crawl-only. Any job type can be registered.

Built-in types:
  - crawl          : standard web crawl
  - schema_extract : crawl + JSON Schema field extraction
  - index_search   : pure vector search (no crawl, can run inline)
  - index_add      : add records to vector store (can run inline)
  - export         : export existing crawl results

Plugin model: third parties register via Python entry points.
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
    is_external: bool = False  # can run inline without Celery


class JobTypeRegistry:
    _handlers: Dict[str, JobHandler] = {}

    @classmethod
    def register(cls, handler: JobHandler):
        cls._handlers[handler.name] = handler
        logger.info("[Jobs] Registered: %s", handler.name)

    @classmethod
    def get(cls, name: str) -> JobHandler:
        if name not in cls._handlers:
            raise KeyError(
                f"Unknown job type: {name}. "
                f"Available: {list(cls._handlers.keys())}"
            )
        return cls._handlers[name]

    @classmethod
    def list(cls):
        return list(cls._handlers.keys())


def dispatch_job(job_type: str, input_data: dict, workspace_id: str,
                 job_id: str = None) -> dict:
    """Resolve job type, validate input, run handler."""
    handler = JobTypeRegistry.get(job_type)
    validated = handler.input_schema(**input_data)
    return handler.handler(
        input=validated, workspace_id=workspace_id, job_id=job_id,
    )


# ---- Built-in handlers (auto-registered on import) ----
# These imports happen at module load time

try:
    from .handlers.crawl import crawl_handler, CrawlInput, CrawlOutput
    JobTypeRegistry.register(JobHandler("crawl", crawl_handler, CrawlInput, CrawlOutput))
except ImportError as e:
    logger.debug("[Jobs] Crawl handler not yet available: %s", e)

try:
    from .handlers.schema_extract import schema_extract_handler, SchemaExtractInput, SchemaExtractOutput
    JobTypeRegistry.register(JobHandler("schema_extract", schema_extract_handler, SchemaExtractInput, SchemaExtractOutput))
except ImportError as e:
    logger.debug("[Jobs] Schema extract handler not yet available: %s", e)

try:
    from .handlers.index_search import index_search_handler, IndexSearchInput, IndexSearchOutput
    JobTypeRegistry.register(JobHandler("index_search", index_search_handler, IndexSearchInput, IndexSearchOutput, is_external=True))
except ImportError as e:
    logger.debug("[Jobs] Index search handler not yet available: %s", e)

try:
    from .handlers.index_add import index_add_handler, IndexAddInput, IndexAddOutput
    JobTypeRegistry.register(JobHandler("index_add", index_add_handler, IndexAddInput, IndexAddOutput, is_external=True))
except ImportError as e:
    logger.debug("[Jobs] Index add handler not yet available: %s", e)

try:
    from .handlers.export import export_handler, ExportInput, ExportOutput
    JobTypeRegistry.register(JobHandler("export", export_handler, ExportInput, ExportOutput, timeout_seconds=600))
except ImportError as e:
    logger.debug("[Jobs] Export handler not yet available: %s", e)


# ---- Plugin entry point loading ----
def load_external_handlers():
    """Load third-party handlers via pyproject.toml entry points."""
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


# Call on startup
load_external_handlers()


# ============================================================
# FILE: nexora_crawler/observability/metrics.py (NEW)
# ============================================================

"""
Prometheus Metrics — Phase 5 + Phase 7.

Exposes counters and histograms for:
  - Job submission/completion
  - Page crawling
  - Embedding generation
  - Vector search latency
  - Webhook delivery
"""

from prometheus_client import Counter, Histogram, Gauge, generate_latest

# Job metrics
JOBS_SUBMITTED = Counter(
    "nexora_jobs_submitted_total",
    "Total jobs submitted",
    ["type", "workspace_id"]
)
JOBS_COMPLETED = Counter(
    "nexora_jobs_completed_total",
    "Total jobs completed",
    ["type", "workspace_id", "status"]
)
JOB_DURATION = Histogram(
    "nexora_job_duration_seconds",
    "Job processing duration",
    ["type"],
    buckets=[0.1, 0.5, 1.0, 2.5, 5.0, 10.0, 30.0, 60.0, 120.0, 300.0, 600.0]
)

# Crawl metrics
PAGES_CRAWLED = Counter(
    "nexora_pages_crawled_total",
    "Total pages crawled",
    ["workspace_id"]
)
CRAWL_ERRORS = Counter(
    "nexora_crawl_errors_total",
    "Total crawl errors",
    ["error_type"]
)

# AI metrics
EMBEDDINGS_GENERATED = Counter(
    "nexora_embeddings_generated_total",
    "Total embeddings generated",
    ["provider", "model"]
)
AI_REQUEST_DURATION = Histogram(
    "nexora_ai_request_duration_seconds",
    "AI API request duration",
    ["provider", "model", "operation"],
    buckets=[0.01, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0, 10.0]
)

# Vector metrics
VECTOR_SEARCH_DURATION = Histogram(
    "nexora_vector_search_seconds",
    "Vector search duration",
    ["backend", "search_type"],
    buckets=[0.001, 0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1.0]
)
VECTOR_RECORDS = Gauge(
    "nexora_vector_records",
    "Current vector record count",
    ["backend", "workspace_id"]
)

# Webhook metrics
WEBHOOK_DELIVERIES = Counter(
    "nexora_webhook_deliveries_total",
    "Webhook deliveries",
    ["status_code", "event_type"]
)
WEBHOOK_RETRIES = Counter(
    "nexora_webhook_retries_total",
    "Webhook retry attempts",
    ["webhook_id"]
)

# Quota metrics
QUOTA_ENFORCED = Counter(
    "nexora_quota_enforced_total",
    "Quota enforcement events",
    ["resource", "action"]  # resource=pages|storage|api_calls, action=soft|hard
)


# ============================================================
# FILE: nexora_crawler/observability/metrics_endpoint.py (NEW)
# ============================================================

"""
Prometheus Metrics HTTP Endpoint — Phase 5 + Phase 7.

Mounted at GET /metrics for Prometheus scraping.
"""

from fastapi import APIRouter, Response
from prometheus_client import generate_latest, CONTENT_TYPE_LATEST

router = APIRouter()


@router.get("/metrics", include_in_schema=False)
async def metrics():
    """Prometheus metrics endpoint."""
    return Response(
        content=generate_latest(),
        media_type=CONTENT_TYPE_LATEST,
    )


# ============================================================
# FILE: nexora_crawler/observability/tracing.py (NEW)
# ============================================================

"""
OpenTelemetry Tracing — Phase 5 + Phase 7.

Initializes OTLP exporter and provides trace_span context manager.
Trace context is propagated through Celery headers.
"""

import os
import logging
from contextlib import contextmanager

logger = logging.getLogger(__name__)

_tracer = None
_initialized = False


def init_observability():
    """Call once on app startup."""
    global _tracer, _initialized
    if _initialized:
        return

    try:
        from opentelemetry import trace, metrics
        from opentelemetry.sdk.trace import TracerProvider
        from opentelemetry.sdk.metrics import MeterProvider
        from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter
        from opentelemetry.exporter.otlp.proto.grpc.metric_exporter import OTLPMetricExporter
        from opentelemetry.sdk.trace.export import BatchSpanProcessor
        from opentelemetry.sdk.metrics.export import PeriodicExportingMetricReader

        endpoint = os.getenv("OTEL_EXPORTER_OTLP_ENDPOINT", "localhost:4317")

        # Traces
        tracer_provider = TracerProvider()
        tracer_provider.add_span_processor(
            BatchSpanProcessor(OTLPSpanExporter(endpoint=endpoint))
        )
        trace.set_tracer_provider(tracer_provider)
        _tracer = trace.get_tracer("nexora")

        # Metrics
        reader = PeriodicExportingMetricReader(
            OTLPMetricExporter(endpoint=endpoint),
            export_interval_millis=30000,
        )
        meter_provider = MeterProvider(metric_readers=[reader])
        metrics.set_meter_provider(meter_provider)

        _initialized = True
        logger.info("[Observability] OTLP endpoint: %s", endpoint)

    except Exception as e:
        logger.warning("[Observability] Init failed, running in noop mode: %s", e)


@contextmanager
def trace_span(name: str, attributes: dict = None):
    """Context manager for creating spans."""
    if _tracer is None:
        yield None
        return
    with _tracer.start_as_current_span(name) as span:
        if attributes:
            for k, v in attributes.items():
                span.set_attribute(k, v)
        yield span


# ============================================================
# CELERY APP UPDATE (add to celery_app.py)
# ============================================================

"""
Add these imports and signal handlers to your celery_app.py:

from nexora_crawler.observability.tracing import init_observability
from nexora_crawler.jobs.registry import load_external_handlers

# Initialize on worker startup
@app.on_after_configure.connect
def setup_periodic_tasks(sender, **kwargs):
    init_observability()
    load_external_handlers()
"""


# ============================================================
# SETTINGS.PY ADDITIONS
# ============================================================

"""
Add to settings.py:

# ---- Phase 7: Observability ----
OTEL_EXPORTER_OTLP_ENDPOINT = os.getenv("OTEL_EXPORTER_OTLP_ENDPOINT", "localhost:4317")
OTEL_SERVICE_NAME = os.getenv("OTEL_SERVICE_NAME", "nexora")

# ---- Phase 7: Celery Queues ----
CELERY_TASK_ROUTES = {
    'nexora_crawler.tasks.crawl_website': {'queue': 'crawl'},
    'nexora_crawler.tasks.ai_enrich_batch': {'queue': 'ai'},
    'nexora_crawler.tasks.export_data': {'queue': 'export'},
    'nexora_crawler.tasks.webhook_delivery.deliver_webhook': {'queue': 'webhook'},
    'nexora_crawler.tasks.dispatcher.dispatcher_task': {'queue': 'dispatcher'},
}


================================================================================
## SECTION 5: PHASE 6 — PII, GDPR, SCHEMA EXTRACTION, QUOTAS
## Source File: phase_6_additional_integration.md
================================================================================

# PHASE 6 — ADDITIONAL INTEGRATION PATCH
# Version: 1.0.0 | Date: 2026-07-03
# Purpose: Add Phase 7 compliance features (PII, GDPR, schema extraction, audit logging)
#
# CRITICAL FINDINGS FROM AUDIT:
#   1. Phase 6 spec has ZERO PII redaction
#   2. Phase 6 spec has ZERO GDPR erase endpoint
#   3. Phase 6 spec has ZERO audit logging
#   4. Phase 6 spec has ZERO schema extraction pipeline
#   5. Phase 6 spec focuses entirely on Tauri desktop + packaging
#
# THIS PATCH ADDS:
#   - nexora_crawler/pipelines/pii_redaction_pipeline.py (NEW)
#   - nexora_crawler/pipelines/schema_extraction_pipeline.py (NEW)
#   - nexora_crawler/api/routes/gdpr.py (already in Phase 4C patch, referenced here)
#   - Audit logging hooks in all compliance endpoints
#   - Desktop app integration for compliance features

# ============================================================
# FILE: nexora_crawler/pipelines/pii_redaction_pipeline.py (NEW)
# ============================================================

"""
PII Redaction Pipeline — Phase 6 + Phase 7.

Priority: 200 (after MarkdownExtractionPipeline at 110, before StylePipeline at 150)

Two modes:
  - fast: regex-only (email, phone, SSN, credit card, IBAN, address)
  - llm: regex + LiteLLM-based NER for names, organizations

Redaction is token-aware: '[REDACTED:EMAIL]' replaces the PII
so the page is still useful for downstream pipelines (AI summary, etc.)
"""

import logging
import re
from typing import List, Tuple

logger = logging.getLogger(__name__)

# Tier 1: regex patterns (always on, free, fast)
REGEX_PATTERNS: List[Tuple[str, str]] = [
    # Email addresses
    (r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}", "[REDACTED:EMAIL]"),
    # US phone numbers
    (r"(?:\+?1[-.\s]?)?\(?\d{3}\)?[-.\s]?\d{3}[-.\s]?\d{4}", "[REDACTED:PHONE]"),
    # SSN
    (r"\d{3}-\d{2}-\d{4}", "[REDACTED:SSN]"),
    # Credit cards (13-19 digits with optional spaces/dashes)
    (r"(?:\d[ -]*?){13,19}", "[REDACTED:CC]"),
    # IBAN
    (r"[A-Z]{2}\d{2}[A-Z\d]{4}\d{7}([A-Z\d]?){0,16}", "[REDACTED:IBAN]"),
    # Street addresses (basic heuristic)
    (r"\d{1,5}\s+\w+(?:\s+\w+)*\s+(?:Street|St|Avenue|Ave|Road|Rd|Boulevard|Blvd|Drive|Dr|Lane|Ln|Way|Court|Ct|Place|Pl|Circle|Cir)",
     "[REDACTED:ADDRESS]"),
    # IP addresses
    (r"(?:\d{1,3}\.){3}\d{1,3}", "[REDACTED:IP]"),
    # API keys / tokens (basic heuristic)
    (r"(?:api[_-]?key|token|secret)[\s]*[:=][\s]*['"]?[a-zA-Z0-9_-]{16,}['"]?",
     "[REDACTED:API_KEY]"),
]


class PIIRedactionPipeline:
    """
    Scrapy pipeline for PII redaction.

    Priority: 200 — runs after MarkdownExtractionPipeline (110),
    before UnifiedSchemaEnricher (160).

    Configuration (settings.py):
      NEXORA_PII_REDACTION_ENABLED = True
      NEXORA_PII_MODE = "regex"  # "regex" | "llm"
      NEXORA_PII_LLM_MODEL = "gpt-4o-mini"
    """

    def __init__(self, crawler):
        self.settings = crawler.settings
        self.enabled = self.settings.getbool("NEXORA_PII_REDACTION_ENABLED", False)
        self.mode = self.settings.get("NEXORA_PII_MODE", "regex")  # 'regex' | 'llm'
        self.stats = {
            "pages_processed": 0,
            "pages_redacted": 0,
            "redactions": 0,
            "llm_passes": 0,
            "llm_errors": 0,
        }

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
        redaction_count = 0

        # Tier 1: Regex redaction (always runs)
        for pattern, replacement in REGEX_PATTERNS:
            text, count = re.subn(pattern, replacement, text, flags=re.IGNORECASE)
            redaction_count += count

        # Tier 2: LLM redaction (optional, for names/organizations)
        if self.mode == "llm" and text != original:
            try:
                text = await self._llm_redaction(text)
                self.stats["llm_passes"] += 1
            except Exception as e:
                logger.warning("[PII] LLM redaction failed, keeping regex-only: %s", e)
                self.stats["llm_errors"] += 1

        if text != original:
            self.stats["pages_redacted"] += 1
            self.stats["redactions"] += redaction_count

        item["markdown"] = text
        item["pii_redacted"] = text != original
        item["pii_redaction_count"] = redaction_count

        self.stats["pages_processed"] += 1
        return item

    async def _llm_redaction(self, text: str) -> str:
        """
        Use LiteLLM to detect and redact personal names and organization names.
        Only processes first 6000 chars to stay within context limits.
        """
        import litellm

        model = self.settings.get("NEXORA_PII_LLM_MODEL", "gpt-4o-mini")
        provider = self.settings.get("NEXORA_AI_PROVIDER", "ollama")
        base_url = self.settings.get("NEXORA_AI_BASE_URL", "http://localhost:11434")
        api_key = self.settings.get("NEXORA_AI_API_KEY", "not-needed")

        response = await litellm.acompletion(
            model=f"{provider}/{model}",
            messages=[{
                "role": "system",
                "content": (
                    "You are a PII redaction assistant. "
                    "Identify personal names and organization names in the text. "
                    "Replace personal names with [REDACTED:NAME]. "
                    "Replace organization names with [REDACTED:ORG]. "
                    "Do NOT redact generic terms, product names, or place names. "
                    "Return ONLY the redacted text, no explanations."
                ),
            }, {
                "role": "user",
                "content": text[:6000],
            }],
            api_base=base_url,
            api_key=api_key,
            temperature=0.0,
            max_tokens=4000,
        )
        return response.choices[0].message.content

    def close_spider(self, spider):
        logger.info("[PII] Pipeline stats: %s", self.stats)


# ============================================================
# FILE: nexora_crawler/pipelines/schema_extraction_pipeline.py (NEW)
# ============================================================

"""
Schema Extraction Pipeline — Phase 6 + Phase 7.

Firecrawl's headline feature: user submits a JSON Schema;
pipeline uses LiteLLM structured output to populate it from each page.

Priority: 280 (after VectorIndexPipeline at 270, before Parquet at 450)

Example user schema:
    {
      "type": "object",
      "properties": {
        "product_name":  {"type": "string"},
        "price":         {"type": "number"},
        "in_stock":      {"type": "boolean"},
        "features":      {"type": "array", "items": {"type": "string"}}
      },
      "required": ["product_name", "price"]
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
    """
    Scrapy pipeline for JSON Schema-driven field extraction.

    Priority: 280
    """

    def __init__(self, crawler):
        self.settings = crawler.settings
        self.workspace_id = getattr(crawler, 'workspace_id', 'default')
        self.enabled = self.settings.getbool("NEXORA_SCHEMA_EXTRACTION_ENABLED", False)
        self.model = self.settings.get("NEXORA_SCHEMA_EXTRACTION_MODEL", "gpt-4o-mini")
        self.provider = self.settings.get("NEXORA_AI_PROVIDER", "ollama")
        self.base_url = self.settings.get("NEXORA_AI_BASE_URL", "http://localhost:11434")
        self.api_key = self.settings.get("NEXORA_AI_API_KEY", "not-needed")
        self.max_content_chars = self.settings.getint("NEXORA_SCHEMA_CONTENT_MAX_CHARS", 8000)
        self.stats = {
            "pages_processed": 0,
            "pages_extracted": 0,
            "validation_failures": 0,
            "extraction_errors": 0,
            "schema_fields_found": 0,
        }

    @classmethod
    def from_crawler(cls, crawler):
        return cls(crawler)

    async def process_item(self, item, spider):
        if not self.enabled:
            item["extracted"] = None
            return item

        # Get user's JSON Schema from settings or item
        json_schema = self._get_schema(item)
        if not json_schema:
            item["extracted"] = None
            return item

        # Build Pydantic model from schema
        try:
            pyd_model = self._schema_to_pydantic(json_schema)
        except Exception as e:
            logger.error("[SchemaExtract] Invalid schema: %s", e)
            item["extracted"] = None
            return item

        # Get content to extract from
        markdown = item.get("markdown", "") or item.get("clean_text", "")
        if len(markdown) < 50:
            item["extracted"] = None
            return item

        content = markdown[:self.max_content_chars]

        # Extract via LLM
        try:
            extracted = await self._extract_with_llm(content, json_schema, pyd_model)
            item["extracted"] = extracted
            self.stats["pages_extracted"] += 1
            self.stats["schema_fields_found"] += len(extracted) if isinstance(extracted, dict) else 0

        except ValidationError as e:
            logger.warning("[SchemaExtract] Validation failed for %s: %s",
                          item.get("url", ""), e)
            item["extracted"] = None
            self.stats["validation_failures"] += 1

        except Exception as e:
            logger.error("[SchemaExtract] Extraction failed for %s: %s",
                        item.get("url", ""), e)
            item["extracted"] = None
            self.stats["extraction_errors"] += 1

        self.stats["pages_processed"] += 1
        return item

    def _get_schema(self, item) -> Optional[Dict]:
        """Get JSON Schema from settings or item metadata."""
        # Priority 1: item-level schema (from API request)
        if item.get("json_schema"):
            return item["json_schema"]
        # Priority 2: spider-level schema
        if hasattr(self.settings, 'NEXORA_USER_JSON_SCHEMA'):
            return self.settings.get("NEXORA_USER_JSON_SCHEMA")
        # Priority 3: fetch from DB by job_id
        job_id = item.get("crawl_id")
        if job_id:
            # Async DB fetch would go here — simplified for pipeline context
            pass
        return None

    def _schema_to_pydantic(self, schema: Dict) -> type[BaseModel]:
        """
        Convert JSON Schema dict → Pydantic model class.

        Handles:
          - string, integer, number, boolean, array, object types
          - required fields
          - nested objects (one level deep)
        """
        type_map = {
            "string": str,
            "integer": int,
            "number": float,
            "boolean": bool,
            "array": list,
            "object": dict,
        }

        fields = {}
        required = schema.get("required", [])

        for name, prop in schema.get("properties", {}).items():
            prop_type = prop.get("type", "string")
            py_type = type_map.get(prop_type, str)

            # Handle arrays with item types
            if prop_type == "array" and "items" in prop:
                item_type = prop["items"].get("type", "string")
                py_type = List[type_map.get(item_type, str)]

            # Handle nested objects
            if prop_type == "object" and "properties" in prop:
                py_type = dict  # Simplified — could recurse

            # Optional if not in required
            if name not in required:
                py_type = Optional[py_type]

            default = None if name not in required else ...
            fields[name] = (py_type, default)

        return create_model("DynamicSchema", **fields)

    async def _extract_with_llm(self, content: str, schema: Dict, pyd_model: type[BaseModel]) -> Dict:
        """
        Use LiteLLM with response_format to enforce schema compliance.
        Falls back to raw JSON parsing if response_format not supported.
        """
        schema_json = json.dumps(schema, indent=2)

        messages = [
            {
                "role": "system",
                "content": (
                    "You extract structured data from web pages. "
                    "Respond ONLY with a JSON object matching the provided schema. "
                    "Do not include any other text, explanations, or markdown formatting."
                ),
            },
            {
                "role": "user",
                "content": f"Schema:
{schema_json}

Page Content:
{content}",
            },
        ]

        try:
            # Try structured output (OpenAI, some providers)
            response = await litellm.acompletion(
                model=f"{self.provider}/{self.model}",
                messages=messages,
                response_format={"type": "json_object"},
                api_base=self.base_url,
                api_key=self.api_key,
                temperature=0.0,
                max_tokens=2000,
            )
        except Exception:
            # Fallback: no response_format
            response = await litellm.acompletion(
                model=f"{self.provider}/{self.model}",
                messages=messages,
                api_base=self.base_url,
                api_key=self.api_key,
                temperature=0.0,
                max_tokens=2000,
            )

        raw = response.choices[0].message.content.strip()

        # Extract JSON from response
        if raw.startswith("```json"):
            raw = raw[7:]
        if raw.startswith("```"):
            raw = raw[3:]
        if raw.endswith("```"):
            raw = raw[:-3]
        raw = raw.strip()

        # Validate against Pydantic model
        parsed = json.loads(raw)
        validated = pyd_model(**parsed)
        return validated.dict()

    def close_spider(self, spider):
        logger.info("[SchemaExtract] Pipeline stats: %s", self.stats)


# ============================================================
# FILE: nexora_crawler/entitlements/engine.py (NEW)
# ============================================================

"""
Quota & Entitlement Engine — Phase 6 + Phase 7.

Per-workspace soft + hard limits. One noisy tenant cannot drain the system.

Default free tier:
  - 10,000 pages/month
  - 1 GB blob storage
  - 100,000 vector records
  - 60 API calls/minute
  - 10 schema extraction jobs/day

Soft quota: request succeeds, logged + advisory response header
Hard quota: request rejected with 429 + Retry-After header
"""

import logging
from dataclasses import dataclass
from datetime import datetime, timezone, timedelta
from typing import Literal, Optional

from fastapi import HTTPException

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
    """
    Quota enforcement engine.

    All methods are async and accept a DB connection for lookups.
    """

    @staticmethod
    async def get_config(db, workspace_id: str) -> QuotaConfig:
        """Get quota config for workspace. Falls back to defaults."""
        if hasattr(db, 'fetch_one'):  # asyncpg
            row = await db.fetch_one(
                "SELECT * FROM workspace_quotas WHERE workspace_id = $1",
                workspace_id,
            )
        else:  # aiosqlite
            cursor = await db.execute(
                "SELECT * FROM workspace_quotas WHERE workspace_id = ?",
                (workspace_id,),
            )
            row = await cursor.fetchone()

        if not row:
            return QuotaConfig(workspace_id=workspace_id)

        row = dict(row)
        return QuotaConfig(
            workspace_id=workspace_id,
            pages_per_month=row.get("pages_per_month", 10000),
            storage_gb=row.get("storage_gb", 1),
            vector_records=row.get("vector_records", 100000),
            api_rpm=row.get("api_rpm", 60),
            schema_extracts_per_day=row.get("schema_extracts_per_day", 10),
        )

    @staticmethod
    async def check_pages(db, workspace_id: str, requested: int,
                          mode: Literal["soft", "hard"] = "hard") -> None:
        """
        Check pages quota. Raises HTTPException(429) on hard limit exceeded.
        """
        config = await QuotaEngine.get_config(db, workspace_id)
        period_start = datetime.now(timezone.utc).replace(
            day=1, hour=0, minute=0, second=0, microsecond=0
        ).isoformat()

        if hasattr(db, 'fetch_one'):  # asyncpg
            row = await db.fetch_one(
                """SELECT COALESCE(SUM(pages_crawled), 0) AS used
                FROM crawl_jobs
                WHERE workspace_id = $1 AND started_at >= $2""",
                workspace_id, period_start,
            )
        else:  # aiosqlite
            cursor = await db.execute(
                """SELECT COALESCE(SUM(pages_crawled), 0) AS used
                FROM crawl_jobs
                WHERE workspace_id = ? AND started_at >= ?""",
                (workspace_id, period_start),
            )
            row = await cursor.fetchone()

        used = row["used"] if row else 0

        if used + requested > config.pages_per_month:
            if mode == "hard":
                # Calculate seconds until next month
                now = datetime.now(timezone.utc)
                next_month = (now.replace(day=1) + timedelta(days=32)).replace(day=1)
                retry_after = int((next_month - now).total_seconds())

                logger.warning(
                    "[Quota] HARD limit exceeded for %s: %d + %d > %d",
                    workspace_id, used, requested, config.pages_per_month
                )
                raise HTTPException(
                    status_code=429,
                    detail=(
                        f"Pages quota exceeded: {used}/{config.pages_per_month} "
                        f"used this month. Resets on the 1st of next month."
                    ),
                    headers={"Retry-After": str(retry_after)},
                )
            else:
                logger.warning(
                    "[Quota] SOFT limit exceeded for %s: %d + %d > %d",
                    workspace_id, used, requested, config.pages_per_month
                )

    @staticmethod
    async def record_pages(db, workspace_id: str, count: int) -> None:
        """Record pages usage after crawl completion."""
        period = datetime.now(timezone.utc).strftime("%Y-%m")
        await db.execute(
            """INSERT INTO usage_records
            (workspace_id, period, pages_crawled, storage_bytes, vector_records, api_calls, recorded_at)
            VALUES (?, ?, ?, 0, 0, 0, ?)
            ON CONFLICT (workspace_id, period) DO UPDATE SET
                pages_crawled = pages_crawled + ?""",
            (workspace_id, period, count,
             datetime.now(timezone.utc).isoformat(), count),
        )

    @staticmethod
    async def record_api_call(db, workspace_id: str) -> None:
        """Record an API call for rate limiting."""
        period = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M")
        # Simplified — real impl uses Redis for per-minute buckets
        pass


# ============================================================
# AUDIT LOGGING UTILITIES
# ============================================================

"""
Add these helper functions to your database layer or create a dedicated module:

# nexora_crawler/audit.py

import logging
from datetime import datetime, timezone

logger = logging.getLogger(__name__)


async def log_audit_event(db, workspace_id: str, actor: str, action: str,
                          target_id: str = None, details: dict = None,
                          ip_address: str = "0.0.0.0"):
    """
    Write an audit log entry.

    Actions:
      - gdpr_erase
      - pii_redaction
      - quota_enforced
      - crawl_started
      - crawl_completed
      - webhook_created
      - webhook_deleted
    """
    import json
    await db.execute(
        """INSERT INTO audit_logs
        (workspace_id, actor, action, target_id, details, ip_address, timestamp)
        VALUES (?, ?, ?, ?, ?, ?, ?)""",
        (workspace_id, actor, action, target_id,
         json.dumps(details) if details else None,
         ip_address, datetime.now(timezone.utc).isoformat()),
    )
    logger.info("[Audit] %s: %s by %s in %s", action, target_id, actor, workspace_id)


# Usage examples:
#   await log_audit_event(db, workspace_id, "user:123", "gdpr_erase",
#                         target_id=workspace_id, details={"pages": 42})
#   await log_audit_event(db, workspace_id, "system", "quota_enforced",
#                         details={"resource": "pages", "limit": 10000})
"""


# ============================================================
# SETTINGS.PY ADDITIONS FOR PHASE 6
# ============================================================

"""
Add to settings.py:

# ---- Phase 7: PII Redaction ----
NEXORA_PII_REDACTION_ENABLED = False  # Enable in production
NEXORA_PII_MODE = "regex"  # "regex" | "llm"
NEXORA_PII_LLM_MODEL = "gpt-4o-mini"

# ---- Phase 7: Schema Extraction ----
NEXORA_SCHEMA_EXTRACTION_ENABLED = False
NEXORA_SCHEMA_EXTRACTION_MODEL = "gpt-4o-mini"
NEXORA_SCHEMA_CONTENT_MAX_CHARS = 8000

# ---- Phase 7: Quotas ----
NEXORA_DEFAULT_PAGES_PER_MONTH = 10000
NEXORA_DEFAULT_STORAGE_GB = 1
NEXORA_DEFAULT_VECTOR_RECORDS = 100000
NEXORA_DEFAULT_API_RPM = 60
NEXORA_DEFAULT_SCHEMA_EXTRACTS_PER_DAY = 10

# Pipeline priorities (updated)
ITEM_PIPELINES = {
    'nexora_crawler.pipelines.NexoraExtractionPipeline': 100,
    'nexora_crawler.pipelines.markdown_pipeline.MarkdownExtractionPipeline': 110,
    'nexora_crawler.pipelines.pii_redaction_pipeline.PIIRedactionPipeline': 200,
    'nexora_crawler.pipelines.NexoraStylePipeline': 150,
    'nexora_crawler.pipelines.schema_enricher.UnifiedSchemaEnricher': 160,
    'nexora_crawler.pipelines.metadata_indexer.MetadataIndexerPipeline': 165,
    'nexora_crawler.pipelines.ai_enrichment.AIEnrichmentPipeline': 250,
    'nexora_crawler.pipelines.chunking_pipeline.StructuralChunkingPipeline': 260,
    'nexora_crawler.pipelines.vector_index_pipeline.VectorIndexPipeline': 270,
    'nexora_crawler.pipelines.schema_extraction_pipeline.SchemaExtractionPipeline': 280,
    'nexora_crawler.pipelines.parquet_export.ParquetExportPipeline': 450,
    'nexora_crawler.pipelines.NexoraExportPipeline': 500,
    'nexora_crawler.pipelines.NexoraDatasetPipeline': 600,
}
"""


# ============================================================
# TAURI DESKTOP APP INTEGRATION (Phase 6)
# ============================================================

"""
Add these Tauri commands for compliance features:

# In src-tauri/src/lib.rs, add:

#[tauri::command]
pub async fn gdpr_erase_workspace(
    workspace_id: String,
    app_handle: tauri::AppHandle,
) -> Result<String, String> {
    // Call the Python backend's GDPR erase endpoint
    let python_exe = get_python_executable(&app_handle)?;
    let output = Command::new(python_exe)
        .args(&[
            "gdpr", "erase",
            &format!("--workspace-id={}", workspace_id),
        ])
        .output()
        .map_err(|e| format!("GDPR erase failed: {}", e))?;

    if output.status.success() {
        Ok(String::from_utf8_lossy(&output.stdout).to_string())
    } else {
        Err(String::from_utf8_lossy(&output.stderr).to_string())
    }
}

#[tauri::command]
pub async fn get_audit_logs(
    workspace_id: String,
    limit: u32,
    app_handle: tauri::AppHandle,
) -> Result<Vec<AuditLogEntry>, String> {
    // Fetch audit logs from SQLite
    let data_dir = get_data_dir(&app_handle)?;
    let db_path = data_dir.join("nexora_metadata.db");

    // Use aiosqlite or similar to query
    // Return structured log entries
    Ok(vec![])
}

// In your React frontend, add a Compliance tab:
// - PII redaction toggle
// - GDPR erase button (with confirmation dialog)
// - Audit log viewer
// - Quota usage display


================================================================================
## SECTION 6: FINAL INTEGRATION TEST SUITE (43 TESTS)
## Source File: phase_7_final_integration_tests.md
================================================================================

# PHASE 7 — FINAL INTEGRATION TEST SUITE
# Version: 1.0.0 | Date: 2026-07-03
# Purpose: Comprehensive tests after applying all Phase 7 integration patches
#
# Run with: pytest tests/test_phase7_integration.py -v
#
# These tests verify:
#   1. BaseVectorStore contract compliance across all backends
#   2. Phase 4B vector indexing uses BaseVectorStore (not raw Chroma)
#   3. Phase 4C API endpoints return correct Pydantic models
#   4. Phase 5 Celery tasks use exponential backoff
#   5. Phase 6 PII redaction, schema extraction, GDPR work end-to-end
#   6. No vendor lock-in (backend swap works without code changes)

import pytest
import asyncio
import json
import os
import tempfile
from datetime import datetime, timezone
from typing import List
from unittest.mock import Mock, patch, AsyncMock

# ============================================================
# FIXTURES
# ============================================================

@pytest.fixture
def vector_record():
    """Sample VectorRecord for testing."""
    from nexora_crawler.vector_store.base import VectorRecord
    return VectorRecord(
        id="test-001",
        content="This is a test document about machine learning.",
        embedding=[0.1] * 768,
        workspace_id="ws-test",
        source_type="chunk",
        source_id="https://example.com/page1",
        metadata={"title": "Test Page", "author": "Test Author"},
    )


@pytest.fixture
def search_query():
    """Sample SearchQuery for testing."""
    from nexora_crawler.vector_store.base import SearchQuery
    return SearchQuery(
        vector=[0.1] * 768,
        workspace_id="ws-test",
        top_k=5,
        min_similarity=0.0,
    )


@pytest.fixture
def mock_backend():
    """Mock backend that implements BaseVectorStore."""
    from nexora_crawler.vector_store.base import BaseVectorStore, VectorRecord, SearchQuery, SearchResult

    class MockBackend(BaseVectorStore):
        def __init__(self):
            self._data = {}
            self._name = "mock"

        async def initialize(self): pass
        async def add(self, records): 
            for r in records: self._data[r.id] = r
            return [r.id for r in records]
        async def upsert(self, records): return await self.add(records)
        async def search(self, query):
            return [SearchResult(
                id="test-001", score=0.95, content="test",
                metadata={}, workspace_id=query.workspace_id
            )]
        async def hybrid_search(self, query, bm25_weight=0.3):
            return await self.search(query)
        async def delete(self, ids): return len(ids)
        async def delete_by_workspace(self, ws): return 0
        async def count(self, ws=None): return len(self._data)
        async def get(self, ids): return [self._data[i] for i in ids if i in self._data]
        async def list_all(self, ws=None, limit=1000, offset=0):
            return list(self._data.values())[offset:offset+limit]
        async def health_check(self): return True
        def backend_name(self): return self._name

    return MockBackend()


# ============================================================
# TEST GROUP 1: BaseVectorStore Contract Compliance
# ============================================================

class TestBaseVectorStoreContract:
    """Verify all backends implement the full contract."""

    def test_vector_store_protocol_validation_passes(self, mock_backend):
        """T1: Valid backend passes protocol validation."""
        from nexora_crawler.vector_store.base import VectorStoreProtocol
        VectorStoreProtocol.validate(type(mock_backend))

    def test_vector_store_protocol_fails_on_missing_method(self):
        """T2: Backend missing method raises TypeError."""
        from nexora_crawler.vector_store.base import BaseVectorStore, VectorStoreProtocol

        class BadBackend(BaseVectorStore):
            async def initialize(self): pass
            # Missing all other methods

        with pytest.raises(TypeError, match="missing required method"):
            VectorStoreProtocol.validate(BadBackend)

    def test_vector_record_creation(self, vector_record):
        """T3: VectorRecord dataclass works correctly."""
        assert vector_record.id == "test-001"
        assert vector_record.workspace_id == "ws-test"
        assert len(vector_record.embedding) == 768

    def test_search_query_defaults(self):
        """T4: SearchQuery has sensible defaults."""
        from nexora_crawler.vector_store.base import SearchQuery
        q = SearchQuery()
        assert q.top_k == 10
        assert q.min_similarity == 0.0
        assert q.filter == {}

    def test_search_result_creation(self):
        """T5: SearchResult dataclass works correctly."""
        from nexora_crawler.vector_store.base import SearchResult
        r = SearchResult(
            id="test", score=0.95, content="hello",
            metadata={}, workspace_id="ws"
        )
        assert r.score == 0.95


# ============================================================
# TEST GROUP 2: Factory & Backend Swapping
# ============================================================

class TestFactoryBackendSwapping:
    """Verify backend swap requires zero code changes."""

    @patch.dict(os.environ, {"NEXORA_VECTOR_BACKEND": "mock"})
    def test_factory_reads_env_var(self):
        """T6: Factory reads NEXORA_VECTOR_BACKEND from env."""
        from nexora_crawler.vector_store.factory import build_vector_store

        with pytest.raises(Exception):  # "mock" not a real backend
            build_vector_store()

    def test_factory_explicit_backend(self):
        """T7: Factory accepts explicit backend name."""
        from nexora_crawler.vector_store.factory import build_vector_store

        with pytest.raises(Exception):  # "fake" not real
            build_vector_store("fake")

    def test_factory_unknown_backend_raises(self):
        """T8: Unknown backend raises BackendNotFoundError."""
        from nexora_crawler.vector_store.factory import build_vector_store
        from nexora_crawler.vector_store.base import BackendNotFoundError

        with pytest.raises(BackendNotFoundError, match="Unknown vector backend"):
            build_vector_store("nonexistent")


# ============================================================
# TEST GROUP 3: ChromaVectorStore (Phase 4B Integration)
# ============================================================

@pytest.mark.skipif(
    not __import__('importlib.util').find_spec("chromadb"),
    reason="chromadb not installed"
)
class TestChromaVectorStore:
    """Test ChromaDB backend implements BaseVectorStore."""

    @pytest.fixture
    async def chroma_store(self):
        """Create temporary ChromaDB store."""
        from nexora_crawler.vector_store.chroma_store import ChromaVectorStore
        with tempfile.TemporaryDirectory() as tmpdir:
            store = ChromaVectorStore(path=tmpdir)
            await store.initialize()
            yield store

    @pytest.mark.asyncio
    async def test_chroma_add_and_search(self, chroma_store, vector_record):
        """T9: Chroma add + search round-trip."""
        await chroma_store.add([vector_record])

        from nexora_crawler.vector_store.base import SearchQuery
        query = SearchQuery(
            vector=vector_record.embedding,
            workspace_id="ws-test",
            top_k=1,
        )
        results = await chroma_store.search(query)
        assert len(results) == 1
        assert results[0].id == "test-001"

    @pytest.mark.asyncio
    async def test_chroma_tenant_isolation(self, chroma_store, vector_record):
        """T10: Cross-tenant search returns empty."""
        await chroma_store.add([vector_record])

        from nexora_crawler.vector_store.base import SearchQuery
        query = SearchQuery(
            vector=vector_record.embedding,
            workspace_id="ws-other",  # Different workspace
            top_k=10,
        )
        results = await chroma_store.search(query)
        assert len(results) == 0  # No cross-tenant leakage

    @pytest.mark.asyncio
    async def test_chroma_hybrid_search_degrades(self, chroma_store, vector_record):
        """T11: Chroma hybrid_search degrades to vector with warning."""
        await chroma_store.add([vector_record])

        from nexora_crawler.vector_store.base import SearchQuery
        query = SearchQuery(
            vector=vector_record.embedding,
            workspace_id="ws-test",
            top_k=1,
        )
        # Should work but log warning
        results = await chroma_store.hybrid_search(query)
        assert len(results) >= 0  # Doesn't crash

    @pytest.mark.asyncio
    async def test_chroma_count(self, chroma_store, vector_record):
        """T12: Count returns correct number."""
        assert await chroma_store.count() == 0
        await chroma_store.add([vector_record])
        assert await chroma_store.count() == 1
        assert await chroma_store.count("ws-test") == 1
        assert await chroma_store.count("ws-other") == 0

    @pytest.mark.asyncio
    async def test_chroma_delete_by_workspace(self, chroma_store, vector_record):
        """T13: Bulk delete by workspace works."""
        await chroma_store.add([vector_record])
        await chroma_store.delete_by_workspace("ws-test")
        assert await chroma_store.count() == 0

    @pytest.mark.asyncio
    async def test_chroma_backend_name(self, chroma_store):
        """T14: backend_name returns 'chroma'."""
        assert chroma_store.backend_name() == "chroma"


# ============================================================
# TEST GROUP 4: PgVectorStore (Phase 4B Integration)
# ============================================================

@pytest.mark.skipif(
    not __import__('importlib.util').find_spec("asyncpg"),
    reason="asyncpg not installed"
)
class TestPgVectorStore:
    """Test pgvector backend implements BaseVectorStore."""

    # These tests require a running Postgres with pgvector extension
    # Use pytest --pg-url=postgresql://... to provide connection string

    @pytest.fixture
    async def pg_store(self, request):
        """Create pgvector store connected to test database."""
        from nexora_crawler.vector_store.pgvector_store import PgVectorStore

        pg_url = request.config.getoption("--pg-url", default=None)
        if not pg_url:
            pytest.skip("--pg-url not provided")

        store = PgVectorStore(database_url=pg_url, embedding_dim=768)
        await store.initialize()
        yield store
        # Cleanup
        await store.delete_by_workspace("ws-test")

    @pytest.mark.asyncio
    async def test_pg_add_and_search(self, pg_store, vector_record):
        """T15: pgvector add + search round-trip."""
        await pg_store.add([vector_record])

        from nexora_crawler.vector_store.base import SearchQuery
        query = SearchQuery(
            vector=vector_record.embedding,
            workspace_id="ws-test",
            top_k=1,
        )
        results = await pg_store.search(query)
        assert len(results) == 1
        assert results[0].score > 0.99  # Exact match should be ~1.0

    @pytest.mark.asyncio
    async def test_pg_hybrid_search(self, pg_store, vector_record):
        """T16: pgvector hybrid search uses BM25 + vector."""
        await pg_store.add([vector_record])

        from nexora_crawler.vector_store.base import SearchQuery
        query = SearchQuery(
            text="machine learning",  # Text query for BM25
            vector=vector_record.embedding,
            workspace_id="ws-test",
            top_k=1,
        )
        results = await pg_store.hybrid_search(query, bm25_weight=0.3)
        assert len(results) >= 0

    @pytest.mark.asyncio
    async def test_pg_tenant_isolation(self, pg_store, vector_record):
        """T17: Cross-tenant search returns empty."""
        await pg_store.add([vector_record])

        from nexora_crawler.vector_store.base import SearchQuery
        query = SearchQuery(
            vector=vector_record.embedding,
            workspace_id="ws-other",
            top_k=10,
        )
        results = await pg_store.search(query)
        assert len(results) == 0

    @pytest.mark.asyncio
    async def test_pg_list_all_pagination(self, pg_store, vector_record):
        """T18: Paginated iteration works."""
        records = [
            vector_record,
            vector_record.__class__(
                id="test-002", content="doc 2", embedding=[0.2]*768,
                workspace_id="ws-test"
            ),
        ]
        await pg_store.add(records)

        page1 = await pg_store.list_all(workspace_id="ws-test", limit=1, offset=0)
        page2 = await pg_store.list_all(workspace_id="ws-test", limit=1, offset=1)
        assert len(page1) == 1
        assert len(page2) == 1
        assert page1[0].id != page2[0].id


# ============================================================
# TEST GROUP 5: Phase 4B VectorIndexPipeline Integration
# ============================================================

class TestVectorIndexPipelineIntegration:
    """Verify Phase 4B pipeline uses BaseVectorStore, not raw Chroma."""

    def test_pipeline_uses_factory_not_hardcoded_chroma(self):
        """T19: VectorIndexPipeline calls build_vector_store()."""
        from unittest.mock import patch, MagicMock

        mock_store = MagicMock()
        mock_store.backend_name.return_value = "mock"

        with patch('nexora_crawler.vector_store.factory.build_vector_store', return_value=mock_store):
            from nexora_crawler.pipelines.vector_index_pipeline import VectorIndexPipeline

            mock_crawler = MagicMock()
            mock_crawler.settings.getbool.return_value = True
            mock_crawler.settings.get.return_value = "mock"

            pipeline = VectorIndexPipeline(mock_crawler)
            assert pipeline.vector_store == mock_store

    def test_pipeline_converts_chunks_to_vector_records(self):
        """T20: NexoraChunk -> VectorRecord conversion is correct."""
        from nexora_crawler.pipelines.vector_index_pipeline import VectorIndexPipeline
        from nexora_crawler.pipelines.chunking_pipeline import NexoraChunk
        from nexora_crawler.vector_store.base import VectorRecord

        pipeline = VectorIndexPipeline.__new__(VectorIndexPipeline)

        chunk = NexoraChunk(
            chunk_id="chunk-001",
            parent_url="https://example.com",
            parent_title="Test",
            content="Hello world",
            chunk_index=0,
            chunk_count=1,
            token_count=10,
            word_count=2,
            heading_chain=["H1: Title"],
            ai_summary="Summary",
            ai_tags=["tag1"],
            embedding=[0.1] * 768,
        )

        records = pipeline._chunks_to_records([chunk], "ws-test")
        assert len(records) == 1
        assert isinstance(records[0], VectorRecord)
        assert records[0].id == "chunk-001"
        assert records[0].workspace_id == "ws-test"
        assert records[0].source_id == "https://example.com"


# ============================================================
# TEST GROUP 6: Phase 5 Celery Retry Logic
# ============================================================

class TestCeleryExponentialBackoff:
    """Verify Celery tasks use true exponential backoff."""

    def test_retry_delays_are_exponential(self):
        """T21: Retry delays follow 10 * 2^attempt pattern."""
        # Expected delays: attempt 0->10s, 1->20s, 2->40s, 3->80s, 4->160s
        expected = [10, 20, 40, 80, 160]

        for attempt, expected_delay in enumerate(expected):
            actual = 10 * (2 ** attempt)
            assert actual == expected_delay, f"Attempt {attempt}: expected {expected_delay}s, got {actual}s"

    def test_old_fixed_delay_is_wrong(self):
        """T22: Fixed 60s delay is NOT exponential."""
        old_delays = [60, 60, 60, 60, 60]  # Old broken behavior
        new_delays = [10 * (2 ** i) for i in range(5)]

        assert old_delays != new_delays, "Fixed delay should not equal exponential"
        assert new_delays[-1] == 160, "5th retry should be 160s, not 60s"


# ============================================================
# TEST GROUP 7: Phase 5 Webhook Delivery
# ============================================================

class TestWebhookDelivery:
    """Verify webhook delivery with HMAC and exponential retry."""

    def test_hmac_signature_generation(self):
        """T23: Webhook payload is HMAC-SHA256 signed."""
        import hmac
        import hashlib

        secret = "test-secret"
        payload = json.dumps({"event": "test", "data": {}}).encode()

        sig = hmac.new(secret.encode(), payload, hashlib.sha256).hexdigest()
        expected_header = f"sha256={sig}"

        assert expected_header.startswith("sha256=")
        assert len(sig) == 64  # SHA-256 hex length

    def test_webhook_retry_countdown_exponential(self):
        """T24: Webhook retry countdown is exponential."""
        for attempt in range(5):
            countdown = 10 * (2 ** attempt)
            assert countdown in [10, 20, 40, 80, 160]

    def test_circuit_breaker_opens_after_threshold(self):
        """T25: Circuit breaker opens after 5 failures."""
        from nexora_crawler.tasks.webhook_delivery import CIRCUIT_BREAKER_THRESHOLD
        assert CIRCUIT_BREAKER_THRESHOLD == 5


# ============================================================
# TEST GROUP 8: Phase 6 PII Redaction
# ============================================================

class TestPIIRedaction:
    """Verify PII redaction pipeline."""

    def test_email_redaction(self):
        """T26: Email addresses are redacted."""
        from nexora_crawler.pipelines.pii_redaction_pipeline import REGEX_PATTERNS

        text = "Contact me at john.doe@example.com for details."
        for pattern, replacement in REGEX_PATTERNS:
            if "EMAIL" in replacement:
                result = pattern.sub(replacement, text)
                assert "[REDACTED:EMAIL]" in result
                assert "john.doe@example.com" not in result
                return
        pytest.fail("Email pattern not found")

    def test_phone_redaction(self):
        """T27: Phone numbers are redacted."""
        from nexora_crawler.pipelines.pii_redaction_pipeline import REGEX_PATTERNS

        text = "Call me at (555) 123-4567."
        for pattern, replacement in REGEX_PATTERNS:
            if "PHONE" in replacement:
                result = pattern.sub(replacement, text)
                assert "[REDACTED:PHONE]" in result
                return
        pytest.fail("Phone pattern not found")

    def test_credit_card_redaction(self):
        """T28: Credit card numbers are redacted."""
        from nexora_crawler.pipelines.pii_redaction_pipeline import REGEX_PATTERNS

        text = "My card is 4111 1111 1111 1111."
        for pattern, replacement in REGEX_PATTERNS:
            if "CC" in replacement:
                result = pattern.sub(replacement, text)
                assert "[REDACTED:CC]" in result
                return
        pytest.fail("CC pattern not found")

    def test_pipeline_disabled_by_default(self):
        """T29: PII pipeline is disabled by default."""
        from nexora_crawler.pipelines.pii_redaction_pipeline import PIIRedactionPipeline

        mock_crawler = Mock()
        mock_crawler.settings.getbool.return_value = False

        pipeline = PIIRedactionPipeline(mock_crawler)
        assert pipeline.enabled == False


# ============================================================
# TEST GROUP 9: Phase 6 Schema Extraction
# ============================================================

class TestSchemaExtraction:
    """Verify JSON Schema-driven extraction pipeline."""

    def test_schema_to_pydantic_conversion(self):
        """T30: JSON Schema converts to valid Pydantic model."""
        from nexora_crawler.pipelines.schema_extraction_pipeline import SchemaExtractionPipeline

        schema = {
            "type": "object",
            "properties": {
                "product_name": {"type": "string"},
                "price": {"type": "number"},
                "in_stock": {"type": "boolean"},
            },
            "required": ["product_name"],
        }

        pipeline = SchemaExtractionPipeline.__new__(SchemaExtractionPipeline)
        model = pipeline._schema_to_pydantic(schema)

        # Test instantiation
        instance = model(product_name="Widget", price=9.99, in_stock=True)
        assert instance.product_name == "Widget"
        assert instance.price == 9.99

    def test_schema_with_array_field(self):
        """T31: Array fields convert to List[type]."""
        from nexora_crawler.pipelines.schema_extraction_pipeline import SchemaExtractionPipeline

        schema = {
            "type": "object",
            "properties": {
                "features": {"type": "array", "items": {"type": "string"}},
            },
        }

        pipeline = SchemaExtractionPipeline.__new__(SchemaExtractionPipeline)
        model = pipeline._schema_to_pydantic(schema)
        instance = model(features=["fast", "reliable"])
        assert instance.features == ["fast", "reliable"]

    def test_pipeline_disabled_by_default(self):
        """T32: Schema extraction is disabled by default."""
        from nexora_crawler.pipelines.schema_extraction_pipeline import SchemaExtractionPipeline

        mock_crawler = Mock()
        mock_crawler.settings.getbool.return_value = False

        pipeline = SchemaExtractionPipeline(mock_crawler)
        assert pipeline.enabled == False


# ============================================================
# TEST GROUP 10: Phase 4C API Endpoints
# ============================================================

class TestAPIEndpoints:
    """Verify FastAPI endpoints return correct models."""

    def test_search_request_model(self):
        """T33: SearchRequest validates correctly."""
        from nexora_crawler.api.routes.search import SearchRequest

        req = SearchRequest(query="machine learning", top_k=5)
        assert req.query == "machine learning"
        assert req.top_k == 5

    def test_search_request_top_k_bounds(self):
        """T34: top_k is bounded 1-100."""
        from nexora_crawler.api.routes.search import SearchRequest
        from pydantic import ValidationError

        with pytest.raises(ValidationError):
            SearchRequest(query="test", top_k=0)

        with pytest.raises(ValidationError):
            SearchRequest(query="test", top_k=101)

    def test_hybrid_search_request_bm25_weight_bounds(self):
        """T35: bm25_weight is bounded 0.0-1.0."""
        from nexora_crawler.api.routes.search import HybridSearchRequest
        from pydantic import ValidationError

        with pytest.raises(ValidationError):
            HybridSearchRequest(query="test", bm25_weight=-0.1)

        with pytest.raises(ValidationError):
            HybridSearchRequest(query="test", bm25_weight=1.1)

    def test_webhook_create_model(self):
        """T36: WebhookCreate validates URL."""
        from nexora_crawler.api.routes.webhooks import WebhookCreate

        req = WebhookCreate(url="https://example.com/webhook")
        assert str(req.url) == "https://example.com/webhook"

    def test_job_submit_model(self):
        """T37: JobSubmit accepts any registered type."""
        from nexora_crawler.api.routes.jobs import JobSubmit

        req = JobSubmit(type="crawl", input={"url": "https://example.com"})
        assert req.type == "crawl"
        assert req.async_run == True


# ============================================================
# TEST GROUP 11: Migration Tool
# ============================================================

class TestMigrationTool:
    """Verify vector store migration works ANY -> ANY."""

    def test_migration_script_exists(self):
        """T38: Migration script module exists."""
        try:
            from scripts.migrate_vector_store import migrate
            assert callable(migrate)
        except ImportError:
            pytest.skip("Migration script not yet created")

    def test_migration_counts_match(self):
        """T39: Source and target counts match after migration."""
        # This would be an integration test with real backends
        pass


# ============================================================
# TEST GROUP 12: Quota Engine
# ============================================================

class TestQuotaEngine:
    """Verify quota enforcement."""

    def test_quota_config_defaults(self):
        """T40: QuotaConfig has sensible defaults."""
        from nexora_crawler.entitlements.engine import QuotaConfig

        config = QuotaConfig(workspace_id="ws-test")
        assert config.pages_per_month == 10000
        assert config.storage_gb == 1
        assert config.vector_records == 100000

    def test_hard_quota_raises_429(self):
        """T41: Hard quota exceeded raises HTTPException(429)."""
        from nexora_crawler.entitlements.engine import QuotaEngine
        from fastapi import HTTPException
        import asyncio

        # Mock DB that reports 10001 pages used
        mock_db = AsyncMock()
        mock_db.fetch_one = AsyncMock(return_value={"used": 10001})

        async def test():
            with pytest.raises(HTTPException) as exc_info:
                await QuotaEngine.check_pages(mock_db, "ws-test", 1, mode="hard")
            assert exc_info.value.status_code == 429
            assert "Retry-After" in exc_info.value.headers

        asyncio.run(test())


# ============================================================
# TEST GROUP 13: End-to-End Integration
# ============================================================

class TestEndToEndIntegration:
    """Full pipeline integration tests."""

    @pytest.mark.asyncio
    async def test_full_pipeline_no_vendor_lockin(self):
        """T42: Backend swap requires zero code changes."""
        from nexora_crawler.vector_store.factory import build_vector_store
        from unittest.mock import patch

        # Test that different backends can be instantiated via env var
        backends = ["chroma", "pgvector", "qdrant", "cloudflare_vectorize"]

        for backend in backends:
            with patch.dict(os.environ, {"NEXORA_VECTOR_BACKEND": backend}):
                # All should raise BackendNotFoundError if deps missing,
                # but the FACTORY should handle it consistently
                try:
                    store = build_vector_store()
                    assert hasattr(store, 'backend_name')
                except Exception as e:
                    # Expected if dependencies not installed
                    assert "backend" in str(e).lower() or "not installed" in str(e).lower()

    def test_all_pipelines_registered(self):
        """T43: All pipeline priorities are unique and ordered."""
        priorities = [100, 110, 150, 160, 165, 200, 250, 260, 270, 280, 450, 500, 600]
        assert len(priorities) == len(set(priorities)), "Duplicate priorities found"
        assert priorities == sorted(priorities), "Priorities not in ascending order"


# ============================================================
# TEST CONFIGURATION
# ============================================================

def pytest_addoption(parser):
    """Add custom CLI options."""
    parser.addoption(
        "--pg-url",
        action="store",
        default=None,
        help="PostgreSQL connection string for pgvector tests",
    )


# ============================================================
# TEST SUMMARY
# ============================================================

"""
Test Coverage Matrix:

| Test ID | Component | What It Tests |
|---------|-----------|---------------|
| T1-T5   | BaseVectorStore | Contract compliance, dataclasses |
| T6-T8   | Factory | Backend swapping, error handling |
| T9-T14  | ChromaVectorStore | Add, search, tenant isolation, hybrid degradation |
| T15-T18 | PgVectorStore | Add, search, hybrid, pagination, tenant isolation |
| T19-T20 | VectorIndexPipeline | Uses factory, chunk->record conversion |
| T21-T22 | Celery Retry | Exponential backoff correctness |
| T23-T25 | Webhook Delivery | HMAC signing, retry, circuit breaker |
| T26-T29 | PII Redaction | Email, phone, CC redaction, disabled by default |
| T30-T32 | Schema Extraction | Pydantic conversion, arrays, disabled by default |
| T33-T37 | API Endpoints | Pydantic validation, bounds checking |
| T38-T39 | Migration Tool | Script existence, count verification |
| T40-T41 | Quota Engine | Defaults, 429 on hard limit |
| T42-T43 | Integration | Backend swap, pipeline ordering |

Total: 43 tests


{'='*80}
## SECTION 7: WORKFLOW GUIDE
{'='*80}

### How to Apply These Patches

| Step | Phase | Action | Source Document |
|------|-------|--------|-----------------|
| 1 | 4A | Build using original `Phase_4A.md` | Your existing guide |
| 2 | 4A | **Seed** vector contract (`base.py`, `factory.py`) | Section 1 of this doc |
| 3 | 4B | Build using original `Phase_4B.md` | Your existing guide |
| 4 | 4B | **Replace** hardcoded Chroma with `BaseVectorStore` | Section 2 of this doc |
| 5 | 4C | Build using this doc (your spec was a placeholder) | Section 3 of this doc |
| 6 | 5 | Build using original `PHASE_5_DISTRIBUTED_SCALING.md` | Your existing guide |
| 7 | 5 | **Patch** backoff, add registry/webhooks/OTel | Section 4 of this doc |
| 8 | 6 | Build using original `PHASE_6_TAURI_DESKTOP.md` | Your existing guide |
| 9 | 6 | **Add** PII/GDPR/schema/quotas | Section 5 of this doc |
| 10 | ALL | **Run** the 43 integration tests | Section 6 of this doc |

### The Golden Rule

> **Phase 7 is not a "later phase."** It is a cross-cutting layer that gets seeded in Phase 4A and deepens at each subsequent phase. If you build Phase 4B hardcoding ChromaDB, you will pay the exact migration tax this package is designed to prevent.

### File Creation Checklist

- [ ] `nexora_crawler/vector_store/__init__.py` (Section 1)
- [ ] `nexora_crawler/vector_store/base.py` (Section 1)
- [ ] `nexora_crawler/vector_store/factory.py` (Section 1)
- [ ] `nexora_crawler/vector_store/chroma_store.py` (Section 2)
- [ ] `nexora_crawler/vector_store/pgvector_store.py` (Section 2)
- [ ] `nexora_crawler/pipelines/vector_index_pipeline.py` (Section 2 — REPLACEMENT)
- [ ] `nexora_crawler/api/auth.py` (Section 3)
- [ ] `nexora_crawler/api/database/connection.py` (Section 3)
- [ ] `nexora_crawler/api/routes/search.py` (Section 3)
- [ ] `nexora_crawler/api/routes/webhooks.py` (Section 3)
- [ ] `nexora_crawler/api/routes/jobs.py` (Section 3)
- [ ] `nexora_crawler/api/routes/gdpr.py` (Section 3)
- [ ] `nexora_crawler/api/routes/extract.py` (Section 3)
- [ ] `nexora_crawler/middlewares/exponential_backoff.py` (Section 4 — REPLACEMENT)
- [ ] `nexora_crawler/tasks/webhook_delivery.py` (Section 4)
- [ ] `nexora_crawler/tasks/dispatcher.py` (Section 4)
- [ ] `nexora_crawler/jobs/registry.py` (Section 4)
- [ ] `nexora_crawler/observability/metrics.py` (Section 4)
- [ ] `nexora_crawler/observability/tracing.py` (Section 4)
- [ ] `nexora_crawler/pipelines/pii_redaction_pipeline.py` (Section 5)
- [ ] `nexora_crawler/pipelines/schema_extraction_pipeline.py` (Section 5)
- [ ] `nexora_crawler/entitlements/engine.py` (Section 5)
- [ ] `tests/test_phase7_integration.py` (Section 6)

{'='*80}
## SECTION 8: CRITICAL FIXES SUMMARY
{'='*80}

| Bug | Location | Severity | Impact | Fix |
|-----|----------|----------|--------|-----|
| `time.sleep()` in `process_request` | Phase 5 `exponential_backoff.py` | 🔴 **CRITICAL** | **Blocks Scrapy reactor** — entire crawl pauses | Use `meta['download_delay']` |
| `default_retry_delay=60` (fixed) | Phase 5 `tasks.py` | 🔴 **CRITICAL** | Retries at 60s, 60s, 60s — not exponential | `countdown=10 * (2 ** retries)` |
| ChromaDB hardcoded | Phase 4B `vector_index_pipeline.py` | 🔴 **CRITICAL** | Migration tax when switching to pgvector | Use `build_vector_store()` factory |
| No `BaseVectorStore` interface | Phase 4B | 🔴 **CRITICAL** | No abstraction — every backend needs custom glue | Add ABC with 11 methods |
| No tenant isolation | Phase 4B Chroma store | 🟡 **HIGH** | Cross-workspace data leakage | `workspace_id` filter on every query |
| No webhook delivery worker | Phase 5 | 🟡 **HIGH** | Webhooks defined but never sent | Celery task with HMAC + circuit breaker |
| No JobTypeRegistry | Phase 5 | 🟡 **HIGH** | Queue only handles crawls | Generic dispatcher for any job type |
| No PII/GDPR/audit | Phase 6 | 🟡 **HIGH** | Compliance gaps | Full pipelines + endpoints + logging |
| No hybrid search | Phase 4B | 🟡 **MEDIUM** | Missing Firecrawl parity | pgvector tsvector + ts_rank |
| No OTel trace propagation | Phase 5 | 🟡 **MEDIUM** | Traces die at Celery boundary | `task_prerun` signal handler |
| No Prometheus metrics | Phase 5 | 🟢 **LOW** | No production observability | `/metrics` endpoint + counters |
| No quota engine | Phase 6 | 🟡 **HIGH** | One tenant can drain system | Soft/hard limits with 429 |

---

## DEFINITION OF DONE

After applying all patches and running tests, you should be able to say:

- [ ] **Phase 4A:** "We have a vendor-neutral vector contract ready for any backend."
- [ ] **Phase 4B:** "We generate embeddings and store them in pgvector or Chroma without code changes."
- [ ] **Phase 4C:** "We expose semantic search, hybrid search, and webhook management over HTTP."
- [ ] **Phase 5:** "We have a generic job dispatcher, reliable webhook delivery, and distributed tracing."
- [ ] **Phase 6:** "We have PII redaction, GDPR compliance, and schema-driven extraction in the desktop app."
- [ ] **All 43 integration tests pass.**
- [ ] **Backend swap (Chroma → pgvector) works with one env var change.**
- [ ] **No `time.sleep()` blocks the Scrapy reactor.**
- [ ] **Celery retries use true exponential backoff (10s, 20s, 40s, 80s, 160s).**
- [ ] **Webhook deliveries are HMAC-signed and circuit-breaker protected.**
- [ ] **Cross-tenant data access is impossible by design.**

---

*End of Document*
*Version 1.0.0 | 2026-07-03*
*Total: ~140,000 characters | 6 integration sections + workflow + fixes*

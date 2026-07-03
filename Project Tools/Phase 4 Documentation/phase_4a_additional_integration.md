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

"""
BaseVectorStore — vendor-neutral vector storage contract.
Added in Phase 4A so Phase 4B can implement against it from day one.
Prevents the Chroma→Supabase migration tax .
"""

from abc import ABC, abstractmethod # used for defining abstract base classes and methods
from dataclasses import dataclass, field #used for creating data classes and defining default values for fields
from typing import List, Dict, Any, Optional #used for type hinting, including lists, dictionaries, and optional values
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
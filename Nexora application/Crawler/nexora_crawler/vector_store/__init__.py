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

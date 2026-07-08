"""
Storage Abstraction Layer — Phase 4A
======================================
Defines abstract base classes for all storage backends.
All pipeline components depend on these interfaces, never on concrete implementations.

This enables seamless switching between:
  - Local: SQLite (metadata) + ChromaDB (vectors) + local files (exports)
  - Cloud: Supabase PostgreSQL + pgvector + S3 buckets

Usage:
    from nexora_crawler.storage.base import BaseMetadataStore, BaseVectorStore
    from nexora_crawler.storage.local_sqlite import LocalMetadataStore
    from nexora_crawler.storage.chroma_vector import ChromaVectorStore

    meta = LocalMetadataStore(db_path="./data/metadata.db")
    vector = ChromaVectorStore(collection_name="nexora_chunks")
"""

from abc import ABC, abstractmethod
from typing import Any, Dict, List, Optional, Tuple


class BaseMetadataStore(ABC):
    """Abstract interface for relational metadata storage."""

    @abstractmethod
    async def connect(self) -> None:
        """Initialize database connection and create schema if needed."""
        ...

    @abstractmethod
    async def close(self) -> None:
        """Close database connection gracefully."""
        ...

    @abstractmethod
    async def save_record(self, record: Dict[str, Any]) -> str:
        """
        Insert or update a NexoraRecord in the metadata store.
        Returns the record_id.
        """
        ...

    @abstractmethod
    async def get_record(self, record_id: str) -> Optional[Dict[str, Any]]:
        """Retrieve a single record by ID."""
        ...

    @abstractmethod
    async def get_record_by_url(self, url: str) -> Optional[Dict[str, Any]]:
        """Retrieve a single record by URL."""
        ...

    @abstractmethod
    async def search_records(
        self,
        domain: Optional[str] = None,
        website_type: Optional[str] = None,
        language: Optional[str] = None,
        tags: Optional[List[str]] = None,
        query: Optional[str] = None,
        limit: int = 100,
        offset: int = 0,
    ) -> List[Dict[str, Any]]:
        """
        Search records with optional filters.
        Returns list of record dicts ordered by recency.
        """
        ...

    @abstractmethod
    async def count_records(
        self,
        domain: Optional[str] = None,
        website_type: Optional[str] = None,
    ) -> int:
        """Count records matching filters."""
        ...

    @abstractmethod
    async def save_job(
        self,
        job_id: str,
        url: str,
        strategy: str = "single",
        status: str = "pending",
    ) -> None:
        """
        Track a crawl job in the metadata store.
        Used by Phase 4C async task queue.
        """
        ...

    @abstractmethod
    async def update_job(
        self,
        job_id: str,
        status: str,
        pages_crawled: Optional[int] = None,
        chunks_generated: Optional[int] = None,
    ) -> None:
        """Update crawl job status."""
        ...

    @abstractmethod
    async def get_job(self, job_id: str) -> Optional[Dict[str, Any]]:
        """Get crawl job details."""
        ...


class BaseVectorStore(ABC):
    """
    Abstract interface for vector storage and semantic search.
    
    .. deprecated:: Phase 4A
        The canonical vector store interface is now :class:`nexora_crawler.vector_store.base.BaseVectorStore`.
        This legacy class remains for backward compatibility with Phase 4A pipelines but has a reduced/method-incompatible surface.
        New code must import from ``nexora_crawler.vector_store.base`` and implement against that contract.
    """

    @abstractmethod
    async def connect(self) -> None:
        """Initialize vector store connection."""
        ...

    @abstractmethod
    async def close(self) -> None:
        """Close vector store connection."""
        ...

    @abstractmethod
    async def add_chunks(
        self,
        chunks: List[Dict[str, Any]],
        embeddings: List[List[float]],
    ) -> int:
        """
        Add chunks with embeddings to the vector store.
        Returns number of chunks added.
        """
        ...

    @abstractmethod
    async def search(
        self,
        query_embedding: List[float],
        n_results: int = 10,
        filters: Optional[Dict[str, Any]] = None,
        min_score: float = 0.5,
    ) -> List[Tuple[Dict[str, Any], float]]:
        """
        Semantic search by embedding vector.
        Returns list of (chunk_dict, score) tuples.
        """
        ...

    @abstractmethod
    async def search_by_text(
        self,
        query_text: str,
        n_results: int = 10,
        filters: Optional[Dict[str, Any]] = None,
        min_score: float = 0.5,
    ) -> List[Tuple[Dict[str, Any], float]]:
        """
        Semantic search by query text (embeddings generated internally).
        Returns list of (chunk_dict, score) tuples.
        """
        ...

    @abstractmethod
    async def delete_chunks(self, chunk_ids: List[str]) -> int:
        """Delete chunks by ID. Returns number deleted."""
        ...

    @abstractmethod
    async def get_collection_stats(self) -> Dict[str, Any]:
        """Get collection statistics (count, dimension, etc.)."""
        ...

    @abstractmethod
    async def count(self) -> int:
        """Total number of chunks in the store."""
        ...
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
        try:
            from chromadb.config import Settings  # chromadb < 0.5
        except ImportError:
            from chromadb.settings import Settings  # chromadb >= 0.5

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
        import chromadb
        try:
            self._collection = self._client.get_collection(self._collection_name)
        except (ValueError, chromadb.errors.NotFoundError):
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
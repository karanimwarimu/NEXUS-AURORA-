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
:::::::::::::::::::::



 The Ultimate Recommendation for NexoraIf you want the pipeline to be fast, free, and lightweight on your computer, the best path isn't picking only one provider. It is split-hosting them based on what they excel at:For Embeddings (Free & Fast): Use Hugging Face’s Serverless Inference API (like your RAG pipeline does). Small embedding models like all-MiniLM-L6-v2 or bge-small are completely free on Hugging Face, run on their cloud GPUs, and process text instantly without draining your laptop's battery.  For the LLM / Text Generation:If you have a strong Mac (M1/M2/M3 with 16GB+ RAM) or an Nvidia RTX GPU, use Ollama locally for llama3. It is private, unmetered, and free.If your computer is a standard lightweight laptop, spend $2 on an OpenAI API key and use gpt-4o-mini. It will cost less than a cup of coffee for thousands of pages of text processing and won't freeze your computer.so, the best setup is: Hugging Face for embeddings + Ollama (local) or OpenAI (cloud) for LLM. This way, you get the best of both worlds: free, fast embeddings and powerful text generation without overloading your machine.
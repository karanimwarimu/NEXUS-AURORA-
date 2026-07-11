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

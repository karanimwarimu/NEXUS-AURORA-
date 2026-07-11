
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

    async def open_spider(self):
        if self.enabled:
            await self.vector_store.initialize()
            logger.info("[VectorIndex] Backend: %s", self.vector_store.backend_name())

    async def process_item(self, item):
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

    def close_spider(self):
        logger.info("[VectorIndex] Stats: %s", self.stats)
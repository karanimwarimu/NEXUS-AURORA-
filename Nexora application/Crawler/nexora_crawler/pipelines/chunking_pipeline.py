#Crawler/nexora_crawler/pipelines/chunking_pipeline.py
# Chunking Pipeline — Phase 4B
# Splits clean Markdown into ~512-token semantic chunks.
# Preserves heading hierarchy, splits at paragraph boundaries.
# Priority: 260


import logging
import re
from typing import List, Dict
from dataclasses import dataclass, field
import uuid

from nexora_crawler.AI_Utilities.embedding_engine import UnifiedEmbeddingEngine

logger = logging.getLogger(__name__)


def _estimate_tokens(text: str) -> int:
    """Estimate token count from characters (4.5 chars ≈ 1 English token).

    Single source of truth for the heuristic — always returns an int
    (floor-dividing by the float 4.5 used to leak floats into token_count).
    """
    return int(len(text) / 4.5)


@dataclass
class NexoraChunk:
    """A single LLM-ready chunk of content."""
    chunk_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    parent_url: str = ""
    parent_title: str = ""
    content: str = ""
    chunk_index: int = 0
    chunk_count: int = 1
    token_count: int = 0
    word_count: int = 0
    heading_chain: List[str] = field(default_factory=list)
    source_type: str = "chunk"  # matches VectorRecord.source_type; a NexoraChunk is always a "chunk"

    # Inherit from parent record
    ai_summary: str = ""
    ai_tags: List[str] = field(default_factory=list)
    # Embedding is generated per-chunk or inherited from parent
    embedding: List[float] = field(default_factory=list)


class StructuralChunkingPipeline:
    """
    Scrapy pipeline that chunks Markdown into ~512-token pieces.
    Splits at paragraph boundaries first, then sentences.
    Preserves heading context in each chunk.
    """

    def __init__(self, crawler):
        self.settings = crawler.settings
        self.chunk_size = self.settings.getint('NEXORA_CHUNK_SIZE', 512)
        self.chunk_overlap = self.settings.getint('NEXORA_CHUNK_OVERLAP', 128)

        self.embeddings_enabled = self.settings.getbool('NEXORA_EMBEDDINGS_ENABLED', False)
        if self.embeddings_enabled:
            self.embedding_engine = UnifiedEmbeddingEngine(
                provider=self.settings.get('NEXORA_AI_PROVIDER', 'ollama'),
                model=self.settings.get('NEXORA_AI_EMBEDDING_MODEL', 'nomic-embed-text'),
                base_url=self.settings.get('NEXORA_AI_BASE_URL', 'http://localhost:11434'),
                api_key=self.settings.get('NEXORA_AI_API_KEY', 'not-needed'),
                timeout=self.settings.getint('NEXORA_AI_TIMEOUT', 30),
                max_concurrent=self.settings.getint('NEXORA_AI_MAX_CONCURRENT', 3),
                failfast_threshold=self.settings.getint('NEXORA_AI_FAILFAST_THRESHOLD', 3),
                fallback_provider=self.settings.get('NEXORA_AI_FALLBACK_PROVIDER', ''),
                fallback_model=self.settings.get('NEXORA_AI_FALLBACK_MODEL', ''),
                fallback_base_url=self.settings.get('NEXORA_AI_FALLBACK_BASE_URL', ''),
                fallback_api_key=self.settings.get('NEXORA_AI_FALLBACK_API_KEY', ''),
            )
        else:
            self.embedding_engine = None

        self.stats = {
            "pages_chunked": 0,
            "chunks_generated": 0,
            "embeddings_generated": 0,
            "avg_chunk_tokens": 0,
        }

    @classmethod
    def from_crawler(cls, crawler):
        return cls(crawler)

    async def process_item(self, item):
        markdown = item.get("markdown", "")
        if not markdown or len(markdown) < 100:
            item["chunk_count"] = 0
            item["chunk_ids"] = []
            return item

        try:
            chunks = self._chunk_markdown(
                markdown=markdown,
                url=item.get("url", ""),
                title=item.get("title", ""),
                ai_summary=item.get("ai_summary", ""),
                ai_tags=item.get("ai_tags", []),
            )

            # Generate per-chunk embeddings (replaces inherited page-level embedding)
            if self.embeddings_enabled and self.embedding_engine and chunks:
                if getattr(self.embedding_engine, "_breaker_open", False):
                    logger.info(
                        "[Chunking] Embedding breaker open — skipping embeddings for %s",
                        item.get("url", ""),
                    )
                else:
                    contents = [c.content[:4000] for c in chunks if c.content]
                    if contents:
                        embeddings = await self.embedding_engine.embed_batch(contents)
                        for chunk, emb in zip(chunks, embeddings):
                            if emb:
                                chunk.embedding = emb
                                self.stats["embeddings_generated"] += 1

            item["chunk_count"] = len(chunks)
            item["chunk_ids"] = [c.chunk_id for c in chunks]
            item["chunks"] = chunks  # Store for VectorIndexPipeline

            self.stats["pages_chunked"] += 1
            self.stats["chunks_generated"] += len(chunks)

            logger.info("[Chunking] %s → %d chunks",
                       item.get("url", "")[:50], len(chunks))

        except Exception as exc:
            logger.error("[Chunking] Failed for %s: %s",
                        item.get("url", ""), exc)
            item["chunk_count"] = 0
            item["chunk_ids"] = []

        return item

    def _chunk_markdown(self, markdown: str, url: str, title: str,
                        ai_summary: str, ai_tags: List[str]) -> List[NexoraChunk]:
        """
        Split markdown into semantic chunks.

        Strategy:
        1. Split by headings (##, ###) to preserve structure
        2. Within each section, split by paragraphs
        3. If paragraph > chunk_size, split by sentences
        4. Add overlap between chunks
        """
        # Estimate tokens (4.5 chars ≈ 1 token for English; avoids under-splitting)
        estimated_tokens = _estimate_tokens(markdown)

        if estimated_tokens <= self.chunk_size:
            # Single chunk — no splitting needed
            return [NexoraChunk(
                parent_url=url,
                parent_title=title,
                content=markdown,
                chunk_index=0,
                chunk_count=1,
                token_count=estimated_tokens,
                word_count=len(markdown.split()),
                ai_summary=ai_summary,
                ai_tags=ai_tags,
            )]

        # Split by headings first
        heading_pattern = re.compile(r'^(#{1,6}\s+.+)$', re.MULTILINE)
        sections = heading_pattern.split(markdown)

        chunks = []
        current_chunk = []
        current_tokens = 0
        current_headings = []
        chunk_index = 0

        for section in sections:
            if not section.strip():
                continue

            # Check if this is a heading
            if section.startswith('#'):
                current_headings = self._extract_heading_chain(section)
                continue

            # Split section into paragraphs
            paragraphs = section.split('\n\n')

            for para in paragraphs:
                para = para.strip()
                if not para:
                    continue

                para_tokens = _estimate_tokens(para)

                if current_tokens + para_tokens > self.chunk_size and current_chunk:
                    # Save current chunk
                    chunk_text = '\n\n'.join(current_chunk)
                    chunks.append(NexoraChunk(
                        parent_url=url,
                        parent_title=title,
                        content=chunk_text,
                        chunk_index=chunk_index,
                        heading_chain=list(current_headings),
                        token_count=_estimate_tokens(chunk_text),
                        word_count=len(chunk_text.split()),
                        ai_summary=ai_summary,
                        ai_tags=ai_tags,
                    ))
                    chunk_index += 1

                    # Start new chunk with overlap
                    overlap_text = self._get_overlap_text(current_chunk, self.chunk_overlap)
                    current_chunk = [overlap_text] if overlap_text else []
                    current_tokens = _estimate_tokens(overlap_text) if overlap_text else 0

                current_chunk.append(para)
                current_tokens += para_tokens

        # Last chunk — chunk_count set in fix-up loop below
        if current_chunk:
            chunk_text = '\n\n'.join(current_chunk)
            chunks.append(NexoraChunk(
                parent_url=url,
                parent_title=title,
                content=chunk_text,
                chunk_index=chunk_index,
                heading_chain=list(current_headings),
                token_count=_estimate_tokens(chunk_text),
                word_count=len(chunk_text.split()),
                ai_summary=ai_summary,
                ai_tags=ai_tags,
            ))

        # Update chunk_count for all chunks
        for i, chunk in enumerate(chunks):
            chunk.chunk_count = len(chunks)
            chunk.chunk_index = i

        return chunks

    def _extract_heading_chain(self, heading_text: str) -> List[str]:
        """Extract heading hierarchy from markdown heading."""
        lines = heading_text.strip().split('\n')
        headings = []
        for line in lines:
            match = re.match(r'^(#{1,6})\s+(.+)$', line.strip())
            if match:
                level = len(match.group(1))
                text = match.group(2).strip()
                headings.append(f"H{level}: {text}")
        return headings

    def _get_overlap_text(self, chunks: List[str], overlap_tokens: int) -> str:
        """Get last ~overlap_tokens from previous chunk for context overlap."""
        text = '\n\n'.join(chunks)
        words = text.split()
        overlap_words = words[-min(len(words), overlap_tokens * 3):]
        return ' '.join(overlap_words)

    def close_spider(self):
        spider = getattr(getattr(self, "crawler", None), "spider", None)
        if self.stats["chunks_generated"] > 0:
            logger.info("[Chunking] Pipeline stats: %s", self.stats)
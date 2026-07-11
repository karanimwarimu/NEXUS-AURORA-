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

logger = logging.getLogger(__name__)


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

        self.stats = {
            "pages_chunked": 0,
            "chunks_generated": 0,
            "avg_chunk_tokens": 0,
        }

    @classmethod
    def from_crawler(cls, crawler):
        return cls(crawler)

    async def process_item(self, item, spider):
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
                ai_embedding=item.get("ai_embedding", []),
            )

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
                        ai_summary: str, ai_tags: List[str],
                        ai_embedding: List[float]) -> List[NexoraChunk]:
        """
        Split markdown into semantic chunks.

        Strategy:
        1. Split by headings (##, ###) to preserve structure
        2. Within each section, split by paragraphs
        3. If paragraph > chunk_size, split by sentences
        4. Add overlap between chunks
        """
        # Estimate tokens (4 chars ≈ 1 token)
        estimated_tokens = len(markdown) // 4

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
                embedding=ai_embedding,  # Inherit parent embedding
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

                para_tokens = len(para) // 4

                if current_tokens + para_tokens > self.chunk_size and current_chunk:
                    # Save current chunk
                    chunk_text = '\n\n'.join(current_chunk)
                    chunks.append(NexoraChunk(
                        parent_url=url,
                        parent_title=title,
                        content=chunk_text,
                        chunk_index=chunk_index,
                        heading_chain=list(current_headings),
                        token_count=len(chunk_text) // 4,
                        word_count=len(chunk_text.split()),
                        ai_summary=ai_summary,
                        ai_tags=ai_tags,
                        embedding=ai_embedding,
                    ))
                    chunk_index += 1

                    # Start new chunk with overlap
                    overlap_text = self._get_overlap_text(current_chunk, self.chunk_overlap)
                    current_chunk = [overlap_text] if overlap_text else []
                    current_tokens = len(overlap_text) // 4 if overlap_text else 0

                current_chunk.append(para)
                current_tokens += para_tokens

        # Last chunk
        if current_chunk:
            chunk_text = '\n\n'.join(current_chunk)
            chunks.append(NexoraChunk(
                parent_url=url,
                parent_title=title,
                content=chunk_text,
                chunk_index=chunk_index,
                chunk_count=len(chunks) + 1,
                heading_chain=list(current_headings),
                token_count=len(chunk_text) // 4,
                word_count=len(chunk_text.split()),
                ai_summary=ai_summary,
                ai_tags=ai_tags,
                embedding=ai_embedding,
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

    def close_spider(self, spider):
        if self.stats["chunks_generated"] > 0:
            self.stats["avg_chunk_tokens"] = int(round(
                sum(c.token_count for c in getattr(spider, '_chunks', [])) 
                / self.stats["chunks_generated"], 1
            ))
        logger.info("[Chunking] Pipeline stats: %s", self.stats)
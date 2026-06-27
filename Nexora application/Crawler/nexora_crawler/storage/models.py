"""
Nexora Storage Models — Phase 4A Enriched Schema
=================================================
Defines the unified data record that travels through the entire pipeline:
  Spider → Extractors → Pipeline → Storage → Export → LLM

This is the SINGLE source of truth for Nexora's data shape.
All components import from here — no scattered field definitions.

Key principles:
  1. Every field has a well-defined default (never None where avoidable).
  2. Enriched schema fields (entities, price_change_delta, quality_scores)
     always present as empty payloads rather than omitted.
  3. Dataclass-based for clarity; convertible to/from Scrapy Item, JSON, Parquet.
"""

import uuid
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional


# ── Standardized entity payloads ────────────────────────────────────────────

@dataclass
class EntityExtraction:
    """
    Captures structured entities extracted from a page.
    Always present on NexoraRecord — defaults to empty lists/None.
    """
    prices: List[float] = field(default_factory=list)
    currency: Optional[str] = None
    tickers: List[str] = field(default_factory=list)
    product_names: List[str] = field(default_factory=list)
    dates: List[str] = field(default_factory=list)
    emails: List[str] = field(default_factory=list)
    phone_numbers: List[str] = field(default_factory=list)
    addresses: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class QualityScores:
    """
    Quality and duplication metrics for a page.
    Always present on NexoraRecord — defaults to reasonable values.
    """
    readability: float = 0.0          # 0.0-1.0 — text density / markup ratio
    duplication_score: float = 0.0    # 0.0-1.0 — higher = more duplicated
    compression_ratio: float = 0.0    # gzip compression ratio (proxy for entropy)
    token_count_estimate: int = 0     # rough token count (chars / 4)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class StyleAnalysis:
    """
    Visual and technical style analysis of a page.
    Populated by the existing NexoraStylePipeline.
    """
    dominant_colors: List[str] = field(default_factory=list)
    tech_stack: List[str] = field(default_factory=list)
    framework: Optional[str] = None
    theme: Optional[str] = None
    layout: Optional[str] = None
    fonts: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


# ── Primary data record ─────────────────────────────────────────────────────

@dataclass
class NexoraRecord:
    """
    The SINGLE enriched data record for every crawled page.

    This is what travels through the entire Phase 4A → 4B → 4C pipeline.
    It consolidates:
      - Raw crawl metadata (url, timestamp, status)
      - Extracted content (markdown, clean_text)
      - Structural analysis (style_analysis, quality_scores)
      - Entity extraction (prices, tickers, entities)
      - AI enrichment placeholders (ai_summary, ai_tags, embedding)
      - Storage references (chunk_ids, saved_paths)

    Every field has a default — no field is ever missing from the record.
    """
    # ── Identity ────────────────────────────────────────────────────────
    record_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    crawl_id: str = ""
    url: str = ""
    domain: str = ""
    title: str = ""
    timestamp: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    # ── Content ─────────────────────────────────────────────────────────
    raw_html: str = ""
    markdown_content: str = ""
    clean_text: str = ""

    # ── Metadata ────────────────────────────────────────────────────────
    website_type: str = "unknown"           # e-commerce, blog, docs, saas, news, etc.
    language: str = ""
    content_type: str = "web_page"
    status_code: int = 0
    response_time_ms: float = 0.0
    playwright_used: bool = False

    # ── Structural Analysis ─────────────────────────────────────────────
    style_analysis: StyleAnalysis = field(default_factory=StyleAnalysis)
    quality_scores: QualityScores = field(default_factory=QualityScores)
    structured_schema: Dict[str, Any] = field(default_factory=dict)  # JSON-LD/Microdata
    social_graphs: Dict[str, Any] = field(default_factory=dict)      # OG/Twitter cards

    # ── Entity Extraction ──────────────────────────────────────────────
    entities: EntityExtraction = field(default_factory=EntityExtraction)
    price_change_delta: Optional[float] = None  # real-time price tracking
    image_assets: List[Dict[str, Any]] = field(default_factory=list)
    video_assets: List[Dict[str, Any]] = field(default_factory=list)

    # ── AI Enrichments (populated by Phase 4B) ─────────────────────────
    ai_summary: str = ""
    ai_tags: List[str] = field(default_factory=list)
    ai_entities: List[str] = field(default_factory=list)
    embedding: List[float] = field(default_factory=list)
    embedding_model: str = ""

    # ── Pipeline tracking ──────────────────────────────────────────────
    chunk_count: int = 0
    chunk_ids: List[str] = field(default_factory=list)
    has_embedding: bool = False
    vector_db_collection: str = ""

    # ── Storage references ─────────────────────────────────────────────
    saved_json_path: str = ""
    saved_csv_path: str = ""
    saved_parquet_path: str = ""
    saved_markdown_path: str = ""

    # ── Serialization ──────────────────────────────────────────────────

    def to_dict(self) -> Dict[str, Any]:
        """Convert to flat dict, expanding nested dataclasses."""
        result = {}
        for key, value in asdict(self).items():
            if isinstance(value, dict) and any(
                k in value for k in ("readability", "prices", "dominant_colors")
            ):
                # Nested dataclasses already expanded by asdict
                result[key] = value
            else:
                result[key] = value
        return result

    def to_enriched_dict(self) -> Dict[str, Any]:
        """
        Return the enriched schema dict as defined in the Phase 4A spec.
        This is the canonical output format — always has all keys.
        """
        return {
            "url": self.url,
            "title": self.title,
            "timestamp": self.timestamp,
            "crawl_id": self.crawl_id,
            "domain": self.domain,
            "website_type": self.website_type,
            "language": self.language,
            "status_code": self.status_code,
            "markdown_content": self.markdown_content,
            "clean_text": self.clean_text,
            "ai_summary": self.ai_summary,
            "ai_tags": self.ai_tags,
            "style_analysis": self.style_analysis.to_dict(),
            "entities": self.entities.to_dict(),
            "price_change_delta": self.price_change_delta,
            "quality_scores": self.quality_scores.to_dict(),
            "structured_schema": self.structured_schema,
            "social_graphs": self.social_graphs,
            "image_assets": self.image_assets,
            "video_assets": self.video_assets,
            "chunk_count": self.chunk_count,
            "chunk_ids": self.chunk_ids,
            "has_embedding": self.has_embedding,
        }

    @classmethod
    def from_scrapy_item(cls, item: Any) -> "NexoraRecord":
        """Convert a Scrapy NexoraPageItem into a NexoraRecord."""
        return cls(
            url=getattr(item, "url", ""),
            domain=cls._extract_domain(getattr(item, "url", "")),
            title=getattr(item, "title", ""),
            timestamp=getattr(item, "crawled_at", datetime.now(timezone.utc).isoformat()),
            raw_html=getattr(item, "html", ""),
            clean_text=getattr(item, "clean_text", ""),
            language=getattr(item, "language_iso", "") or getattr(item, "language", ""),
            status_code=getattr(item, "status", 0),
            response_time_ms=float(getattr(item, "response_time_ms", 0) or 0),
            playwright_used=bool(getattr(item, "playwright_used", False)),
            style_analysis=cls._parse_style(getattr(item, "styles", {})),
            structured_schema=getattr(item, "structured_schema", {}),
            social_graphs=getattr(item, "social_graphs", {}),
            image_assets=getattr(item, "image_assets", []),
            quality_scores=QualityScores(
                readability=cls._calculate_readability(getattr(item, "html", "")),
                token_count_estimate=len(getattr(item, "clean_text", "") or "") // 4,
            ),
        )

    @staticmethod
    def _extract_domain(url: str) -> str:
        if "//" in url:
            return url.split("/")[2]
        return url

    @staticmethod
    def _parse_style(styles: Any) -> StyleAnalysis:
        if not styles or not isinstance(styles, dict):
            return StyleAnalysis()
        return StyleAnalysis(
            dominant_colors=styles.get("dominant_colors", []),
            tech_stack=styles.get("tech_stack", []),
            framework=styles.get("framework"),
            theme=styles.get("theme"),
            layout=styles.get("layout"),
            fonts=styles.get("fonts", []),
        )

    @staticmethod
    def _calculate_readability(html: str) -> float:
        """Simple readability heuristic: text-to-markup ratio."""
        if not html:
            return 0.0
        import re
        text = re.sub(r'<[^>]+>', ' ', html)
        text = re.sub(r'\s+', ' ', text).strip()
        return round(len(text) / max(len(html), 1), 4)


# ── LLM-Ready Chunk (used by Phase 4B) ─────────────────────────────────────

@dataclass
class NexoraChunk:
    """
    A single LLM-ready chunk of content derived from a NexoraRecord.
    This is the unit of retrieval for RAG queries.
    """
    chunk_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    record_id: str = ""
    url: str = ""
    domain: str = ""
    title: str = ""
    heading_chain: str = ""           # "H1 > H2 > H3" for structural context

    content: str = ""                 # chunked text (~512 tokens)
    chunk_index: int = 0
    chunk_count: int = 1
    token_count: int = 0

    embedding: List[float] = field(default_factory=list)
    embedding_model: str = ""

    # Metadata for filtering
    language: str = ""
    website_type: str = ""
    crawled_at: str = ""
    quality_score: float = 1.0

    # AI enrichment at chunk level
    summary: str = ""
    tags: List[str] = field(default_factory=list)

    def to_llm_context(self) -> str:
        """Format for LLM context window insertion (RAG prompt)."""
        header = f"Source: {self.url}\nTitle: {self.title}"
        if self.heading_chain:
            header += f"\nSection: {self.heading_chain}"
        if self.summary:
            header += f"\nSummary: {self.summary}"
        if self.tags:
            header += f"\nTags: {', '.join(self.tags[:5])}"
        return header + "\n\n---\n\n" + self.content

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)
# models.py — Unified Schema Dataclass
#Priority: 160 (after StylePipeline at 150, before Phase 4B at 250)
#Purpose: Ensure every item conforms to the unified schema with defaults.
# Every record must conform(items added in phase 4a). Missing fields populated with defaults.

from typing import List, Dict, Any, Optional
from dataclasses import dataclass, field


@dataclass
class NexoraUnifiedRecord:
    # — Identity —
    url: str = ""
    title: str = ""
    domain: str = ""

    # — Temporal —
    timestamp: str = ""           # ISO 8601 UTC
    crawl_id: str = ""          # UUID of crawl job

    # — Content —
    markdown: str = ""            # Clean Markdown (primary)
    clean_text: str = ""        # Fallback plain text
    html_length: int = 0
    markdown_word_count: int = 0
    token_reduction_pct: float = 0.0

    # — AI Enrichment (populated by Phase 4B) —
    ai_summary: str = ""        # 2-3 sentence summary
    ai_tags: List[str] = field(default_factory=list)
    ai_embedding: List[float] = field(default_factory=list)

    # — Entities —
    entities: Dict[str, Any] = field(default_factory=lambda: {
        "prices": [],
        "currency": "",
        "tickers": [],
        "products": [],
        "people": [],
        "organizations": [],
    })
    price_change_delta: Optional[float] = None

    # — Style Analysis —
    style_analysis: Dict[str, Any] = field(default_factory=lambda: {
        "dominant_colors": [],
        "tech_stack": [],
        "css_framework": "",
        "theme": "",
        "fonts": [],
    })

    # — Quality Scores —
    quality_scores: Dict[str, float] = field(default_factory=lambda: {
        "readability": 0.0,
        "duplication_score": 0.0,
        "text_density": 0.0,
        "crawl_quality": 1.0,
    })

    # — Multimodal —
    image_assets: List[Dict] = field(default_factory=list)
    video_assets: List[Dict] = field(default_factory=list)
    total_images: int = 0
    total_videos: int = 0
    has_hero_image: bool = False

    # — Metadata —
    language: str = ""
    website_type: str = "unknown"  # article, product, docs, blog, etc.
    extraction_method: str = ""

    # — Provenance —
    spider_name: str = ""
    depth: int = 0
    playwright_used: bool = False

    def to_dict(self) -> Dict[str, Any]:
        from dataclasses import asdict
        return asdict(self)

    def to_parquet_row(self) -> Dict[str, Any]:
        import json
        d = self.to_dict()
        # Flatten nested dicts to JSON strings for Parquet
        d["entities_json"] = json.dumps(d.pop("entities"))
        d["style_analysis_json"] = json.dumps(d.pop("style_analysis"))
        d["quality_scores_json"] = json.dumps(d.pop("quality_scores"))
        d["image_assets_json"] = json.dumps(d.pop("image_assets"))
        d["video_assets_json"] = json.dumps(d.pop("video_assets"))
        d["ai_tags_json"] = json.dumps(d.pop("ai_tags"))
        d["ai_embedding_json"] = json.dumps(d.pop("ai_embedding"))
        # Remove heavy text fields (stored separately)
        d.pop("markdown", None)
        d.pop("clean_text", None)
        return d
# markdown_pipeline.py
# MarkdownExtractionPipeline — Phase 4A Core
# Converts raw HTML to clean Markdown using Trafilatura.
# Also extracts multimodal assets (images, videos) inline.
# Priority: 110

import logging
import trafilatura
from Extractor.multimodal_extractor import MultimodalAssetExtractor

logger = logging.getLogger(__name__)


class MarkdownExtractionPipeline:
    """
    Scrapy pipeline converting HTML → clean Markdown.
    Uses Trafilatura for intelligent boilerplate removal.
    Preserves tables, links; strips nav, footers, ads.
    Also extracts multimodal asset metadata (images, videos) inline.
    """

    def __init__(self):
        self.stats = {
            "pages_processed": 0,
            "markdown_generated": 0,
            "extraction_failures": 0,
            "avg_token_reduction": 0.0,
        }
        self.asset_extractor = MultimodalAssetExtractor()

    @classmethod
    def from_crawler(cls, crawler):
        return cls()

    def _extract_multimodal(self, item, html):
        """Extract image/video assets and set item fields."""
        assets = self.asset_extractor.extract(html, item.get("url", ""))
        item["image_assets"] = assets["images"]
        item["video_assets"] = assets["videos"]
        item["total_images"] = assets["total_images"]
        item["total_videos"] = assets["total_videos"]
        item["has_hero_image"] = assets["has_hero_image"]

    async def process_item(self, item, spider):
        html = item.get("html", "")
        if not html:
            item["markdown"] = ""
            item["extraction_method"] = "no_html"
            self._extract_multimodal(item, html)
            return item

        try:
            markdown = trafilatura.extract(
                html,
                output_format="markdown",
                include_comments=False,
                include_tables=True,
                include_images=False,      # Images handled by MultimodalAssetExtractor
                include_links=True,
                deduplicate=True,
                url=item.get("url", ""),
            )

            if markdown and len(markdown.strip()) > 50:
                item["markdown"] = markdown.strip()
                item["markdown_word_count"] = len(markdown.split())
                item["extraction_method"] = "trafilatura"

                # Token reduction metric
                raw_tokens = len(html) / 4
                clean_tokens = len(markdown) / 4
                if raw_tokens > 0:
                    item["token_reduction_pct"] = round(
                        (1 - clean_tokens / raw_tokens) * 100, 1
                    )

                self.stats["markdown_generated"] += 1
            else:
                # Fallback: use clean_text if Trafilatura fails
                clean_text = item.get("clean_text", "")
                item["markdown"] = clean_text
                item["markdown_word_count"] = len(clean_text.split()) if clean_text else 0
                item["extraction_method"] = "trafilatura_fallback_to_clean_text"
                item["token_reduction_pct"] = 0.0

            # Extract multimodal assets (always available from raw HTML)
            self._extract_multimodal(item, html)
            self.stats["pages_processed"] += 1

        except Exception as exc:
            logger.error("[MarkdownPipeline] Extraction failed for %s: %s",
                        item.get("url", "unknown"), exc)
            item["markdown"] = item.get("clean_text", "")
            item["extraction_method"] = "error_fallback"
            item["token_reduction_pct"] = 0.0
            # Still try to extract multimodal from raw HTML
            self._extract_multimodal(item, html)
            self.stats["extraction_failures"] += 1

        return item

    def close_spider(self, spider):
        logger.info("[MarkdownPipeline] Stats: %s", self.stats)
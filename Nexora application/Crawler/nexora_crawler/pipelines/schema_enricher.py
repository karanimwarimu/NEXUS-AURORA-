# schema_enricher.py
# UnifiedSchemaEnricher — Phase 4A
# Ensures every item conforms to the unified schema.
# Runs after StylePipeline (150), before Phase 4B (250).
# Priority: 160

import logging
from datetime import datetime, timezone

logger = logging.getLogger(__name__)


class UnifiedSchemaEnricher:
    """
    Scrapy pipeline that enforces the unified schema.
    Populates defaults, validates types, adds temporal fields.
    """

    def __init__(self):
        self.stats = {"items_enriched": 0, "defaults_applied": 0}
        self.crawler = None

    @classmethod
    def from_crawler(cls, crawler):
        obj = cls()
        obj.crawler = crawler
        return obj

    async def process_item(self, item):
        spider = getattr(self.crawler, 'spider', None)
        # Ensure crawl_id
        if not item.get("crawl_id"):
            item["crawl_id"] = getattr(spider, "crawl_id", "") if spider else ""

        # Ensure timestamp
        if not item.get("timestamp"):
            item["timestamp"] = datetime.now(timezone.utc).isoformat()

        # Ensure domain
        if not item.get("domain"):
            url = item.get("url", "")
            item["domain"] = url.split("/")[2] if "//" in url else ""

        # Ensure entities with defaults
        if not item.get("entities"):
            item["entities"] = {
                "prices": [],
                "currency": "",
                "tickers": [],
                "products": [],
                "people": [],
                "organizations": [],
            }
            self.stats["defaults_applied"] += 1

        # Ensure style_analysis with defaults
        if not item.get("style_analysis"):
            item["style_analysis"] = {
                "dominant_colors": [],
                "tech_stack": [],
                "css_framework": "",
                "theme": "",
                "fonts": [],
            }

        # Ensure quality_scores with defaults
        if not item.get("quality_scores"):
            item["quality_scores"] = {
                "readability": 0.0,
                "duplication_score": 0.0,
                "text_density": 0.0,
                "crawl_quality": 1.0,
            }

        # Ensure website_type classification
        if not item.get("website_type"):
            item["website_type"] = self._classify_website_type(item)

        self.stats["items_enriched"] += 1
        return item

    def _classify_website_type(self, item) -> str:
        """Heuristic classification of page type."""
        url = item.get("url", "").lower()
        markdown = item.get("markdown", "")
        title = item.get("title", "").lower()

        if any(x in url for x in ["/product", "/item", "/shop", "/store", "/cart"]):
            return "e-commerce"
        if any(x in title for x in ["blog", "article", "post", "news"]):
            return "blog"
        if any(x in url for x in ["/docs", "/documentation", "/api", "/guide"]):
            return "documentation"
        if item.get("entities", {}).get("prices"):
            return "e-commerce"
        if len(markdown) > 2000 and "##" in markdown:
            return "article"
        return "unknown"

    def close_spider(self):
        spider = getattr(self.crawler, 'spider', None)
        spider_name = getattr(spider, 'name', None) if spider else 'unknown'
        logger.info("[SchemaEnricher] Stats for %s: %s", spider_name, self.stats)
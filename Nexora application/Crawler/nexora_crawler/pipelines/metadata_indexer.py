# metadata_indexer.py
# MetadataIndexerPipeline — Phase 4A
# Scrapy pipeline that indexes items into MetadataStore (SQLite).
# Priority: 165 (after UnifiedSchemaEnricher at 160)

import logging

from nexora_crawler.storage.local_sqlite import MetadataStore

logger = logging.getLogger(__name__)


class MetadataIndexerPipeline:
    """
    Scrapy pipeline that persists each item to the SQLite MetadataStore.
    Runs after UnifiedSchemaEnricher so all unified schema fields are populated.
    """

    def __init__(self, crawler):
        self.crawler = crawler
        self.store = MetadataStore(
            db_path=crawler.settings.get('NEXORA_METADATA_DB', './data/nexora_metadata.db')
        )
        self.stats = {"indexed": 0, "failed": 0}

    @classmethod
    def from_crawler(cls, crawler):
        obj = cls(crawler)
        obj.crawler = crawler
        return obj

    async def process_item(self, item):
        success = self.store.insert_page(dict(item))
        if success:
            self.stats["indexed"] += 1
        else:
            self.stats["failed"] += 1
        return item

    def close_spider(self):
        spider = getattr(self.crawler, 'spider', None)
        spider_name = getattr(spider, 'name', None) if spider else 'unknown'
        logger.info("[MetadataIndexer] Stats for %s: %s", spider_name, self.stats)
        stats = self.store.get_stats()
        logger.info("[MetadataStore] DB stats: %s", stats)
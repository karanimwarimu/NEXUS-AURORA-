#File: nexora_crawler/storage/local_sqlite.py

#Purpose: Relational metadata storage for fast filtering and analytics
# MetadataStore — Phase 4A Unified Relational Storage
# SQLite-backed metadata for fast filtering and analytics.
# Uses the unified schema. Replaces old Phase 3B metadata_store.py.

import os
import json
import logging
import sqlite3
from typing import List, Dict

logger = logging.getLogger(__name__)


class MetadataStore:
    """
    SQLite metadata store with unified schema.
    Tables: pages, crawl_jobs
    """

    def __init__(self, db_path: str = "./data/nexora_metadata.db"):
        self.db_path = db_path
        os.makedirs(os.path.dirname(db_path) or ".", exist_ok=True)
        self._init_schema()

    def _init_schema(self):
        with sqlite3.connect(self.db_path) as conn:
            conn.executescript("""
                CREATE TABLE IF NOT EXISTS pages (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    url TEXT NOT NULL UNIQUE,
                    domain TEXT NOT NULL,
                    title TEXT,
                    timestamp TEXT NOT NULL,
                    crawl_id TEXT NOT NULL,
                    markdown_preview TEXT,
                    markdown_word_count INTEGER DEFAULT 0,
                    token_reduction_pct REAL DEFAULT 0.0,
                    ai_summary TEXT,
                    ai_tags_json TEXT,
                    entities_json TEXT DEFAULT '{}',
                    price_change_delta REAL,
                    style_analysis_json TEXT DEFAULT '{}',
                    quality_scores_json TEXT DEFAULT '{}',
                    image_assets_json TEXT DEFAULT '[]',
                    video_assets_json TEXT DEFAULT '[]',
                    total_images INTEGER DEFAULT 0,
                    total_videos INTEGER DEFAULT 0,
                    has_hero_image INTEGER DEFAULT 0,
                    language TEXT,
                    website_type TEXT DEFAULT 'unknown',
                    extraction_method TEXT,
                    spider_name TEXT,
                    depth INTEGER DEFAULT 0,
                    playwright_used INTEGER DEFAULT 0,
                    created_at TEXT DEFAULT (datetime('now'))
                );

                CREATE INDEX IF NOT EXISTS idx_pages_domain ON pages(domain);
                CREATE INDEX IF NOT EXISTS idx_pages_crawl_id ON pages(crawl_id);
                CREATE INDEX IF NOT EXISTS idx_pages_website_type ON pages(website_type);
                CREATE INDEX IF NOT EXISTS idx_pages_timestamp ON pages(timestamp);
                CREATE INDEX IF NOT EXISTS idx_pages_language ON pages(language);

                CREATE TABLE IF NOT EXISTS crawl_jobs (
                    job_id TEXT PRIMARY KEY,
                    url TEXT NOT NULL,
                    strategy TEXT DEFAULT 'whole-website',
                    max_pages INTEGER DEFAULT 100,
                    status TEXT DEFAULT 'running',
                    pages_crawled INTEGER DEFAULT 0,
                    pages_failed INTEGER DEFAULT 0,
                    started_at TEXT NOT NULL,
                    completed_at TEXT,
                    error TEXT
                );
            """)
            conn.commit()
        logger.info("[MetadataStore] Schema initialized at %s", self.db_path)

    def insert_page(self, item: dict) -> bool:
        try:
            with sqlite3.connect(self.db_path) as conn:
                conn.execute("""
                    INSERT OR REPLACE INTO pages (
                        url, domain, title, timestamp, crawl_id,
                        markdown_preview, markdown_word_count, token_reduction_pct,
                        ai_summary, ai_tags_json, entities_json, price_change_delta,
                        style_analysis_json, quality_scores_json,
                        image_assets_json, video_assets_json,
                        total_images, total_videos, has_hero_image,
                        language, website_type, extraction_method,
                        spider_name, depth, playwright_used
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, (
                    item.get("url", ""),
                    item.get("domain", ""),
                    item.get("title", ""),
                    item.get("timestamp", ""),
                    item.get("crawl_id", ""),
                    item.get("markdown", "")[:500],
                    item.get("markdown_word_count", 0),
                    item.get("token_reduction_pct", 0.0),
                    item.get("ai_summary", ""),
                    json.dumps(item.get("ai_tags", [])),
                    json.dumps(item.get("entities", {})),
                    item.get("price_change_delta"),
                    json.dumps(item.get("style_analysis", {})),
                    json.dumps(item.get("quality_scores", {})),
                    json.dumps(item.get("image_assets", [])),
                    json.dumps(item.get("video_assets", [])),
                    item.get("total_images", 0),
                    item.get("total_videos", 0),
                    1 if item.get("has_hero_image") else 0,
                    item.get("language", ""),
                    item.get("website_type", "unknown"),
                    item.get("extraction_method", ""),
                    item.get("spider_name", ""),
                    item.get("depth", 0),
                    1 if item.get("playwright_used") else 0,
                ))
                conn.commit()
            return True
        except Exception as exc:
            logger.error("[MetadataStore] Insert failed for %s: %s",
                        item.get("url", ""), exc)
            return False

    def query_by_domain(self, domain: str, limit: int = 100) -> List[Dict]:
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.execute(
                "SELECT * FROM pages WHERE domain = ? ORDER BY timestamp DESC LIMIT ?",
                (domain, limit)
            )
            return [dict(row) for row in cursor.fetchall()]

    def query_by_crawl_id(self, crawl_id: str) -> List[Dict]:
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.execute(
                "SELECT * FROM pages WHERE crawl_id = ? ORDER BY timestamp DESC",
                (crawl_id,)
            )
            return [dict(row) for row in cursor.fetchall()]

    def get_stats(self) -> Dict:
        with sqlite3.connect(self.db_path) as conn:
            total = conn.execute("SELECT COUNT(*) FROM pages").fetchone()[0]
            domains = conn.execute(
                "SELECT COUNT(DISTINCT domain) FROM pages"
            ).fetchone()[0]
            return {"total_pages": total, "unique_domains": domains}
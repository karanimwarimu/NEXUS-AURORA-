#File: nexora_crawler/storage/local_sqlite.py

#Purpose: Relational metadata storage for fast filtering and analytics
# MetadataStore — Phase 4A Unified Relational Storage
# SQLite-backed metadata for fast filtering and analytics.
# Uses the unified schema. Replaces old Phase 3B metadata_store.py.

import os
import json
import logging
import sqlite3
from typing import List, Dict, Optional

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
                    markdown TEXT,
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
        # Non-destructive migration for databases created before the
        # `markdown` column existed (they used `markdown_preview`).
        self._migrate_schema(conn)
        logger.info("[MetadataStore] Schema initialized at %s", self.db_path)

    def _migrate_schema(self, conn):
        """Reconcile the `pages` table with the current schema without data loss.

        Handles the rename markdown_preview -> markdown (Step 2 of the rework):
        old DBs still expose `markdown_preview`, which breaks insert_page's
        reference to `markdown`.
        """
        cols = {row[1] for row in conn.execute("PRAGMA table_info(pages)").fetchall()}
        if "markdown" in cols:
            return
        if "markdown_preview" in cols:
            try:
                conn.execute("ALTER TABLE pages RENAME COLUMN markdown_preview TO markdown")
                logger.info("[MetadataStore] Migrated markdown_preview -> markdown")
            except sqlite3.OperationalError:
                conn.execute("ALTER TABLE pages ADD COLUMN markdown TEXT")
                conn.execute("UPDATE pages SET markdown = markdown_preview")
                logger.info("[MetadataStore] Added markdown column (copied from markdown_preview)")
        else:
            conn.execute("ALTER TABLE pages ADD COLUMN markdown TEXT")
            logger.info("[MetadataStore] Added markdown column")
        conn.commit()

    def insert_page(self, item: dict) -> bool:
        try:
            with sqlite3.connect(self.db_path) as conn:
                conn.execute("""
                    INSERT OR REPLACE INTO pages (
                        url, domain, title, timestamp, crawl_id,
                        markdown, markdown_word_count, token_reduction_pct,
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
                    item.get("markdown", ""),
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

    def update_enrichment(self, url: str, ai_summary: str, ai_tags: List) -> bool:
        """Persist AI enrichment results back onto an already-saved page row.

        Writes to the existing `ai_summary` / `ai_tags_json` columns so the
        offline `enrich` command and eager-mode crawls share the same fields.
        """
        try:
            with sqlite3.connect(self.db_path) as conn:
                conn.execute(
                    "UPDATE pages SET ai_summary = ?, ai_tags_json = ? WHERE url = ?",
                    (ai_summary or "", json.dumps(ai_tags or []), url)
                )
                conn.commit()
            return True
        except Exception as exc:
            logger.error("[MetadataStore] update_enrichment failed for %s: %s",
                         url, exc)
            return False

    @staticmethod
    def _limit_clause(limit: Optional[int]):
        """Return (sql_suffix, params) for an optional LIMIT.

        limit=None means "no limit" — the clause is omitted entirely.
        (Binding None into `LIMIT ?` raises sqlite3.IntegrityError.)
        """
        if limit is None:
            return "", ()
        return " LIMIT ?", (int(limit),)

    def get_unenriched_pages(self, limit: Optional[int] = None) -> List[Dict]:
        """Return saved pages that have not been enriched yet.

        A page counts as unenriched when its `ai_summary` is still empty
        (the crawler never sets it inline in on_demand mode, and the offline
        `enrich` command fills it in once vectors/summary are produced).
        limit=None returns all unenriched pages.
        """
        suffix, extra = self._limit_clause(limit)
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.execute(
                "SELECT * FROM pages "
                "WHERE ai_summary IS NULL OR ai_summary = '' "
                "ORDER BY timestamp DESC" + suffix,
                extra
            )
            return [dict(row) for row in cursor.fetchall()]

    def query_by_domain(self, domain: str, limit: Optional[int] = None) -> List[Dict]:
        suffix, extra = self._limit_clause(limit)
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.execute(
                "SELECT * FROM pages WHERE domain = ? ORDER BY timestamp DESC" + suffix,
                (domain,) + extra
            )
            return [dict(row) for row in cursor.fetchall()]

    def query_by_crawl_id(self, crawl_id: str, limit: Optional[int] = None) -> List[Dict]:
        suffix, extra = self._limit_clause(limit)
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.execute(
                "SELECT * FROM pages WHERE crawl_id = ? ORDER BY timestamp DESC" + suffix,
                (crawl_id,) + extra
            )
            return [dict(row) for row in cursor.fetchall()]

    def query_by_url(self, url: str) -> List[Dict]:
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.execute(
                "SELECT * FROM pages WHERE url = ? ORDER BY timestamp DESC",
                (url,)
            )
            return [dict(row) for row in cursor.fetchall()]

    def get_stats(self) -> Dict:
        with sqlite3.connect(self.db_path) as conn:
            total = conn.execute("SELECT COUNT(*) FROM pages").fetchone()[0]
            domains = conn.execute(
                "SELECT COUNT(DISTINCT domain) FROM pages"
            ).fetchone()[0]
            return {"total_pages": total, "unique_domains": domains}
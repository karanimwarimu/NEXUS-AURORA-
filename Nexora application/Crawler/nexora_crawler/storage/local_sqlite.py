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

from nexora_crawler.settings import NEXORA_METADATA_DB

logger = logging.getLogger(__name__)


class MetadataStore:
    """
    SQLite metadata store with unified schema.
    Tables: pages, crawl_jobs
    """

    def __init__(self, db_path: str = None):
        self.db_path = db_path or NEXORA_METADATA_DB
        os.makedirs(os.path.dirname(self.db_path) or ".", exist_ok=True)
        self._init_schema()

    def _init_schema(self):
        # Run non-destructive migrations FIRST so that ALTER TABLE / backfill
        # happens before any DDL that references the new columns. Without this
        # ordering, an existing database crashes on the CREATE INDEX statements
        # below because the column does not exist yet.
        self._migrate_schema()

        with sqlite3.connect(self.db_path) as conn:
            conn.executescript("""
                CREATE TABLE IF NOT EXISTS pages (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    url TEXT NOT NULL UNIQUE,
                    domain TEXT NOT NULL,
                    title TEXT,
                    timestamp TEXT NOT NULL,
                    crawl_id TEXT NOT NULL,
                    workspace_id TEXT DEFAULT 'default',
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
                CREATE INDEX IF NOT EXISTS idx_pages_workspace_id ON pages(workspace_id);
                CREATE INDEX IF NOT EXISTS idx_pages_website_type ON pages(website_type);
                CREATE INDEX IF NOT EXISTS idx_pages_timestamp ON pages(timestamp);
                CREATE INDEX IF NOT EXISTS idx_pages_language ON pages(language);

                CREATE TABLE IF NOT EXISTS crawl_jobs (
                    job_id TEXT PRIMARY KEY,
                    workspace_id TEXT DEFAULT 'default',
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

                -- Phase 4C: Webhooks
                CREATE TABLE IF NOT EXISTS webhooks (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    workspace_id TEXT NOT NULL,
                    url TEXT NOT NULL,
                    event_types TEXT NOT NULL,
                    secret TEXT NOT NULL,
                    is_active INTEGER DEFAULT 1,
                    created_at TEXT DEFAULT (datetime('now'))
                );
                CREATE INDEX IF NOT EXISTS idx_webhooks_workspace ON webhooks(workspace_id);

                -- Phase 4C: Webhook delivery log
                CREATE TABLE IF NOT EXISTS webhook_deliveries (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    webhook_id INTEGER NOT NULL,
                    job_id TEXT,
                    event_type TEXT,
                    status_code INTEGER,
                    attempt INTEGER DEFAULT 0,
                    delivered_at TEXT,
                    error TEXT,
                    FOREIGN KEY (webhook_id) REFERENCES webhooks(id)
                );
                CREATE INDEX IF NOT EXISTS idx_webhook_deliveries_webhook ON webhook_deliveries(webhook_id);

                -- Phase 4C: Workspace quotas
                CREATE TABLE IF NOT EXISTS workspace_quotas (
                    workspace_id TEXT PRIMARY KEY,
                    pages_per_month INTEGER DEFAULT 10000,
                    storage_gb INTEGER DEFAULT 1,
                    vector_records INTEGER DEFAULT 100000,
                    api_rpm INTEGER DEFAULT 60,
                    schema_extracts_per_day INTEGER DEFAULT 10,
                    updated_at TEXT DEFAULT (datetime('now'))
                );

                -- Phase 4C: Usage tracking
                CREATE TABLE IF NOT EXISTS usage_records (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    workspace_id TEXT NOT NULL,
                    period TEXT NOT NULL,
                    pages_crawled INTEGER DEFAULT 0,
                    storage_bytes INTEGER DEFAULT 0,
                    vector_records INTEGER DEFAULT 0,
                    api_calls INTEGER DEFAULT 0,
                    recorded_at TEXT DEFAULT (datetime('now')),
                    UNIQUE(workspace_id, period)
                );
                CREATE INDEX IF NOT EXISTS idx_usage_workspace_period ON usage_records(workspace_id, period);

                -- Phase 4C: Audit logs
                CREATE TABLE IF NOT EXISTS audit_logs (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    workspace_id TEXT NOT NULL,
                    actor TEXT NOT NULL,
                    action TEXT NOT NULL,
                    target_id TEXT,
                    details TEXT,
                    ip_address TEXT,
                    timestamp TEXT DEFAULT (datetime('now'))
                );
                CREATE INDEX IF NOT EXISTS idx_audit_workspace ON audit_logs(workspace_id);
                CREATE INDEX IF NOT EXISTS idx_audit_action ON audit_logs(action);
                CREATE INDEX IF NOT EXISTS idx_audit_timestamp ON audit_logs(timestamp);

                -- Phase 4C: Extraction schemas (for schema-driven crawls)
                CREATE TABLE IF NOT EXISTS extraction_schemas (
                    job_id TEXT PRIMARY KEY,
                    workspace_id TEXT NOT NULL,
                    schema_json TEXT NOT NULL,
                    created_at TEXT NOT NULL
                );
                CREATE INDEX IF NOT EXISTS idx_extraction_schemas_workspace ON extraction_schemas(workspace_id);

                -- Phase 4C: API keys for service account auth
                CREATE TABLE IF NOT EXISTS api_keys (
                    id TEXT PRIMARY KEY,
                    workspace_id TEXT NOT NULL,
                    key_hash TEXT NOT NULL,
                    name TEXT,
                    is_active INTEGER DEFAULT 1,
                    created_at TEXT DEFAULT (datetime('now'))
                );
                CREATE INDEX IF NOT EXISTS idx_api_keys_workspace ON api_keys(workspace_id);
            """)
            conn.commit()
        logger.info("[MetadataStore] Schema initialized at %s", self.db_path)

    def _migrate_schema(self):
        """Reconcile the `pages` and `crawl_jobs` tables with the current schema
        without data loss.

        Handles:
        - rename markdown_preview -> markdown (Step 2 of the rework)
        - add workspace_id column to pages and crawl_jobs (Phase 4C integration)
        """
        with sqlite3.connect(self.db_path) as conn:
            # Check if tables exist FIRST. Only run migrations on existing tables.
            cursor = conn.execute("SELECT name FROM sqlite_master WHERE type='table'")
            existing_tables = {row[0] for row in cursor.fetchall()}
            
            # Only migrate if pages table exists (fresh DB doesn't need migration)
            if "pages" not in existing_tables:
                logger.debug("[MetadataStore] Fresh database detected - skipping migrations")
                return
            
            # --- pages table migrations ---
            cols = {row[1] for row in conn.execute("PRAGMA table_info(pages)").fetchall()}

            if "markdown" not in cols:
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

            if "workspace_id" not in cols:
                conn.execute("ALTER TABLE pages ADD COLUMN workspace_id TEXT DEFAULT 'default'")
                conn.execute("UPDATE pages SET workspace_id = 'default' WHERE workspace_id IS NULL")
                logger.info("[MetadataStore] Added workspace_id column to pages (backfilled 'default')")

            # --- crawl_jobs table migrations ---
            job_cols = {row[1] for row in conn.execute("PRAGMA table_info(crawl_jobs)").fetchall()}
            if "workspace_id" not in job_cols:
                conn.execute("ALTER TABLE crawl_jobs ADD COLUMN workspace_id TEXT DEFAULT 'default'")
                conn.execute("UPDATE crawl_jobs SET workspace_id = 'default' WHERE workspace_id IS NULL")
                logger.info("[MetadataStore] Added workspace_id column to crawl_jobs (backfilled 'default')")

            conn.commit()

    def insert_page(self, item: dict) -> bool:
        try:
            with sqlite3.connect(self.db_path) as conn:
                conn.execute("""
                    INSERT OR REPLACE INTO pages (
                        url, domain, title, timestamp, crawl_id, workspace_id,
                        markdown, markdown_word_count, token_reduction_pct,
                        ai_summary, ai_tags_json, entities_json, price_change_delta,
                        style_analysis_json, quality_scores_json,
                        image_assets_json, video_assets_json,
                        total_images, total_videos, has_hero_image,
                        language, website_type, extraction_method,
                        spider_name, depth, playwright_used
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, (
                    item.get("url", ""),
                    item.get("domain", ""),
                    item.get("title", ""),
                    item.get("timestamp", ""),
                    item.get("crawl_id", ""),
                    item.get("workspace_id", "default"),
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

    def create_api_key(self, key_id: str, workspace_id: str, key_hash: str, name: str = "") -> bool:
        try:
            with sqlite3.connect(self.db_path) as conn:
                conn.execute(
                    "INSERT INTO api_keys (id, workspace_id, key_hash, name) VALUES (?, ?, ?, ?)",
                    (key_id, workspace_id, key_hash, name),
                )
                conn.commit()
            return True
        except Exception as exc:
            logger.error("[MetadataStore] create_api_key failed: %s", exc)
            return False

    def list_api_keys(self, workspace_id: str) -> List[Dict]:
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.execute(
                "SELECT id, workspace_id, name, is_active, created_at FROM api_keys WHERE workspace_id = ? ORDER BY created_at DESC",
                (workspace_id,),
            )
            return [dict(row) for row in cursor.fetchall()]

    def revoke_api_key(self, key_id: str, workspace_id: str) -> bool:
        try:
            with sqlite3.connect(self.db_path) as conn:
                conn.execute(
                    "UPDATE api_keys SET is_active = 0 WHERE id = ? AND workspace_id = ?",
                    (key_id, workspace_id),
                )
                conn.commit()
            return True
        except Exception as exc:
            logger.error("[MetadataStore] revoke_api_key failed: %s", exc)
            return False

    def get_api_key_hash(self, key_id: str) -> Optional[str]:
        with sqlite3.connect(self.db_path) as conn:
            row = conn.execute(
                "SELECT key_hash FROM api_keys WHERE id = ? AND is_active = 1",
                (key_id,),
            ).fetchone()
            return row[0] if row else None

    def get_api_key_by_id(self, key_id: str, active_only: bool = True) -> Optional[Dict]:
        """
        Retrieve API key by ID.
        
        Args:
            key_id: API key ID (first part of the key_id.raw_key format)
            active_only: If True, only return active keys (default: True for security)
        
        Returns:
            Dict with key metadata (id, workspace_id, name, is_active, created_at)
            or None if not found / inactive.
        """
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            query = "SELECT id, workspace_id, name, is_active, created_at FROM api_keys WHERE id = ?"
            params = [key_id]
            
            if active_only:
                query += " AND is_active = 1"
            
            row = conn.execute(query, params).fetchone()
            return dict(row) if row else None
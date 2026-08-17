"""
nexora_crawler/api/database/connection.py
==========================================
Async database connection — Phase 4C + Phase 7.

Supports SQLite (dev) and Postgres (prod) via DATABASE_URL env var.
Uses aiosqlite for SQLite, asyncpg for Postgres.

This module points to NEXORA_METADATA_DB (the same file used by
local_sqlite.py) to prevent data divergence between the Scrapy pipelines
and the API routes.
"""

import os
import logging
from typing import Optional

logger = logging.getLogger(__name__)

# Resolve against the same anchored path logic as settings.py
from nexora_crawler.settings import NEXORA_METADATA_DB  # noqa: E402

# Default to the unified metadata DB path
DATABASE_URL = os.getenv("NEXORA_DATABASE_URL", f"sqlite+aiosqlite:///{NEXORA_METADATA_DB}")
_db = None


async def get_db():
    """Get async database connection. Singleton pattern."""
    global _db
    if _db is not None:
        return _db

    if DATABASE_URL.startswith("postgresql") or DATABASE_URL.startswith("postgres"):
        import asyncpg
        _db = await asyncpg.create_pool(DATABASE_URL, min_size=2, max_size=10)
        logger.info("[DB] Connected to Postgres")
    else:
        import aiosqlite
        # aiosqlite doesn't have connection pools, so we return a connection
        db_path = DATABASE_URL.replace("sqlite+aiosqlite:///", "")
        _db = await aiosqlite.connect(db_path)
        _db.row_factory = aiosqlite.Row
        logger.info("[DB] Connected to SQLite at %s", db_path)

    return _db


async def close_db():
    """Close database connection."""
    global _db
    if _db is not None:
        if hasattr(_db, 'close'):
            await _db.close()
        _db = None
        logger.info("[DB] Connection closed")

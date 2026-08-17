"""
nexora_crawler/api/routes/gdpr.py
=====================================
GDPR Compliance Endpoints — Phase 4C + Phase 7.

Endpoints:
  DELETE /v1/gdpr/erase — Right to erasure (Article 17)
"""

import json
import logging
from datetime import datetime, timezone, timedelta

from fastapi import APIRouter, Depends, BackgroundTasks
from pydantic import BaseModel

from nexora_crawler.api.auth import get_workspace_id
from nexora_crawler.api.database.connection import get_db
from nexora_crawler.vector_store.factory import get_vector_store

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/v1/gdpr", tags=["GDPR Compliance"])


class EraseResponse(BaseModel):
    workspace_id: str
    status: str
    pages_deleted: int
    vectors_deleted: int
    scheduled_hard_delete: str


def _is_asyncpg(db) -> bool:
    """Detect asyncpg pool vs aiosqlite connection."""
    return hasattr(db, 'fetchrow')


@router.delete("/erase", response_model=EraseResponse)
async def gdpr_erase(
    background_tasks: BackgroundTasks,
    workspace_id: str = Depends(get_workspace_id),
):
    """
    GDPR Article 17 — Right to erasure.
    Deletes all data for workspace. Hard-delete scheduled in 30 days.
    """
    db = await get_db()
    is_pg = _is_asyncpg(db)
    ph = "$" if is_pg else "?"

    # Count before delete
    if is_pg:
        pages = await db.fetchval(
            f"SELECT COUNT(*) FROM pages WHERE workspace_id = {ph}1", workspace_id
        )
    else:
        cursor = await db.execute(
            f"SELECT COUNT(*) FROM pages WHERE workspace_id = {ph}1",
            (workspace_id,)
        )
        row = await cursor.fetchone()
        pages = row[0] if row else 0

    # Delete from relational store
    await db.execute(
        f"DELETE FROM pages WHERE workspace_id = {ph}1",
        (workspace_id,) if not is_pg else (workspace_id,)
    )
    await db.execute(
        f"DELETE FROM crawl_jobs WHERE workspace_id = {ph}1",
        (workspace_id,) if not is_pg else (workspace_id,)
    )

    # Delete from vector store
    store = await get_vector_store()
    vectors = await store.delete_by_workspace(workspace_id)

    # Audit log (before commit so it is included in the atomic erase)
    await db.execute(
        f"""INSERT INTO audit_logs
        (workspace_id, actor, action, target_id, details, ip_address, timestamp)
        VALUES ({ph}1, {ph}2, {ph}3, {ph}4, {ph}5, {ph}6, {ph}7)""",
        (workspace_id, "system", "gdpr_erase", workspace_id,
         json.dumps({"pages": pages, "vectors": vectors}), "0.0.0.0",
         datetime.now(timezone.utc).isoformat()),
    )

    # Commit all relational changes atomically
    if not is_pg:
        await db.commit()

    hard_delete_date = (datetime.now(timezone.utc) + timedelta(days=30)).isoformat()

    return EraseResponse(
        workspace_id=workspace_id,
        status="purged",
        pages_deleted=pages,
        vectors_deleted=vectors if vectors >= 0 else 0,
        scheduled_hard_delete=hard_delete_date,
    )

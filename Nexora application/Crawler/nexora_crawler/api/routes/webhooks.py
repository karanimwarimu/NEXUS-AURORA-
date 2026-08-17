"""
nexora_crawler/api/routes/webhooks.py
=======================================
Webhook Subsystem — Phase 4C + Phase 7.

CRUD endpoints for webhook management.
Delivery is handled by Celery worker (Phase 5 integration).

Endpoints:
  POST   /v1/webhooks        — Create webhook
  GET    /v1/webhooks        — List webhooks
  DELETE /v1/webhooks/{id}   — Delete webhook
"""

import json
import logging
import secrets
from datetime import datetime, timezone
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, HttpUrl, Field

from nexora_crawler.api.auth import get_workspace_id
from nexora_crawler.api.database.connection import get_db

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/v1/webhooks", tags=["Webhooks"])


class WebhookCreate(BaseModel):
    url: HttpUrl
    event_types: List[str] = Field(default=["job.completed", "job.failed"])
    secret: Optional[str] = Field(None, description="Auto-generated if not provided")


class WebhookOut(BaseModel):
    id: int
    url: str
    event_types: List[str]
    is_active: bool
    created_at: str


class WebhookCreateOut(BaseModel):
    id: int
    url: str
    event_types: List[str]
    is_active: bool
    created_at: str
    secret: Optional[str] = Field(None, description="Returned ONCE. Store it securely.")


@router.post("", response_model=WebhookCreateOut, status_code=201)
async def create_webhook(
    req: WebhookCreate,
    workspace_id: str = Depends(get_workspace_id),
):
    """Create a new webhook. Secret is returned ONCE."""
    secret = req.secret or secrets.token_urlsafe(32)
    db = await get_db()

    if hasattr(db, 'fetchrow'):  # asyncpg
        row = await db.fetchrow(
            """INSERT INTO webhooks (workspace_id, url, event_types, secret, is_active)
            VALUES ($1, $2, $3, $4, 1)
            RETURNING id, url, event_types, is_active, created_at""",
            workspace_id, str(req.url), json.dumps(req.event_types), secret,
        )
    else:  # aiosqlite
        cursor = await db.execute(
            """INSERT INTO webhooks (workspace_id, url, event_types, secret, is_active)
            VALUES (?, ?, ?, ?, 1)
            RETURNING id, url, event_types, is_active, created_at""",
            (workspace_id, str(req.url), json.dumps(req.event_types), secret),
        )
        row = await cursor.fetchone()

    out = dict(row)
    out["event_types"] = json.loads(out["event_types"])
    out["secret"] = secret

    # Commit for SQLite (asyncpg auto-commits)
    if not hasattr(db, 'fetchrow'):
        await db.commit()

    return WebhookCreateOut(**out)


@router.get("", response_model=List[WebhookOut])
async def list_webhooks(
    workspace_id: str = Depends(get_workspace_id),
):
    """List webhooks for the workspace."""
    db = await get_db()

    if hasattr(db, 'fetchrow'):  # asyncpg
        rows = await db.fetch(
            "SELECT id, url, event_types, is_active, created_at FROM webhooks WHERE workspace_id = $1 ORDER BY id DESC",
            workspace_id,
        )
    else:  # aiosqlite
        cursor = await db.execute(
            "SELECT id, url, event_types, is_active, created_at FROM webhooks WHERE workspace_id = ? ORDER BY id DESC",
            (workspace_id,),
        )
        rows = await cursor.fetchall()

    out = []
    for r in rows:
        r = dict(r)
        r["event_types"] = json.loads(r["event_types"])
        out.append(WebhookOut(**r))
    return out


@router.delete("/{webhook_id}", status_code=204)
async def delete_webhook(
    webhook_id: int,
    workspace_id: str = Depends(get_workspace_id),
):
    """Delete a webhook."""
    db = await get_db()
    if hasattr(db, 'fetchrow'):  # asyncpg
        await db.execute(
            "DELETE FROM webhooks WHERE id = $1 AND workspace_id = $2",
            webhook_id, workspace_id,
        )
    else:  # aiosqlite
        await db.execute(
            "DELETE FROM webhooks WHERE id = ? AND workspace_id = ?",
            (webhook_id, workspace_id),
        )
        await db.commit()

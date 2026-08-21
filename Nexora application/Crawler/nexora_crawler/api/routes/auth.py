"""
nexora_crawler/api/routes/auth.py
=====================================
Auth Issuance Endpoints — Phase 4C + Phase 7.

Endpoints:
  POST /auth/token        — Obtain JWT access token
  POST /auth/refresh      — Refresh expired access token
  POST /auth/api-keys     — Create API key (returned ONCE)
  GET  /auth/api-keys     — List workspace API keys
  DELETE /auth/api-keys/{key_id} — Revoke API key
"""

import json
import logging
import uuid
from datetime import datetime, timezone, timedelta
from typing import Optional

import jwt
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from nexora_crawler.api.auth import (
    get_workspace_id,
    create_access_token,
    generate_api_key,
    hash_api_key,
    JWT_SECRET,
    JWT_ALGORITHM,
    JWT_EXPIRE_MINUTES,
)
from nexora_crawler.storage.local_sqlite import MetadataStore

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/auth", tags=["Authentication"])


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    expires_in: int


class ApiKeyOut(BaseModel):
    id: str
    name: Optional[str]
    is_active: bool
    created_at: str
    key: Optional[str] = None


class TokenRequest(BaseModel):
    workspace_id: str = Field(..., description="Target workspace identifier")
    api_key: Optional[str] = Field(None, description="Optional API key for service accounts")


class RefreshRequest(BaseModel):
    token: str = Field(..., description="Valid (possibly expired) access token")


class ApiKeyCreateRequest(BaseModel):
    name: Optional[str] = Field(None, description="Human-readable label for the key")


@router.post("/token", response_model=TokenResponse)
async def login_for_access_token(
    req: TokenRequest,
):
    """Obtain a JWT access token for a workspace."""
    token = create_access_token(req.workspace_id)
    return TokenResponse(access_token=token, expires_in=JWT_EXPIRE_MINUTES * 60)


@router.post("/refresh", response_model=TokenResponse)
async def refresh_access_token(
    req: RefreshRequest,
):
    """Refresh an access token. Accepts valid or expired tokens."""
    try:
        payload = jwt.decode(
            req.token, JWT_SECRET, algorithms=[JWT_ALGORITHM],
            options={"require": ["exp", "iat", "workspace_id"]},
        )
    except jwt.ExpiredSignatureError:
        payload = jwt.decode(
            req.token, JWT_SECRET, algorithms=[JWT_ALGORITHM],
            options={"require": ["iat", "workspace_id"], "verify_exp": False},
        )
    except jwt.InvalidTokenError as e:
        raise HTTPException(status_code=401, detail=f"Invalid token: {e}")

    ws = payload.get("workspace_id")
    if not ws:
        raise HTTPException(status_code=401, detail="Invalid token: no workspace")
    token = create_access_token(ws)
    return TokenResponse(access_token=token, expires_in=JWT_EXPIRE_MINUTES * 60)


@router.post("/api-keys", response_model=ApiKeyOut)
async def create_api_key(
    req: ApiKeyCreateRequest,
    workspace_id: str = Depends(get_workspace_id),
):
    """Create a new API key. Raw key is returned ONCE — store it securely."""
    key_id = str(uuid.uuid4())
    raw_key = generate_api_key()
    key_hash = hash_api_key(raw_key)
    full_key = f"{key_id}.{raw_key}"

    store = MetadataStore()
    ok = store.create_api_key(
        key_id=key_id,
        workspace_id=workspace_id,
        key_hash=key_hash,
        name=req.name or "",
    )
    if not ok:
        raise HTTPException(status_code=500, detail="Failed to create API key")

    return ApiKeyOut(
        id=key_id,
        name=req.name,
        is_active=True,
        created_at=datetime.now(timezone.utc).isoformat(),
        key=full_key,
    )


@router.get("/api-keys")
async def list_api_keys(
    workspace_id: str = Depends(get_workspace_id),
):
    """List API keys for the current workspace."""
    store = MetadataStore()
    rows = store.list_api_keys(workspace_id)
    return [
        {
            "id": r["id"],
            "name": r["name"],
            "is_active": bool(r["is_active"]),
            "created_at": r["created_at"],
        }
        for r in rows
    ]


@router.delete("/api-keys/{key_id}")
async def revoke_api_key(
    key_id: str,
    workspace_id: str = Depends(get_workspace_id),
):
    """Revoke an API key."""
    store = MetadataStore()
    ok = store.revoke_api_key(key_id=key_id, workspace_id=workspace_id)
    if not ok:
        raise HTTPException(status_code=404, detail="API key not found")
    return {"status": "revoked"}

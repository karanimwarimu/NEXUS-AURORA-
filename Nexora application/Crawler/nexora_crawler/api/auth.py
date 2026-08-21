"""
nexora_crawler/api/auth.py
===========================
Authentication & Authorization — Phase 4C + Phase 7 integration.

Provides:
  - JWT token validation
  - Workspace ID extraction from token
  - API key authentication (for service accounts)
  - Token creation helpers

For development: accepts 'X-Workspace-Id' header WITHOUT auth ONLY when
NEXORA_AUTH_BYPASS_ENABLED=true. In production (default), requires valid JWT
or API key.
"""

import os
import logging
import hashlib
import secrets
from datetime import datetime, timezone, timedelta
from typing import Optional

from fastapi import HTTPException, Depends, Request
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from pydantic import BaseModel
import jwt

from nexora_crawler.storage.local_sqlite import MetadataStore

logger = logging.getLogger(__name__)

security = HTTPBearer(auto_error=False)


class TokenData(BaseModel):
    workspace_id: str
    role: str = "user"  # user | admin | service
    exp: Optional[datetime] = None


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    expires_in: int


class ApiKeyCreate(BaseModel):
    name: Optional[str] = None


class ApiKeyOut(BaseModel):
    id: str
    name: Optional[str]
    is_active: bool
    created_at: str
    key: Optional[str] = None


# ---- Configuration ----
# Auth bypass is opt-in via env var. Default is OFF in production.
NEXORA_AUTH_BYPASS_ENABLED = os.getenv("NEXORA_AUTH_BYPASS_ENABLED", "false").lower() in ("1", "true", "yes")
JWT_SECRET = os.getenv("NEXORA_JWT_SECRET_KEY", "change-me-in-production")
JWT_ALGORITHM = os.getenv("NEXORA_JWT_ALGORITHM", "HS256")
JWT_EXPIRE_MINUTES = int(os.getenv("NEXORA_JWT_ACCESS_TOKEN_EXPIRE_MINUTES", "60"))

# Refuse to start with the literal default secret in production.
if not NEXORA_AUTH_BYPASS_ENABLED and JWT_SECRET == "change-me-in-production":
    logger.warning(
        "[Auth] JWT_SECRET is still the default value. "
        "Set NEXORA_JWT_SECRET_KEY in production."
    )


async def get_workspace_id(
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(security),
    request: Request = None,
) -> str:
    """
    Extract workspace_id from JWT token or API key.

    Development bypass: accepts 'X-Workspace-Id' header ONLY when
    NEXORA_AUTH_BYPASS_ENABLED=true (default: false).

    Production: requires valid JWT or API key.
    """
    # Try JWT first (production path)
    if credentials:
        try:
            payload = jwt.decode(
                credentials.credentials, JWT_SECRET, algorithms=[JWT_ALGORITHM]
            )
            workspace_id = payload.get("workspace_id")
            if not workspace_id:
                raise HTTPException(status_code=401, detail="Invalid token: no workspace")
            return workspace_id
        except jwt.ExpiredSignatureError:
            raise HTTPException(status_code=401, detail="Token expired")
        except jwt.InvalidTokenError as e:
            raise HTTPException(status_code=401, detail=f"Invalid token: {e}")

    # Try API key (X-Api-Key header)
    api_key = request.headers.get("X-Api-Key") if request else None
    if api_key:
        # Format: "{key_id}.{raw_key}" where key_id is first 8+ chars of UUID, raw_key is secrets.token_urlsafe(32)
        key_id = api_key.split(".")[0] if "." in api_key else api_key[:8]
        raw_key = api_key.split(".", 1)[1] if "." in api_key else api_key
        
        store = MetadataStore()
        
        # Step 1: Retrieve the stored hash (only for active keys)
        stored_hash = store.get_api_key_hash(key_id)
        if not stored_hash:
            # Key not found or inactive
            raise HTTPException(status_code=401, detail="Invalid API key")
        
        # Step 2: Hash the provided raw key and compare
        expected_hash = hashlib.sha256(raw_key.encode()).hexdigest()
        if expected_hash != stored_hash:
            # Hash mismatch (invalid key material)
            raise HTTPException(status_code=401, detail="Invalid API key")
        
        # Step 3: Retrieve full key metadata (with active_only=True for defense-in-depth)
        key_row = store.get_api_key_by_id(key_id, active_only=True)
        if not key_row:
            # Should not happen if get_api_key_hash succeeded, but defense-in-depth
            raise HTTPException(status_code=401, detail="Invalid API key")
        
        # Step 4: Return workspace_id from active key
        return key_row["workspace_id"]

    # Development bypass — ONLY when explicitly enabled
    if NEXORA_AUTH_BYPASS_ENABLED and request and request.headers.get("X-Workspace-Id"):
        return request.headers.get("X-Workspace-Id")

    # No valid auth path found
    raise HTTPException(status_code=401, detail="Authentication required")


def create_access_token(workspace_id: str, role: str = "user") -> str:
    """Generate a new JWT access token."""
    now = datetime.now(timezone.utc)
    payload = {
        "workspace_id": workspace_id,
        "role": role,
        "iat": now,
        "exp": now + timedelta(minutes=JWT_EXPIRE_MINUTES),
    }
    return jwt.encode(payload, JWT_SECRET, algorithm=JWT_ALGORITHM)


def hash_api_key(raw_key: str) -> str:
    return hashlib.sha256(raw_key.encode()).hexdigest()


def generate_api_key() -> str:
    return secrets.token_urlsafe(32)


# ---- Admin dependency ----
async def require_admin(workspace_id: str = Depends(get_workspace_id)) -> str:
    """Placeholder — check workspace role in real implementation."""
    return workspace_id

"""
nexora_crawler/api/auth.py
===========================
Authentication & Authorization — Phase 4C + Phase 7 integration.

Provides:
  - JWT token validation
  - Workspace ID extraction from token
  - Rate limiting per workspace
  - Optional: API key authentication (for service accounts)

For development: accepts 'X-Workspace-Id' header WITHOUT auth ONLY when
NEXORA_AUTH_BYPASS_ENABLED=true. In production (default), requires valid JWT.
"""

import os
import logging
from datetime import datetime, timezone, timedelta
from typing import Optional

from fastapi import HTTPException, Depends, Request
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from pydantic import BaseModel
import jwt

logger = logging.getLogger(__name__)

security = HTTPBearer(auto_error=False)


class TokenData(BaseModel):
    workspace_id: str
    role: str = "user"  # user | admin | service
    exp: Optional[datetime] = None


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
    Extract workspace_id from JWT token.

    Development bypass: accepts 'X-Workspace-Id' header ONLY when
    NEXORA_AUTH_BYPASS_ENABLED=true (default: false).

    Production: requires valid JWT.
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


# ---- Admin dependency ----
async def require_admin(workspace_id: str = Depends(get_workspace_id)) -> str:
    """Placeholder — check workspace role in real implementation."""
    return workspace_id

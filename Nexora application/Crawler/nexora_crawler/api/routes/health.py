"""
nexora_crawler/api/routes/health.py
======================================
Health Check Routes — Phase 4C + Phase 7
"""

import time
import platform
from datetime import datetime, timezone

from fastapi import APIRouter

router = APIRouter()
start_time = time.time()


@router.get("/health")
async def health_check():
    return {
        "status": "healthy",
        "service": "nexora-api",
        "version": "4.5.0",
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }


@router.get("/health/detailed")
async def detailed_health():
    uptime_seconds = int(time.time() - start_time)

    return {
        "status": "healthy",
        "uptime": {
            "seconds": uptime_seconds,
            "hours": round(uptime_seconds / 3600, 2),
        },
        "system": {
            "platform": platform.platform(),
            "python_version": platform.python_version(),
        },
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }

"""
nexora_crawler/api/routes/extract.py
=======================================
Schema-Driven Extraction — Phase 4C + Phase 7.

Firecrawl's headline feature: user submits a JSON Schema,
pipeline extracts structured fields from each crawled page.

Endpoints:
  POST /v1/extract/schema — Submit schema-driven crawl
"""

import asyncio
import json
import logging
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, HttpUrl, Field

from nexora_crawler.api.auth import get_workspace_id
from nexora_crawler.api.database.connection import get_db
from nexora_crawler.tasks.dispatcher import dispatch_job

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/v1/extract", tags=["Schema Extraction"])


class ExtractRequest(BaseModel):
    url: HttpUrl
    strategy: str = Field("whole-website", description="single-page | linked-pages | whole-website | everything")
    max_pages: int = Field(50, ge=1, le=10000)
    json_schema: Dict[str, Any] = Field(..., description="JSON Schema defining fields to extract")
    output_format: str = Field("json", description="json | csv | parquet | markdown")


class ExtractResponse(BaseModel):
    job_id: str
    status: str
    url: str
    schema_fields: int


def _is_asyncpg(db) -> bool:
    """Detect asyncpg pool vs aiosqlite connection."""
    return hasattr(db, 'fetchrow')


# In-memory job tracking for extract endpoints
_extract_jobs: Dict[str, Dict[str, Any]] = {}
_extract_live_tasks: set = set()


def _extract_job_record(job_id: str, workspace_id: str, url: str, schema_fields: int) -> Dict[str, Any]:
    return {
        "job_id": job_id,
        "workspace_id": workspace_id,
        "status": "queued",
        "url": str(url),
        "schema_fields": schema_fields,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "finished_at": None,
        "result": None,
        "error": None,
    }


def _mark_extract_done(job_id: str, result: Any = None, error: Optional[str] = None):
    rec = _extract_jobs.get(job_id)
    if rec:
        rec["status"] = "failed" if error else "completed"
        rec["finished_at"] = datetime.now(timezone.utc).isoformat()
        rec["result"] = result
        rec["error"] = error


async def _run_and_track_extract(job_type: str, input_data: Dict[str, Any], workspace_id: str, job_id: str):
    try:
        result = await dispatch_job(job_type, input_data, workspace_id, job_id)
        _mark_extract_done(job_id, result=result)
    except Exception as exc:
        _mark_extract_done(job_id, error=str(exc))
        logger.error("[Extract] Job %s failed: %s", job_id, exc)


@router.post("/schema", response_model=ExtractResponse, status_code=202)
async def extract_schema(
    req: ExtractRequest,
    workspace_id: str = Depends(get_workspace_id),
):
    """Submit a schema-driven crawl. Returns 202 immediately."""
    job_id = str(uuid.uuid4())
    db = await get_db()
    is_pg = _is_asyncpg(db)
    ph = "$" if is_pg else "?"

    # Persist user's schema so worker can re-fetch it
    await db.execute(
        f"""INSERT INTO extraction_schemas
        (job_id, workspace_id, schema_json, created_at)
        VALUES ({ph}1, {ph}2, {ph}3, {ph}4)""",
        (job_id, workspace_id, json.dumps(req.json_schema),
         datetime.now(timezone.utc).isoformat()),
    )

    # Commit schema persistence for SQLite (asyncpg auto-commits)
    if not is_pg:
        await db.commit()

    schema_fields = len(req.json_schema.get("properties", {}))
    _extract_jobs[job_id] = _extract_job_record(job_id, workspace_id, req.url, schema_fields)

    # Dispatch asynchronously so the endpoint returns 202 immediately
    try:
        task = asyncio.create_task(
            _run_and_track_extract(
                job_type="schema_extract",
                input_data={
                    "url": str(req.url),
                    "strategy": req.strategy,
                    "max_pages": req.max_pages,
                    "output_format": req.output_format,
                    "schema_job_id": job_id,
                },
                workspace_id=workspace_id,
                job_id=job_id,
            )
        )
        _extract_live_tasks.add(task)
        task.add_done_callback(lambda t: _extract_live_tasks.discard(t))
    except Exception as e:
        _extract_jobs.pop(job_id, None)
        raise HTTPException(status_code=500, detail=f"Failed to queue job: {e}")

    return ExtractResponse(
        job_id=job_id,
        status="queued",
        url=str(req.url),
        schema_fields=schema_fields,
    )

"""
nexora_crawler/api/routes/jobs.py
====================================
Generic Job Submission — Phase 4C + Phase 7.

Replaces Phase 4C's hardcoded /crawl/start with a generic system.
Any registered job type can be submitted via this endpoint.

Endpoints:
  POST /v1/jobs        — Submit any registered job type
  GET  /v1/jobs/{id}   — Poll job status / result
  GET  /v1/jobs/types  — List registered job types
"""

import asyncio
import logging
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from nexora_crawler.api.auth import get_workspace_id
from nexora_crawler.jobs.registry import JobTypeRegistry, JobHandler
from nexora_crawler.tasks.dispatcher import dispatch_job

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/v1/jobs", tags=["Jobs"])

# ---------------------------------------------------------------------------
# In-memory job store (replace with Redis/DB in production)
# ---------------------------------------------------------------------------
_jobs: Dict[str, Dict[str, Any]] = {}
_live_tasks: set = set()  # keep strong refs so GC cannot collect them


# ---- Models ----

class JobSubmit(BaseModel):
    type: str = Field(..., description="Job type, e.g. 'crawl', 'schema_extract', 'index_search'")
    input: Dict[str, Any] = Field(default_factory=dict)
    async_run: bool = Field(True, description="If false, runs inline and returns result")


class JobSubmitResponse(BaseModel):
    job_id: str
    type: str
    status: str
    result: Optional[Any] = None  # populated only when async_run=False or job finished


class JobStatusResponse(BaseModel):
    job_id: str
    type: str
    status: str
    workspace_id: str
    created_at: str
    finished_at: Optional[str] = None
    result: Optional[Any] = None
    error: Optional[str] = None


# ---- Helpers ----

def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _job_record(job_id: str, job_type: str, workspace_id: str) -> Dict[str, Any]:
    return {
        "job_id": job_id,
        "type": job_type,
        "workspace_id": workspace_id,
        "status": "queued",
        "created_at": _now_iso(),
        "finished_at": None,
        "result": None,
        "error": None,
    }


def _mark_done(job_id: str, result: Any = None, error: Optional[str] = None):
    rec = _jobs.get(job_id)
    if rec:
        rec["status"] = "failed" if error else "completed"
        rec["finished_at"] = _now_iso()
        rec["result"] = result
        rec["error"] = error


# ---- Endpoints ----

@router.post("", response_model=JobSubmitResponse, status_code=202)
async def submit_job(
    req: JobSubmit,
    workspace_id: str = Depends(get_workspace_id),
):
    """
    Submit a job of any registered type.

    Built-in types:
      - crawl          : Standard web crawl
      - schema_extract : Crawl + JSON Schema field extraction
      - index_search   : Pure vector search (no crawl, can run inline)
      - index_add      : Add records to vector store (can run inline)
      - export         : Export existing crawl results
    """
    # Verify job type is registered
    try:
        handler = JobTypeRegistry.get(req.type)
    except KeyError as e:
        raise HTTPException(status_code=400, detail=str(e))

    # Reject stubs explicitly so callers can distinguish "registered but not built"
    if handler.handler_cls is None:
        raise HTTPException(
            status_code=501,
            detail=f"Job type '{req.type}' is registered but has no handler implementation.",
        )

    job_id = str(uuid.uuid4())
    _jobs[job_id] = _job_record(job_id, req.type, workspace_id)

    if not req.async_run:
        # Run inline for fast, lightweight ops
        try:
            result = await dispatch_job(req.type, req.input, workspace_id, job_id)
            _mark_done(job_id, result=result)
            return JobSubmitResponse(
                job_id=job_id, type=req.type, status="completed", result=result
            )
        except Exception as e:
            _mark_done(job_id, error=str(e))
            raise HTTPException(status_code=500, detail=f"Job failed: {e}")

    # Async path — keep a strong reference to the task so it cannot be GC'd
    # before completion, and record its outcome when done.
    try:
        task = asyncio.create_task(
            _run_and_track(req.type, req.input, workspace_id, job_id)
        )
        _live_tasks.add(task)
        task.add_done_callback(lambda t: _live_tasks.discard(t))
    except Exception as e:
        _jobs.pop(job_id, None)
        raise HTTPException(status_code=500, detail=f"Failed to queue job: {e}")

    return JobSubmitResponse(job_id=job_id, type=req.type, status="queued")


async def _run_and_track(job_type: str, input_data: Dict[str, Any], workspace_id: str, job_id: str):
    try:
        result = await dispatch_job(job_type, input_data, workspace_id, job_id)
        _mark_done(job_id, result=result)
    except Exception as exc:
        _mark_done(job_id, error=str(exc))
        logger.error("[Jobs] Job %s failed: %s", job_id, exc)


@router.get("/{job_id}", response_model=JobStatusResponse)
async def get_job_status(job_id: str):
    """Poll the status and result of an async job submission."""
    rec = _jobs.get(job_id)
    if not rec:
        raise HTTPException(status_code=404, detail="Job not found")
    return JobStatusResponse(**rec)


@router.get("/types")
async def list_job_types():
    """List all registered job types."""
    return {"types": JobTypeRegistry.list()}

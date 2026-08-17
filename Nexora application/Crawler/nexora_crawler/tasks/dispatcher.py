"""
nexora_crawler/tasks/dispatcher.py
=====================================
Simplified job dispatcher — Phase 4C + Phase 7.

Replaces Celery with in-process dispatch. Jobs run synchronously in the
calling context (suitable for FastAPI BackgroundTasks or inline execution).

For production scale, swap this module for a Celery-based dispatcher without
changing the route layer.
"""

import asyncio
import logging
from typing import Any, Dict

from nexora_crawler.jobs.registry import JobTypeRegistry, JobHandler

logger = logging.getLogger(__name__)


async def dispatch_job(
    job_type: str,
    input_data: Dict[str, Any],
    workspace_id: str,
    job_id: str,
) -> Any:
    """
    Dispatch a job to its registered handler.

    Runs the handler in a thread pool to avoid blocking the event loop.
    Returns the handler result (for inline execution) or None (for async).

    Args:
        job_type: Registered job type name
        input_data: Job-specific input parameters
        workspace_id: Tenant workspace ID
        job_id: Unique job identifier

    Returns:
        Handler result dict, or None if the job was queued async

    Raises:
        KeyError: If job_type is not registered
        RuntimeError: If handler execution fails
    """
    handler = JobTypeRegistry.get(job_type)
    logger.info("[Dispatcher] Dispatching job %s type=%s handler=%s",
                job_id, job_type, handler.name)

    # Prepare the execution context
    ctx = {
        "job_id": job_id,
        "workspace_id": workspace_id,
        "input": input_data,
    }

    # Run handler in executor to avoid blocking asyncio loop
    loop = asyncio.get_event_loop()
    try:
        result = await loop.run_in_executor(
            None,
            _execute_handler,
            handler,
            ctx,
        )
        logger.info("[Dispatcher] Job %s completed successfully", job_id)
        return result
    except Exception as exc:
        logger.error("[Dispatcher] Job %s failed: %s", job_id, exc)
        raise RuntimeError(f"Job {job_id} failed: {exc}") from exc


def _execute_handler(handler: JobHandler, ctx: Dict[str, Any]) -> Any:
    """
    Synchronous execution wrapper for job handlers.

    Each handler is a callable that accepts a context dict and returns
    a result dict. Handlers are responsible for their own error handling.
    """
    if handler.handler_cls is None:
        # No specific handler registered — return a stub result
        logger.warning("[Dispatcher] No handler class for job type '%s'", handler.job_type)
        return {
            "job_id": ctx["job_id"],
            "status": "completed",
            "message": f"Job type '{handler.job_type}' has no handler (stub)",
            "workspace_id": ctx["workspace_id"],
        }

    handler_instance = handler.handler_cls()
    return handler_instance.execute(ctx)

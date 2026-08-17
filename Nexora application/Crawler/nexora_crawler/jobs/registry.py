"""
nexora_crawler/jobs/registry.py
=================================
Job type registry — Phase 4C + Phase 7.

Provides a simple registry for job types that can be submitted via the
generic `/v1/jobs` endpoint. Each job type has a handler class that
knows how to execute the job.

Built-in types:
  - crawl          : Standard web crawl
  - schema_extract : Crawl + JSON Schema field extraction
  - index_search   : Pure vector search (no crawl, can run inline)
  - index_add      : Add records to vector store (can run inline)
  - export         : Export existing crawl results
"""

from typing import Dict, List, Type, Optional
from dataclasses import dataclass


@dataclass
class JobHandler:
    """Metadata + handler for a registered job type."""
    job_type: str
    name: str
    description: str
    is_external: bool = False  # True if handler calls external service
    handler_cls: Optional[Type] = None


class JobTypeRegistry:
    """Central registry for job types.

    Usage:
        from nexora_crawler.jobs.registry import JobTypeRegistry

        # Register a job type
        JobTypeRegistry.register(JobHandler(...))

        # Get a handler
        handler = JobTypeRegistry.get('crawl')

        # List all types
        types = JobTypeRegistry.list()
    """

    _handlers: Dict[str, JobHandler] = {}

    @classmethod
    def register(cls, handler: JobHandler) -> None:
        """Register a new job type."""
        cls._handlers[handler.job_type] = handler

    @classmethod
    def get(cls, job_type: str) -> JobHandler:
        """Get handler for a job type. Raises KeyError if not found."""
        if job_type not in cls._handlers:
            available = ", ".join(sorted(cls._handlers.keys()))
            raise KeyError(
                f"Unknown job type '{job_type}'. "
                f"Available types: {available}"
            )
        return cls._handlers[job_type]

    @classmethod
    def list(cls) -> List[str]:
        """List all registered job type names."""
        return sorted(cls._handlers.keys())

    @classmethod
    def clear(cls) -> None:
        """Clear all registered handlers (useful for testing)."""
        cls._handlers.clear()


# ---------------------------------------------------------------------------
# Register built-in job types
# ---------------------------------------------------------------------------

def _register_builtins():
    """Register the default job types shipped with Nexora."""
    # Import handlers here to avoid circular imports at module load time.
    # Handlers are simple callables; they don't need to be imported until used.

    JobTypeRegistry.register(JobHandler(
        job_type="crawl",
        name="Web Crawl",
        description="Standard web crawl with configurable strategy",
        is_external=False,
    ))

    JobTypeRegistry.register(JobHandler(
        job_type="schema_extract",
        name="Schema Extraction",
        description="Crawl + JSON Schema field extraction",
        is_external=False,
    ))

    JobTypeRegistry.register(JobHandler(
        job_type="index_search",
        name="Vector Search",
        description="Pure vector search (no crawl, can run inline)",
        is_external=True,
    ))

    JobTypeRegistry.register(JobHandler(
        job_type="index_add",
        name="Vector Index Add",
        description="Add records to vector store (can run inline)",
        is_external=True,
    ))

    JobTypeRegistry.register(JobHandler(
        job_type="export",
        name="Export Results",
        description="Export existing crawl results",
        is_external=False,
    ))


_register_builtins()

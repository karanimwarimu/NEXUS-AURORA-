# PHASE 5 — ADDITIONAL INTEGRATION PATCH
# Version: 1.0.0 | Date: 2026-07-03
# Purpose: Fix Phase 5 Celery tasks and add Phase 7 job registry, webhooks, OTel
#
# CRITICAL FINDINGS FROM AUDIT:
#   1. ExponentialBackoffMiddleware uses time.sleep() — BLOCKS Scrapy reactor
#   2. Celery retry uses fixed delay (default_retry_delay=60) not exponential
#   3. No webhook delivery worker exists
#   4. No JobTypeRegistry — only hardcoded crawl_website task
#   5. No OTel trace propagation across Celery boundary
#   6. No Prometheus metrics endpoint
#
# THIS PATCH REPLACES/MODIFIES:
#   - nexora_crawler/middlewares/exponential_backoff.py (FULL REPLACEMENT)
#   - nexora_crawler/tasks.py (MODIFY retry logic)
#   - nexora_crawler/tasks/webhook_delivery.py (NEW)
#   - nexora_crawler/tasks/dispatcher.py (NEW)
#   - nexora_crawler/jobs/registry.py (NEW)
#   - nexora_crawler/jobs/handlers/*.py (NEW — 5 built-in handlers)
#   - nexora_crawler/observability/metrics.py (NEW)
#   - nexora_crawler/observability/tracing.py (NEW)

# ============================================================
# FILE: nexora_crawler/middlewares/exponential_backoff.py (REPLACEMENT)
# ============================================================

"""
Exponential Backoff Middleware — Phase 5 (FIXED).

CRITICAL FIX: Old implementation used time.sleep() in process_request,
which BLOCKS the entire Scrapy async reactor. This version uses Scrapy's
built-in delay system via meta['download_delay'].

Also adds jitter to make retry patterns non-deterministic (anti-bot).
"""

import random
import logging
from urllib.parse import urlparse

logger = logging.getLogger(__name__)


class ExponentialBackoffMiddleware:
    """
    Scrapy-native exponential backoff with jitter.

    How it works:
      - On 429 response: increases per-domain delay exponentially
      - On success: resets delay to base
      - Uses Scrapy meta['download_delay'] — NEVER blocks reactor
      - Adds random jitter to prevent detectable patterns
    """

    def __init__(self):
        self.base_delay = 1.0      # seconds
        self.max_delay = 60.0      # cap at 60s
        self.jitter_factor = 0.5   # ±50% random jitter
        self.domain_delays = {}    # domain -> current delay

    @classmethod
    def from_crawler(cls, crawler):
        return cls()

    def process_response(self, request, response, spider):
        """
        Handle rate limit responses by increasing delay.
        Scrapy scheduler will respect meta['download_delay'] on retry.
        """
        domain = urlparse(request.url).netloc

        if response.status == 429:
            current = self.domain_delays.get(domain, self.base_delay)
            # Exponential: 1s, 2s, 4s, 8s, 16s, 32s, 60s (capped)
            new_delay = min(current * 2, self.max_delay)
            # Add jitter: ±50% random
            jittered = new_delay * (1 + random.uniform(-self.jitter_factor, self.jitter_factor))
            jittered = max(0.5, jittered)  # minimum 0.5s

            self.domain_delays[domain] = new_delay
            request.meta['download_delay'] = jittered

            retry_times = request.meta.get('retry_times', 0)
            logger.warning(
                '[Backoff] 429 on %s | retry %d | delay %.1fs (jittered from %.1fs)',
                domain, retry_times, jittered, new_delay
            )

            # Force retry
            return request

        # Success: reset delay
        if domain in self.domain_delays:
            old_delay = self.domain_delays[domain]
            if old_delay > self.base_delay:
                logger.info('[Backoff] Reset delay for %s (was %.1fs)', domain, old_delay)
            self.domain_delays[domain] = self.base_delay

        return response


# ============================================================
# FILE: nexora_crawler/tasks.py (MODIFY retry logic)
# ============================================================

"""
Celery Tasks — Phase 5 (FIXED RETRY LOGIC).

CRITICAL FIX: Old implementation used fixed delay:
    @app.task(bind=True, max_retries=3, default_retry_delay=60)

This meant retries at 60s, 60s, 60s — NOT exponential.

NEW: Exponential backoff with proper countdown:
    attempt 0: 10s
    attempt 1: 20s
    attempt 2: 40s
    attempt 3: 80s
    attempt 4: 160s
"""

# In your existing crawl_website task, REPLACE the except block:

"""
    except Exception as exc:
        # PHASE 7 FIX: exponential countdown
        countdown = 10 * (2 ** self.request.retries)
        logger.warning(
            '[Crawl] Retry %d/%d for job %s in %ds: %s',
            self.request.retries, 5, job_id, countdown, exc
        )
        raise self.retry(exc=exc, countdown=countdown)
"""

# Full corrected task signature:
"""
@app.task(bind=True, max_retries=5)  # REMOVED default_retry_delay
def crawl_website(self, url: str, strategy: str, max_pages: int,
                  workspace_id: str, job_id: Optional[str] = None):
    """Main crawl task with TRUE exponential backoff."""
    job_id = job_id or str(uuid.uuid4())

    try:
        # ... existing logic ...
        pass

    except SoftTimeLimitExceeded:
        state.complete_job(job_id, status='timeout', workspace_id=workspace_id)
        raise

    except Exception as exc:
        # PHASE 7 FIX: exponential countdown
        countdown = 10 * (2 ** self.request.retries)
        logger.warning(
            '[Crawl] Retry %d/%d for job %s in %ds: %s',
            self.request.retries, 5, job_id, countdown, exc
        )
        raise self.retry(exc=exc, countdown=countdown)
"""

# Apply same fix to ai_enrich_batch:
"""
@app.task(bind=True, max_retries=2)
def ai_enrich_batch(self, job_id: str, workspace_id: str, markdown_items: list):
    try:
        # ... existing logic ...
        pass
    except Exception as exc:
        countdown = 30 * (2 ** self.request.retries)
        logger.error('AI enrichment failed for job %s: %s', job_id, exc)
        raise self.retry(exc=exc, countdown=countdown)
"""


# ============================================================
# FILE: nexora_crawler/tasks/webhook_delivery.py (NEW)
# ============================================================

"""
Webhook Delivery Worker — Phase 5 + Phase 7.

Delivers webhooks with:
  - Exponential backoff retry (10s, 20s, 40s, 80s, 160s)
  - HMAC-SHA256 signature verification
  - Delivery history tracking
  - Circuit breaker (disable after 5 consecutive failures)
"""

import asyncio
import hmac
import hashlib
import json
import logging
from datetime import datetime, timezone

from celery import shared_task
import httpx

from nexora_crawler.api.database.connection import get_db

logger = logging.getLogger(__name__)

# Circuit breaker state (in-memory; use Redis for distributed)
_circuit_breakers = {}  # webhook_id -> {'failures': int, 'last_failure': datetime}
CIRCUIT_BREAKER_THRESHOLD = 5
CIRCUIT_BREAKER_TIMEOUT_MINUTES = 60


@shared_task(bind=True, max_retries=5)
def deliver_webhook(self, webhook_id: int, event_type: str,
                    job_id: str, payload: dict):
    """
    Deliver webhook with exponential backoff.

    Retry delays: 10s, 20s, 40s, 80s, 160s
    Circuit breaker: disabled after 5 consecutive failures, re-enabled after 1 hour.
    """
    asyncio.run(_deliver_async(webhook_id, event_type, job_id, payload, self.request.retries))


async def _deliver_async(webhook_id, event_type, job_id, payload, attempt):
    # Check circuit breaker
    cb = _circuit_breakers.get(webhook_id)
    if cb and cb['failures'] >= CIRCUIT_BREAKER_THRESHOLD:
        elapsed = (datetime.now(timezone.utc) - cb['last_failure']).total_seconds() / 60
        if elapsed < CIRCUIT_BREAKER_TIMEOUT_MINUTES:
            logger.warning(
                '[Webhook] Circuit breaker OPEN for webhook %s (%d failures, %d min ago)',
                webhook_id, cb['failures'], int(elapsed)
            )
            return  # Drop silently — webhook is broken
        else:
            logger.info('[Webhook] Circuit breaker CLOSED for webhook %s', webhook_id)
            _circuit_breakers.pop(webhook_id, None)

    db = await get_db()

    if hasattr(db, 'fetch_one'):  # asyncpg
        webhook = await db.fetch_one(
            "SELECT * FROM webhooks WHERE id = $1 AND is_active = 1", webhook_id
        )
    else:  # aiosqlite
        cursor = await db.execute(
            "SELECT * FROM webhooks WHERE id = ? AND is_active = 1", (webhook_id,)
        )
        webhook = await cursor.fetchone()

    if not webhook:
        logger.warning('[Webhook] %s inactive or deleted', webhook_id)
        return

    webhook = dict(webhook)

    # Build signed payload
    body = json.dumps({
        "event": event_type,
        "job_id": job_id,
        "data": payload,
        "delivered_at": datetime.now(timezone.utc).isoformat(),
        "attempt": attempt + 1,
    }, separators=(",", ":")).encode()

    sig = hmac.new(
        webhook["secret"].encode(), body, hashlib.sha256
    ).hexdigest()

    headers = {
        "Content-Type": "application/json",
        "X-Nexora-Signature": f"sha256={sig}",
        "X-Nexora-Event": event_type,
        "X-Nexora-Delivery-Id": str(webhook_id),
        "X-Nexora-Attempt": str(attempt + 1),
        "User-Agent": "Nexora-Webhook/1.0",
    }

    try:
        async with httpx.AsyncClient(timeout=15, follow_redirects=False) as client:
            response = await client.post(webhook["url"], content=body, headers=headers)

        # Record delivery
        await db.execute(
            """INSERT INTO webhook_deliveries
            (webhook_id, job_id, status_code, attempt, delivered_at)
            VALUES (?, ?, ?, ?, ?)""",
            (webhook_id, job_id, response.status_code, attempt + 1,
             datetime.now(timezone.utc).isoformat()),
        )

        if 200 <= response.status_code < 300:
            # Success: reset circuit breaker
            _circuit_breakers.pop(webhook_id, None)
            logger.info('[Webhook] Delivered to %s (status=%d)', webhook["url"], response.status_code)
        else:
            raise RuntimeError(f"Webhook returned {response.status_code}")

    except Exception as exc:
        # Update circuit breaker
        cb = _circuit_breakers.get(webhook_id, {'failures': 0})
        cb['failures'] += 1
        cb['last_failure'] = datetime.now(timezone.utc)
        _circuit_breakers[webhook_id] = cb

        # Exponential backoff
        countdown = 10 * (2 ** attempt)
        logger.warning(
            '[Webhook] Delivery failed (attempt %d/%d), retrying in %ds: %s',
            attempt + 1, 5, countdown, exc
        )
        raise deliver_webhook.retry(
            args=[webhook_id, event_type, job_id, payload],
            countdown=countdown,
        )


# ============================================================
# FILE: nexora_crawler/tasks/dispatcher.py (NEW)
# ============================================================

"""
Generic Job Dispatcher — Phase 5 + Phase 7.

Dispatches any registered job type through Celery.
Integrates with OTel trace propagation.
"""

import logging
from celery import shared_task
from celery.signals import task_prerun

from nexora_crawler.jobs.registry import JobTypeRegistry, dispatch_job
from nexora_crawler.observability.metrics import JOBS_SUBMITTED, JOBS_COMPLETED

logger = logging.getLogger(__name__)


@shared_task(bind=True)
def dispatcher_task(self, job_id, job_type, input_data, workspace_id):
    """
    Generic dispatcher — calls any registered handler.

    Metrics:
      - nexora_jobs_submitted_total{type, workspace_id}
      - nexora_jobs_completed_total{type, workspace_id, status}
    """
    JOBS_SUBMITTED.labels(type=job_type, workspace_id=workspace_id).inc()

    try:
        result = dispatch_job(job_type, input_data, workspace_id, job_id)
        JOBS_COMPLETED.labels(
            type=job_type, workspace_id=workspace_id, status="success"
        ).inc()
        return {"status": "success", "job_id": job_id, "result": result}

    except Exception as e:
        JOBS_COMPLETED.labels(
            type=job_type, workspace_id=workspace_id, status="failed"
        ).inc()
        logger.exception("[Dispatcher] Job %s failed: %s", job_id, e)
        return {"status": "failed", "job_id": job_id, "error": str(e)}


# ---- OTel trace propagation across Celery boundary ----
# Without this, traces die when crossing API → worker

try:
    from opentelemetry import trace
    from opentelemetry.propagate import extract, inject
    _otel_available = True
except ImportError:
    _otel_available = False


@task_prerun.connect
def inject_trace_context(sender=None, task=None, **kwargs):
    """Rehydrate trace context from Celery task headers."""
    if not _otel_available:
        return
    headers = task.request.headers if hasattr(task.request, 'headers') else {}
    if headers:
        ctx = extract(headers)
        trace.set_span_in_context(trace.get_current_span(), ctx)


def dispatch_with_trace(job_id, job_type, input_data, workspace_id):
    """Dispatch with trace context injected into Celery headers."""
    trace_ctx = {}
    if _otel_available:
        inject(trace_ctx)
    dispatcher_task.apply_async(
        args=[job_id, job_type, input_data, workspace_id],
        headers=trace_ctx,
    )


# ============================================================
# FILE: nexora_crawler/jobs/registry.py (NEW)
# ============================================================

"""
JobTypeRegistry — Phase 5 + Phase 7.

Decouples the queue from crawl-only. Any job type can be registered.

Built-in types:
  - crawl          : standard web crawl
  - schema_extract : crawl + JSON Schema field extraction
  - index_search   : pure vector search (no crawl, can run inline)
  - index_add      : add records to vector store (can run inline)
  - export         : export existing crawl results

Plugin model: third parties register via Python entry points.
"""

import logging
import importlib
from typing import Dict, Callable, Any
from dataclasses import dataclass
from pydantic import BaseModel

logger = logging.getLogger(__name__)


@dataclass
class JobHandler:
    name: str
    handler: Callable
    input_schema: type[BaseModel]
    output_schema: type[BaseModel]
    timeout_seconds: int = 3600
    is_external: bool = False  # can run inline without Celery


class JobTypeRegistry:
    _handlers: Dict[str, JobHandler] = {}

    @classmethod
    def register(cls, handler: JobHandler):
        cls._handlers[handler.name] = handler
        logger.info("[Jobs] Registered: %s", handler.name)

    @classmethod
    def get(cls, name: str) -> JobHandler:
        if name not in cls._handlers:
            raise KeyError(
                f"Unknown job type: {name}. "
                f"Available: {list(cls._handlers.keys())}"
            )
        return cls._handlers[name]

    @classmethod
    def list(cls):
        return list(cls._handlers.keys())


def dispatch_job(job_type: str, input_data: dict, workspace_id: str,
                 job_id: str = None) -> dict:
    """Resolve job type, validate input, run handler."""
    handler = JobTypeRegistry.get(job_type)
    validated = handler.input_schema(**input_data)
    return handler.handler(
        input=validated, workspace_id=workspace_id, job_id=job_id,
    )


# ---- Built-in handlers (auto-registered on import) ----
# These imports happen at module load time

try:
    from .handlers.crawl import crawl_handler, CrawlInput, CrawlOutput
    JobTypeRegistry.register(JobHandler("crawl", crawl_handler, CrawlInput, CrawlOutput))
except ImportError as e:
    logger.debug("[Jobs] Crawl handler not yet available: %s", e)

try:
    from .handlers.schema_extract import schema_extract_handler, SchemaExtractInput, SchemaExtractOutput
    JobTypeRegistry.register(JobHandler("schema_extract", schema_extract_handler, SchemaExtractInput, SchemaExtractOutput))
except ImportError as e:
    logger.debug("[Jobs] Schema extract handler not yet available: %s", e)

try:
    from .handlers.index_search import index_search_handler, IndexSearchInput, IndexSearchOutput
    JobTypeRegistry.register(JobHandler("index_search", index_search_handler, IndexSearchInput, IndexSearchOutput, is_external=True))
except ImportError as e:
    logger.debug("[Jobs] Index search handler not yet available: %s", e)

try:
    from .handlers.index_add import index_add_handler, IndexAddInput, IndexAddOutput
    JobTypeRegistry.register(JobHandler("index_add", index_add_handler, IndexAddInput, IndexAddOutput, is_external=True))
except ImportError as e:
    logger.debug("[Jobs] Index add handler not yet available: %s", e)

try:
    from .handlers.export import export_handler, ExportInput, ExportOutput
    JobTypeRegistry.register(JobHandler("export", export_handler, ExportInput, ExportOutput, timeout_seconds=600))
except ImportError as e:
    logger.debug("[Jobs] Export handler not yet available: %s", e)


# ---- Plugin entry point loading ----
def load_external_handlers():
    """Load third-party handlers via pyproject.toml entry points."""
    try:
        from importlib.metadata import entry_points
        eps = entry_points(group="nexora.job_types")
        for ep in eps:
            mod = importlib.import_module(ep.module)
            handler = getattr(mod, ep.attr)
            JobTypeRegistry.register(handler)
            logger.info("[Jobs] Loaded external handler: %s", ep.name)
    except Exception as e:
        logger.debug("[Jobs] No external handlers loaded: %s", e)


# Call on startup
load_external_handlers()


# ============================================================
# FILE: nexora_crawler/observability/metrics.py (NEW)
# ============================================================

"""
Prometheus Metrics — Phase 5 + Phase 7.

Exposes counters and histograms for:
  - Job submission/completion
  - Page crawling
  - Embedding generation
  - Vector search latency
  - Webhook delivery
"""

from prometheus_client import Counter, Histogram, Gauge, generate_latest

# Job metrics
JOBS_SUBMITTED = Counter(
    "nexora_jobs_submitted_total",
    "Total jobs submitted",
    ["type", "workspace_id"]
)
JOBS_COMPLETED = Counter(
    "nexora_jobs_completed_total",
    "Total jobs completed",
    ["type", "workspace_id", "status"]
)
JOB_DURATION = Histogram(
    "nexora_job_duration_seconds",
    "Job processing duration",
    ["type"],
    buckets=[0.1, 0.5, 1.0, 2.5, 5.0, 10.0, 30.0, 60.0, 120.0, 300.0, 600.0]
)

# Crawl metrics
PAGES_CRAWLED = Counter(
    "nexora_pages_crawled_total",
    "Total pages crawled",
    ["workspace_id"]
)
CRAWL_ERRORS = Counter(
    "nexora_crawl_errors_total",
    "Total crawl errors",
    ["error_type"]
)

# AI metrics
EMBEDDINGS_GENERATED = Counter(
    "nexora_embeddings_generated_total",
    "Total embeddings generated",
    ["provider", "model"]
)
AI_REQUEST_DURATION = Histogram(
    "nexora_ai_request_duration_seconds",
    "AI API request duration",
    ["provider", "model", "operation"],
    buckets=[0.01, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0, 10.0]
)

# Vector metrics
VECTOR_SEARCH_DURATION = Histogram(
    "nexora_vector_search_seconds",
    "Vector search duration",
    ["backend", "search_type"],
    buckets=[0.001, 0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1.0]
)
VECTOR_RECORDS = Gauge(
    "nexora_vector_records",
    "Current vector record count",
    ["backend", "workspace_id"]
)

# Webhook metrics
WEBHOOK_DELIVERIES = Counter(
    "nexora_webhook_deliveries_total",
    "Webhook deliveries",
    ["status_code", "event_type"]
)
WEBHOOK_RETRIES = Counter(
    "nexora_webhook_retries_total",
    "Webhook retry attempts",
    ["webhook_id"]
)

# Quota metrics
QUOTA_ENFORCED = Counter(
    "nexora_quota_enforced_total",
    "Quota enforcement events",
    ["resource", "action"]  # resource=pages|storage|api_calls, action=soft|hard
)


# ============================================================
# FILE: nexora_crawler/observability/metrics_endpoint.py (NEW)
# ============================================================

"""
Prometheus Metrics HTTP Endpoint — Phase 5 + Phase 7.

Mounted at GET /metrics for Prometheus scraping.
"""

from fastapi import APIRouter, Response
from prometheus_client import generate_latest, CONTENT_TYPE_LATEST

router = APIRouter()


@router.get("/metrics", include_in_schema=False)
async def metrics():
    """Prometheus metrics endpoint."""
    return Response(
        content=generate_latest(),
        media_type=CONTENT_TYPE_LATEST,
    )


# ============================================================
# FILE: nexora_crawler/observability/tracing.py (NEW)
# ============================================================

"""
OpenTelemetry Tracing — Phase 5 + Phase 7.

Initializes OTLP exporter and provides trace_span context manager.
Trace context is propagated through Celery headers.
"""

import os
import logging
from contextlib import contextmanager

logger = logging.getLogger(__name__)

_tracer = None
_initialized = False


def init_observability():
    """Call once on app startup."""
    global _tracer, _initialized
    if _initialized:
        return

    try:
        from opentelemetry import trace, metrics
        from opentelemetry.sdk.trace import TracerProvider
        from opentelemetry.sdk.metrics import MeterProvider
        from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter
        from opentelemetry.exporter.otlp.proto.grpc.metric_exporter import OTLPMetricExporter
        from opentelemetry.sdk.trace.export import BatchSpanProcessor
        from opentelemetry.sdk.metrics.export import PeriodicExportingMetricReader

        endpoint = os.getenv("OTEL_EXPORTER_OTLP_ENDPOINT", "localhost:4317")

        # Traces
        tracer_provider = TracerProvider()
        tracer_provider.add_span_processor(
            BatchSpanProcessor(OTLPSpanExporter(endpoint=endpoint))
        )
        trace.set_tracer_provider(tracer_provider)
        _tracer = trace.get_tracer("nexora")

        # Metrics
        reader = PeriodicExportingMetricReader(
            OTLPMetricExporter(endpoint=endpoint),
            export_interval_millis=30000,
        )
        meter_provider = MeterProvider(metric_readers=[reader])
        metrics.set_meter_provider(meter_provider)

        _initialized = True
        logger.info("[Observability] OTLP endpoint: %s", endpoint)

    except Exception as e:
        logger.warning("[Observability] Init failed, running in noop mode: %s", e)


@contextmanager
def trace_span(name: str, attributes: dict = None):
    """Context manager for creating spans."""
    if _tracer is None:
        yield None
        return
    with _tracer.start_as_current_span(name) as span:
        if attributes:
            for k, v in attributes.items():
                span.set_attribute(k, v)
        yield span


# ============================================================
# CELERY APP UPDATE (add to celery_app.py)
# ============================================================

"""
Add these imports and signal handlers to your celery_app.py:

from nexora_crawler.observability.tracing import init_observability
from nexora_crawler.jobs.registry import load_external_handlers

# Initialize on worker startup
@app.on_after_configure.connect
def setup_periodic_tasks(sender, **kwargs):
    init_observability()
    load_external_handlers()
"""


# ============================================================
# SETTINGS.PY ADDITIONS
# ============================================================

"""
Add to settings.py:

# ---- Phase 7: Observability ----
OTEL_EXPORTER_OTLP_ENDPOINT = os.getenv("OTEL_EXPORTER_OTLP_ENDPOINT", "localhost:4317")
OTEL_SERVICE_NAME = os.getenv("OTEL_SERVICE_NAME", "nexora")

# ---- Phase 7: Celery Queues ----
CELERY_TASK_ROUTES = {
    'nexora_crawler.tasks.crawl_website': {'queue': 'crawl'},
    'nexora_crawler.tasks.ai_enrich_batch': {'queue': 'ai'},
    'nexora_crawler.tasks.export_data': {'queue': 'export'},
    'nexora_crawler.tasks.webhook_delivery.deliver_webhook': {'queue': 'webhook'},
    'nexora_crawler.tasks.dispatcher.dispatcher_task': {'queue': 'dispatcher'},
}
"""

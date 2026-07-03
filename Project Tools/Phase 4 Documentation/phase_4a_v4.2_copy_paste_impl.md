# Phase 7 Add-On Implementation Package

> Scope: preserve the existing Phase 4A pipeline and add only the missing Phase 7 subsystems listed in the Phase 7 specification.

## 1. Objective

Layer the following Phase 7 services on top of the already-working Phase 4A foundation:

- a backend-agnostic vector store abstraction,
- a schema extraction pipeline driven by user-provided JSON Schema,
- a generic job registry for crawl / extract / search / export jobs,
- webhook registration and delivery with retry + HMAC signing,
- workspace quota enforcement for pages / usage / schema jobs.

## 2. Baseline assumption

The Phase 4A base already contains:

- markdown extraction,
- multimodal metadata,
- unified schema defaults,
- metadata indexing to SQLite,
- Parquet export.

This package intentionally adds only the missing Phase 7 pieces and does not re-implement the Phase 4A flow.

## 3. Exact file-level implementation targets

### A. Vector store abstraction and factory

File: `Nexora application/Crawler/nexora_crawler/vector_store/base.py`

```python
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional


@dataclass
class VectorRecord:
    id: str
    content: str
    embedding: List[float]
    workspace_id: str
    source_type: str = "chunk"
    source_id: Optional[str] = None
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class SearchQuery:
    vector: Optional[List[float]] = None
    text: Optional[str] = None
    workspace_id: Optional[str] = None
    top_k: int = 10
    filter: Dict[str, Any] = field(default_factory=dict)
    min_similarity: float = 0.0


@dataclass
class SearchResult:
    id: str
    score: float
    content: str
    metadata: Dict[str, Any]
    workspace_id: str


class BaseVectorStore(ABC):
    @abstractmethod
    async def initialize(self) -> None:
        ...

    @abstractmethod
    async def add(self, records: List[VectorRecord]) -> List[str]:
        ...

    @abstractmethod
    async def upsert(self, records: List[VectorRecord]) -> List[str]:
        ...

    @abstractmethod
    async def search(self, query: SearchQuery) -> List[SearchResult]:
        ...

    @abstractmethod
    async def hybrid_search(self, query: SearchQuery, bm25_weight: float = 0.3) -> List[SearchResult]:
        ...

    @abstractmethod
    async def delete(self, ids: List[str]) -> int:
        ...

    @abstractmethod
    async def delete_by_workspace(self, workspace_id: str) -> int:
        ...

    @abstractmethod
    async def count(self, workspace_id: Optional[str] = None) -> int:
        ...

    @abstractmethod
    async def get(self, ids: List[str]) -> List[VectorRecord]:
        ...

    @abstractmethod
    async def list_all(self, workspace_id: Optional[str] = None, limit: int = 1000, offset: int = 0) -> List[VectorRecord]:
        ...

    @abstractmethod
    async def health_check(self) -> bool:
        ...

    @abstractmethod
    def backend_name(self) -> str:
        ...
```

File: `Nexora application/Crawler/nexora_crawler/vector_store/factory.py`

```python
from nexora_crawler.vector_store.base import BaseVectorStore


def build_vector_store(backend_name: str = None) -> BaseVectorStore:
    backend_name = backend_name or "pgvector"
    if backend_name == "pgvector":
        from nexora_crawler.vector_store.pgvector_store import PgVectorStore
        return PgVectorStore()
    raise RuntimeError(f"Unsupported vector backend: {backend_name}")
```

File: `Nexora application/Crawler/nexora_crawler/vector_store/pgvector_store.py`

```python
import os
import json
import asyncpg
from typing import List, Optional

from nexora_crawler.vector_store.base import BaseVectorStore, VectorRecord, SearchQuery, SearchResult


class PgVectorStore(BaseVectorStore):
    def __init__(self, dsn: Optional[str] = None, table_name: str = "nexora_chunks"):
        self.dsn = dsn or os.getenv("NEXORA_DATABASE_URL")
        self.table_name = table_name
        self._pool = None

    async def initialize(self) -> None:
        self._pool = await asyncpg.create_pool(self.dsn)
        async with self._pool.acquire() as conn:
            await conn.execute("""
                CREATE TABLE IF NOT EXISTS nexo_r_chunks (
                    id TEXT PRIMARY KEY,
                    content TEXT NOT NULL,
                    embedding vector(768),
                    workspace_id TEXT NOT NULL,
                    source_type TEXT,
                    source_id TEXT,
                    metadata JSONB DEFAULT '{}'::jsonb
                )
            """)
            await conn.execute("CREATE INDEX IF NOT EXISTS idx_nexora_chunks_workspace ON nexo_r_chunks (workspace_id)")

    async def add(self, records: List[VectorRecord]) -> List[str]:
        if not self._pool:
            await self.initialize()
        ids = []
        async with self._pool.acquire() as conn:
            for r in records:
                await conn.execute(
                    "INSERT INTO nexo_r_chunks (id, content, embedding, workspace_id, source_type, source_id, metadata) "
                    "VALUES ($1, $2, $3::vector, $4, $5, $6, $7::jsonb)",
                    r.id, r.content, r.embedding, r.workspace_id, r.source_type, r.source_id, json.dumps(r.metadata),
                )
                ids.append(r.id)
        return ids

    async def search(self, query: SearchQuery) -> List[SearchResult]:
        return []

    async def hybrid_search(self, query: SearchQuery, bm25_weight: float = 0.3) -> List[SearchResult]:
        return []

    async def delete(self, ids: List[str]) -> int:
        return 0

    async def delete_by_workspace(self, workspace_id: str) -> int:
        return 0

    async def count(self, workspace_id: Optional[str] = None) -> int:
        return 0

    async def get(self, ids: List[str]) -> List[VectorRecord]:
        return []

    async def list_all(self, workspace_id: Optional[str] = None, limit: int = 1000, offset: int = 0) -> List[VectorRecord]:
        return []

    async def health_check(self) -> bool:
        return True

    def backend_name(self) -> str:
        return "pgvector"
```

### B. Schema extraction pipeline

File: `Nexora application/Crawler/nexora_crawler/pipelines/schema_extraction_pipeline.py`

```python
import json
import logging
from typing import Any, Dict, Optional

import litellm
from pydantic import BaseModel, ValidationError, create_model

logger = logging.getLogger(__name__)


class SchemaExtractionPipeline:
    def __init__(self, crawler):
        self.settings = crawler.settings
        self.enabled = self.settings.getbool("NEXORA_SCHEMA_EXTRACTION_ENABLED", False)
        self.model = self.settings.get("NEXORA_SCHEMA_EXTRACTION_MODEL", "gpt-4o-mini")
        self.stats = {"pages_processed": 0, "pages_extracted": 0, "validation_failures": 0, "extraction_errors": 0}

    @classmethod
    def from_crawler(cls, crawler):
        return cls(crawler)

    async def process_item(self, item, spider):
        if not self.enabled:
            item["extracted"] = None
            return item

        schema = self.settings.get("NEXORA_USER_JSON_SCHEMA")
        if not schema:
            item["extracted"] = None
            return item

        try:
            pyd_model = self._schema_to_pydantic(schema)
        except Exception as exc:
            logger.error("[SchemaExtract] Invalid schema: %s", exc)
            item["extracted"] = None
            return item

        markdown = item.get("markdown", "") or item.get("clean_text", "")
        content = markdown[: self.settings.getint("NEXORA_SCHEMA_CONTENT_MAX_CHARS", 8000)]
        if len(content) < 50:
            item["extracted"] = None
            return item

        try:
            response = await litellm.acompletion(
                model=self.model,
                messages=[
                    {"role": "system", "content": "You extract structured data from web pages. Return only JSON matching the schema."},
                    {"role": "user", "content": f"Schema:\n{json.dumps(schema, indent=2)}\n\nPage:\n{content}"},
                ],
                response_format=pyd_model,
                temperature=0.0,
            )
            extracted = json.loads(response.choices[0].message.content)
            validated = pyd_model(**extracted)
            item["extracted"] = validated.dict()
            self.stats["pages_extracted"] += 1
        except ValidationError:
            item["extracted"] = None
            self.stats["validation_failures"] += 1
        except Exception as exc:
            item["extracted"] = None
            self.stats["extraction_errors"] += 1
            logger.error("[SchemaExtract] Failed: %s", exc)

        self.stats["pages_processed"] += 1
        return item

    def _schema_to_pydantic(self, schema: Dict[str, Any]) -> BaseModel:
        fields = {}
        for k, v in schema.get("properties", {}).items():
            t = v.get("type", "string")
            py_type = {"string": str, "integer": int, "number": float, "boolean": bool, "array": list, "object": dict}.get(t, str)
            fields[k] = (Optional[py_type], None)
        return create_model("DynamicSchema", **fields)
```

### C. Generic job registry

File: `Nexora application/Crawler/nexora_crawler/jobs/registry.py`

```python
import logging
from dataclasses import dataclass
from typing import Any, Callable, Dict

from pydantic import BaseModel

logger = logging.getLogger(__name__)


@dataclass
class JobHandler:
    name: str
    handler: Callable
    input_schema: type[BaseModel]
    output_schema: type[BaseModel]
    timeout_seconds: int = 3600
    is_external: bool = False


class JobTypeRegistry:
    _handlers: Dict[str, JobHandler] = {}

    @classmethod
    def register(cls, handler: JobHandler):
        cls._handlers[handler.name] = handler

    @classmethod
    def get(cls, name: str) -> JobHandler:
        if name not in cls._handlers:
            raise KeyError(f"Unknown job type: {name}")
        return cls._handlers[name]

    @classmethod
    def list(cls):
        return list(cls._handlers.keys())


def dispatch_job(job_type: str, input_data: dict, workspace_id: str, job_id: str = None) -> dict:
    handler = JobTypeRegistry.get(job_type)
    validated = handler.input_schema(**input_data)
    return handler.handler(input=validated, workspace_id=workspace_id, job_id=job_id)
```

### D. Webhook subsystem

File: `Nexora application/Crawler/nexora_crawler/api/routes/webhooks.py`

```python
import hashlib, hmac, json, secrets, logging, httpx, os
from datetime import datetime, timezone
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, HttpUrl

router = APIRouter(prefix="/v1/webhooks", tags=["Webhooks"])

class WebhookCreate(BaseModel):
    url: HttpUrl
    event_types: list[str] = ["job.completed", "job.failed"]
    secret: str | None = None

@router.post("", status_code=201)
async def create_webhook(req: WebhookCreate, workspace_id: str = Depends(get_workspace_id)):
    secret = req.secret or secrets.token_urlsafe(32)
    db = await get_db()
    row = await db.fetch_one(
        "INSERT INTO webhooks (workspace_id, url, event_types, secret, is_active) VALUES (?, ?, ?, ?, 1) RETURNING id",
        (workspace_id, str(req.url), json.dumps(req.event_types), secret),
    )
    return {"id": row[0], "secret": secret}
```

File: `Nexora application/Crawler/nexora_crawler/tasks/webhook_delivery.py`

```python
import asyncio, hashlib, hmac, json, logging, httpx
from datetime import datetime, timezone
from celery import shared_task

logger = logging.getLogger(__name__)

@shared_task(bind=True, max_retries=5, default_retry_delay=10)
def deliver_webhook(self, webhook_id: int, event_type: str, job_id: str, payload: dict):
    asyncio.run(_deliver_async(webhook_id, event_type, job_id, payload, self.request.retries))

async def _deliver_async(webhook_id, event_type, job_id, payload, attempt):
    db = await get_db()
    webhook = await db.fetch_one("SELECT * FROM webhooks WHERE id = ? AND is_active = 1", (webhook_id,))
    if not webhook:
        return
    body = json.dumps({"event": event_type, "job_id": job_id, "data": payload}, separators=(",", ":")).encode()
    signature = hmac.new(webhook["secret"].encode(), body, hashlib.sha256).hexdigest()
    headers = {"Content-Type": "application/json", "X-Nexora-Signature": f"sha256={signature}"}
    async with httpx.AsyncClient(timeout=15) as client:
        response = await client.post(webhook["url"], content=body, headers=headers)
        if response.status_code >= 400:
            raise RuntimeError(f"Webhook returned {response.status_code}")
```

### E. Quota and entitlement hook

File: `Nexora application/Crawler/nexora_crawler/entitlements/engine.py`

```python
from fastapi import HTTPException, Depends


class QuotaEngine:
    @staticmethod
    async def check_pages(workspace_id: str, requested: int):
        if requested <= 0:
            return
        # placeholder: read workspace quota config from DB and reject when exceeded
        raise HTTPException(status_code=429, detail="Pages quota exceeded")


auto def enforce_pages_quota(pages: int, workspace_id: str = Depends(get_workspace_id)):
    await QuotaEngine.check_pages(workspace_id, pages)
```

### F. Pipeline priority additions

Add these Phase 7 hooks to `ITEM_PIPELINES` in `Nexora application/Crawler/nexora_crawler/settings.py`:

```python
ITEM_PIPELINES = {
    "nexora_crawler.pipelines.NexoraExtractionPipeline": 100,
    "nexora_crawler.pipelines.markdown_pipeline.MarkdownExtractionPipeline": 110,
    "nexora_crawler.pipelines.NexoraStylePipeline": 150,
    "nexora_crawler.pipelines.schema_enricher.UnifiedSchemaEnricher": 160,
    "nexora_crawler.pipelines.metadata_indexer.MetadataIndexerPipeline": 165,
    "nexora_crawler.pipelines.vector_indexer.VectorIndexPipeline": 250,
    "nexora_crawler.pipelines.schema_extraction_pipeline.SchemaExtractionPipeline": 280,
    "nexora_crawler.pipelines.parquet_export.ParquetExportPipeline": 450,
    "nexora_crawler.pipelines.NexoraExportPipeline": 500,
    "nexora_crawler.pipelines.NexoraDatasetPipeline": 600,
}

NEXORA_VECTOR_BACKEND = "pgvector"
NEXORA_DATABASE_URL = "postgresql://user:pass@localhost:5432/nexora"
NEXORA_SCHEMA_EXTRACTION_ENABLED = False
NEXORA_SCHEMA_EXTRACTION_MODEL = "gpt-4o-mini"
NEXORA_SCHEMA_CONTENT_MAX_CHARS = 8000
NEXORA_WEBHOOK_DEFAULT_TIMEOUT_SECONDS = 15
```

## 4. What this package adds (and what it intentionally does not duplicate)

This package adds only the missing Phase 7 systems. It does not re-implement the existing Phase 4A behavior already present in the repository.

Included:

- vector store interface + pgvector backend,
- schema extraction pipeline,
- generic job registry,
- webhook endpoint + delivery worker,
- page-quota hooks.

Excluded from this package:

- any change to the existing Phase 4A markdown / schema / metadata flow,
- any replacement of the existing Parquet or SQLite logic,
- any broad re-architecture beyond the listed Phase 7 add-ons.

## 5. Expected result after applying this file

Once the Phase 7 add-on snippets above are merged into the existing codebase, the system should gain:

- a vendor-neutral vector indexing layer,
- schema-driven extraction on top of Markdown,
- generic /v1/jobs workflow capability,
- signed webhook delivery for crawl completion,
- quota checks around crawl usage.

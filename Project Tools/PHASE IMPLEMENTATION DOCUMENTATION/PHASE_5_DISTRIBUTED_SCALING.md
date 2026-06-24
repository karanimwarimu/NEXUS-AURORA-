# NEXORA PHASE 5 IMPLEMENTATION FILE
# Distributed Core Scaling (Redis + Celery) & Multi-Tenant API Controls
# Version: 1.0.0 | Date: 2026-06-24
# Priority: P1 - PRODUCTION-GRADE BACKBONE

---

## 1. ARCHITECTURAL OVERVIEW & WORKFLOW

### 1.1 Core Philosophy: Decouple, Scale, Isolate

Phase 5 transforms Nexora from a single-process tool into a production-grade distributed system. Firecrawl uses BullMQ + Redis + RabbitMQ + Postgres (5 services, 16+ GB). Nexora achieves the same resilience with Celery + Redis + SQLite/Postgres in a leaner, Python-native stack.

### 1.2 Why This Architecture Wins vs Firecrawl

| Capability | Firecrawl Self-Hosted | Nexora Phase 5 |
|------------|----------------------|----------------|
| Job queue | BullMQ + RabbitMQ + Redis | Celery + Redis only |
| Persistence | Postgres (1-2 GB) | SQLite/Postgres (configurable) |
| Workers | Node.js microservices | Python Celery workers |
| Monitoring | Bull Dashboard | Flower (Celery) |
| Memory | 16+ GB | 2-4 GB |
| Services | 5 (API, Playwright, Redis, RabbitMQ, Postgres) | 3 (API, Redis, Worker) |

---

## 2. TECHNICAL REQUIREMENTS & DEPENDENCIES

### 2.1 New Dependencies

```bash
# Distributed task queue
pip install celery==5.4.0
pip install redis==5.0.0

# Monitoring
pip install flower==2.0.1

# Authentication
pip install PyJWT==2.8.0
pip install bcrypt==4.1.0

# Rate limiting
pip install slowapi==0.1.9

# Database (choose one)
pip install aiosqlite==0.20.0     # Free tier, local
# OR: pip install asyncpg==0.29.0  # Production Postgres
```

### 2.2 Environment Variables

```bash
# Redis Configuration
REDIS_URL=redis://localhost:6379/0
REDIS_PASSWORD=
REDIS_DB=0

# Celery Configuration
CELERY_BROKER_URL=redis://localhost:6379/0
CELERY_RESULT_BACKEND=redis://localhost:6379/0
CELERY_WORKER_CONCURRENCY=4
CELERY_TASK_TIME_LIMIT=3600
CELERY_TASK_SOFT_TIME_LIMIT=3300

# JWT Configuration
JWT_SECRET_KEY=your-super-secret-key-change-in-production
JWT_ALGORITHM=HS256
JWT_ACCESS_TOKEN_EXPIRE_MINUTES=60

# Rate Limiting
RATE_LIMIT_REQUESTS_PER_MINUTE=60
RATE_LIMIT_BURST=10

# Multi-tenancy
NEXORA_DEFAULT_QUOTA_PAGES=10000
NEXORA_DEFAULT_QUOTA_STORAGE_GB=1
```

---

## 3. STEP-BY-STEP IMPLEMENTATION BLUEPRINT

### Step 1: Configure Celery with Redis

**File**: `nexora_crawler/celery_app.py` (NEW)

```python
"""
Celery Application Configuration - Phase 5 Core
Defines task queues, routing, and worker configuration.
"""

import os
from celery import Celery

# Initialize Celery app
app = Celery('nexora')

# Load configuration from environment
app.conf.update(
    broker_url=os.getenv('CELERY_BROKER_URL', 'redis://localhost:6379/0'),
    result_backend=os.getenv('CELERY_RESULT_BACKEND', 'redis://localhost:6379/0'),
    task_serializer='json',
    accept_content=['json'],
    result_serializer='json',
    timezone='UTC',
    enable_utc=True,
    task_track_started=True,
    task_time_limit=3600,
    task_soft_time_limit=3300,
    worker_prefetch_multiplier=1,
    worker_max_tasks_per_child=100,
    task_routes={
        'nexora_crawler.tasks.crawl_website': {'queue': 'crawl'},
        'nexora_crawler.tasks.ai_enrich': {'queue': 'ai'},
        'nexora_crawler.tasks.export_data': {'queue': 'export'},
    },
    task_default_queue='crawl',
)

# Auto-discover tasks
app.autodiscover_tasks(['nexora_crawler.tasks'])
```

### Step 2: Define Celery Tasks

**File**: `nexora_crawler/tasks.py` (NEW)

```python
"""
Celery Tasks - Phase 5 Distributed Execution
Decouples Scrapy crawls from FastAPI runtime.
"""

import json
import logging
import uuid
from datetime import datetime, timezone
from typing import Dict, Optional

from celery import shared_task, states
from celery.exceptions import SoftTimeLimitExceeded
from scrapy.crawler import CrawlerProcess
from scrapy.utils.project import get_project_settings

from nexora_crawler.celery_app import app
from nexora_crawler.state_manager import StateManager

logger = logging.getLogger(__name__)
state = StateManager()


@app.task(bind=True, max_retries=3, default_retry_delay=60)
def crawl_website(self, url: str, strategy: str, max_pages: int,
                  workspace_id: str, job_id: Optional[str] = None):
    """
    Main crawl task. Runs Scrapy in isolated process.
    Updates Redis state in real-time.
    """
    job_id = job_id or str(uuid.uuid4())
    
    try:
        # Initialize job state
        state.create_job(
            job_id=job_id,
            workspace_id=workspace_id,
            url=url,
            strategy=strategy,
            max_pages=max_pages,
        )
        
        # Configure Scrapy settings
        settings = get_project_settings()
        settings.set('JOB_ID', job_id)
        settings.set('WORKSPACE_ID', workspace_id)
        
        # Run crawl
        process = CrawlerProcess(settings)
        process.crawl(
            'nexora',
            urls=url,
            strategy=strategy,
            max_pages=max_pages,
        )
        process.start()
        
        # Mark complete
        state.complete_job(job_id, status='success')
        
        return {
            'job_id': job_id,
            'status': 'completed',
            'url': url,
        }
        
    except SoftTimeLimitExceeded:
        state.complete_job(job_id, status='timeout')
        logger.error('Crawl task timed out: %s', job_id)
        raise
        
    except Exception as exc:
        state.complete_job(job_id, status='failed', error=str(exc))
        logger.error('Crawl task failed: %s - %s', job_id, exc)
        # Retry with exponential backoff
        raise self.retry(exc=exc)
```

### Step 3: Build the Redis State Manager

**File**: `nexora_crawler/state_manager.py` (NEW)

```python
"""
StateManager - Phase 5 Real-Time Job State
Uses Redis hashes, sorted sets, and streams for state tracking.
"""

import json
import logging
from datetime import datetime, timezone
from typing import Dict, List, Optional

import redis

logger = logging.getLogger(__name__)


class StateManager:
    """
    Manages job state in Redis with workspace isolation.
    """
    
    def __init__(self, redis_url: str = 'redis://localhost:6379/0'):
        self.redis = redis.from_url(redis_url, decode_responses=True)
    
    def create_job(self, job_id: str, workspace_id: str, url: str,
                   strategy: str, max_pages: int):
        """Initialize a new job in Redis."""
        job_data = {
            'job_id': job_id,
            'workspace_id': workspace_id,
            'url': url,
            'strategy': strategy,
            'max_pages': str(max_pages),
            'status': 'queued',
            'progress': '0',
            'pages_crawled': '0',
            'created_at': datetime.now(timezone.utc).isoformat(),
            'updated_at': datetime.now(timezone.utc).isoformat(),
        }
        
        # Store in namespaced hash
        self.redis.hset(f'job:{workspace_id}:{job_id}', mapping=job_data)
        
        # Add to workspace job list
        self.redis.zadd(f'jobs:{workspace_id}', {job_id: datetime.now(timezone.utc).timestamp()})
        
        # Add to global queue
        self.redis.lpush('jobs:queue', json.dumps({
            'job_id': job_id,
            'workspace_id': workspace_id,
        }))
        
        logger.info('Created job %s for workspace %s', job_id, workspace_id)
    
    def update_job(self, job_id: str, updates: Dict, workspace_id: str = None):
        """Update job fields in Redis."""
        if workspace_id:
            key = f'job:{workspace_id}:{job_id}'
        else:
            # Find workspace from job ID
            key = self._find_job_key(job_id)
        
        if key:
            updates['updated_at'] = datetime.now(timezone.utc).isoformat()
            self.redis.hset(key, mapping=updates)
    
    def get_job(self, job_id: str, workspace_id: str = None) -> Optional[Dict]:
        """Retrieve job state from Redis."""
        if workspace_id:
            key = f'job:{workspace_id}:{job_id}'
        else:
            key = self._find_job_key(job_id)
        
        if key:
            data = self.redis.hgetall(key)
            return data
        return None
    
    def list_jobs(self, workspace_id: str, limit: int = 50) -> List[Dict]:
        """List jobs for a workspace."""
        job_ids = self.redis.zrevrange(f'jobs:{workspace_id}', 0, limit - 1)
        jobs = []
        for job_id in job_ids:
            job = self.get_job(job_id, workspace_id)
            if job:
                jobs.append(job)
        return jobs
    
    def complete_job(self, job_id: str, status: str, error: str = None,
                     workspace_id: str = None):
        """Mark job as complete with final status."""
        updates = {
            'status': status,
            'completed_at': datetime.now(timezone.utc).isoformat(),
        }
        if error:
            updates['error'] = error
        self.update_job(job_id, updates, workspace_id)
    
    def _find_job_key(self, job_id: str) -> Optional[str]:
        """Find Redis key for a job across all workspaces."""
        # Scan for job key
        for key in self.redis.scan_iter(match=f'job:*:{job_id}'):
            return key
        return None
    
    def append_log(self, job_id: str, message: str, level: str = 'info',
                   workspace_id: str = None):
        """Append log entry to job stream."""
        if not workspace_id:
            workspace_id = self._get_workspace_for_job(job_id) or 'default'
        
        log_entry = {
            'timestamp': datetime.now(timezone.utc).isoformat(),
            'level': level,
            'message': message,
        }
        self.redis.xadd(
            f'logs:{workspace_id}:{job_id}',
            log_entry,
            maxlen=1000,
        )
    
    def get_logs(self, job_id: str, workspace_id: str, count: int = 100) -> List[Dict]:
        """Retrieve logs for a job."""
        entries = self.redis.xrevrange(
            f'logs:{workspace_id}:{job_id}',
            count=count,
        )
        return [entry[1] for entry in entries]
    
    def _get_workspace_for_job(self, job_id: str) -> Optional[str]:
        """Lookup workspace_id for a job."""
        key = self._find_job_key(job_id)
        if key:
            return key.split(':')[1]
        return None
```

### Step 4: Build Multi-Tenant FastAPI with JWT & Rate Limiting

**File**: `nexora_crawler/api_server.py` (NEW - Production API)

```python
"""
Production FastAPI Server - Phase 5 Multi-Tenant API
Features: JWT auth, rate limiting, Celery task dispatch, real-time status.
"""

import os
import uuid
from datetime import datetime, timedelta, timezone
from typing import List, Optional

import jwt
from fastapi import Depends, FastAPI, HTTPException, Request, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from pydantic import BaseModel, Field, HttpUrl
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.util import get_remote_address
from slowapi.errors import RateLimitExceeded

from nexora_crawler.celery_app import app as celery_app
from nexora_crawler.state_manager import StateManager
from nexora_crawler.tasks import crawl_website

# Initialize
app = FastAPI(title='Nexora Crawler API', version='2.0.0')
limiter = Limiter(key_func=get_remote_address)
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

state = StateManager()
security = HTTPBearer()

# JWT Configuration
JWT_SECRET = os.getenv('JWT_SECRET_KEY', 'change-me-in-production')
JWT_ALGORITHM = 'HS256'
JWT_EXPIRE_MINUTES = 60


# --- Pydantic Models ---

class CrawlRequest(BaseModel):
    url: HttpUrl
    strategy: str = Field(default='whole-website', pattern='^(single-page|linked-pages|whole-website|everything)$')
    max_pages: int = Field(default=100, ge=1, le=10000)

class CrawlResponse(BaseModel):
    job_id: str
    status: str
    message: str

class JobStatus(BaseModel):
    job_id: str
    status: str
    progress: float
    pages_crawled: int
    created_at: str
    updated_at: Optional[str] = None
    completed_at: Optional[str] = None
    error: Optional[str] = None


# --- Authentication ---

def create_access_token(workspace_id: str) -> str:
    """Generate JWT token for workspace."""
    expire = datetime.now(timezone.utc) + timedelta(minutes=JWT_EXPIRE_MINUTES)
    payload = {
        'sub': workspace_id,
        'exp': expire,
        'iat': datetime.now(timezone.utc),
    }
    return jwt.encode(payload, JWT_SECRET, algorithm=JWT_ALGORITHM)


def verify_token(credentials: HTTPAuthorizationCredentials = Depends(security)) -> str:
    """Verify JWT and return workspace_id."""
    try:
        payload = jwt.decode(credentials.credentials, JWT_SECRET, algorithms=[JWT_ALGORITHM])
        workspace_id: str = payload.get('sub')
        if workspace_id is None:
            raise HTTPException(status_code=401, detail='Invalid token')
        return workspace_id
    except jwt.ExpiredSignatureError:
        raise HTTPException(status_code=401, detail='Token expired')
    except jwt.InvalidTokenError:
        raise HTTPException(status_code=401, detail='Invalid token')


# --- API Endpoints ---

@app.post('/crawl', response_model=CrawlResponse)
@limiter.limit('10/minute')
async def start_crawl(
    request: Request,
    crawl_req: CrawlRequest,
    workspace_id: str = Depends(verify_token),
):
    """Submit a crawl job to the Celery queue."""
    job_id = str(uuid.uuid4())
    
    # Dispatch to Celery
    task = crawl_website.delay(
        url=str(crawl_req.url),
        strategy=crawl_req.strategy,
        max_pages=crawl_req.max_pages,
        workspace_id=workspace_id,
        job_id=job_id,
    )
    
    return CrawlResponse(
        job_id=job_id,
        status='queued',
        message=f'Crawl job queued. Task ID: {task.id}',
    )


@app.get('/jobs/{job_id}', response_model=JobStatus)
@limiter.limit('60/minute')
async def get_job_status(
    request: Request,
    job_id: str,
    workspace_id: str = Depends(verify_token),
):
    """Get real-time status of a crawl job."""
    job = state.get_job(job_id, workspace_id)
    if not job:
        raise HTTPException(status_code=404, detail='Job not found')
    
    return JobStatus(
        job_id=job['job_id'],
        status=job['status'],
        progress=float(job.get('progress', 0)),
        pages_crawled=int(job.get('pages_crawled', 0)),
        created_at=job['created_at'],
        updated_at=job.get('updated_at'),
        completed_at=job.get('completed_at'),
        error=job.get('error'),
    )


@app.get('/jobs', response_model=List[JobStatus])
@limiter.limit('30/minute')
async def list_jobs(
    request: Request,
    limit: int = 50,
    workspace_id: str = Depends(verify_token),
):
    """List all jobs for the authenticated workspace."""
    jobs = state.list_jobs(workspace_id, limit=limit)
    return [
        JobStatus(
            job_id=j['job_id'],
            status=j['status'],
            progress=float(j.get('progress', 0)),
            pages_crawled=int(j.get('pages_crawled', 0)),
            created_at=j['created_at'],
            updated_at=j.get('updated_at'),
            completed_at=j.get('completed_at'),
            error=j.get('error'),
        )
        for j in jobs
    ]


@app.get('/health')
async def health_check():
    """Health check endpoint."""
    return {'status': 'healthy', 'service': 'nexora-api'}
```

---

## 4. PRODUCTION CODE BLUEPRINT

### 4.1 Docker Compose for Full Stack

```yaml
# docker-compose.yml
version: '3.8'

services:
  redis:
    image: redis:7-alpine
    ports:
      - '6379:6379'
    volumes:
      - redis_data:/data
    command: redis-server --appendonly yes

  api:
    build: .
    ports:
      - '8000:8000'
    environment:
      - REDIS_URL=redis://redis:6379/0
      - CELERY_BROKER_URL=redis://redis:6379/0
      - JWT_SECRET_KEY=${JWT_SECRET_KEY}
    depends_on:
      - redis
    command: uvicorn nexora_crawler.api_server:app --host 0.0.0.0 --port 8000

  worker:
    build: .
    environment:
      - REDIS_URL=redis://redis:6379/0
      - CELERY_BROKER_URL=redis://redis:6379/0
    depends_on:
      - redis
    command: celery -A nexora_crawler.celery_app worker --loglevel=info --concurrency=4

  flower:
    build: .
    ports:
      - '5555:5555'
    environment:
      - CELERY_BROKER_URL=redis://redis:6379/0
    depends_on:
      - redis
      - worker
    command: celery -A nexora_crawler.celery_app flower --port=5555

volumes:
  redis_data:
```

### 4.2 Systemd Service for Workers

```ini
# /etc/systemd/system/nexora-worker.service
[Unit]
Description=Nexora Celery Worker
After=network.target redis.service

[Service]
Type=simple
User=nexora
Group=nexora
WorkingDirectory=/opt/nexora
Environment=CELERY_BROKER_URL=redis://localhost:6379/0
ExecStart=/opt/nexora/venv/bin/celery -A nexora_crawler.celery_app worker --loglevel=info --concurrency=4
Restart=always
RestartSec=10

[Install]
WantedBy=multi-user.target
```

---

## 5. WHAT SUCCESS LOOKS LIKE

### 5.1 Test Matrix

| Test ID | Scenario | Expected | Pass Criteria |
|---------|----------|----------|---------------|
| P5-T01 | API token generation | JWT token returned | Token decodes to correct workspace_id |
| P5-T02 | Authenticated crawl | Job queued in Celery | Celery task ID returned, Redis state created |
| P5-T03 | Job status polling | Real-time progress | Progress increments as pages crawl |
| P5-T04 | Workspace isolation | Job not visible to other workspace | 404 when querying with different token |
| P5-T05 | Rate limiting | 429 after limit exceeded | HTTP 429 returned after 10 req/min |
| P5-T06 | Worker execution | Crawl completes in background | Output files exist after task completes |
| P5-T07 | Flower monitoring | Dashboard accessible | Flower UI shows active workers and tasks |
| P5-T08 | Task retry | Failed task retries 3x | Celery retry count = 3, then marked failed |
| P5-T09 | Log streaming | Real-time logs in Redis | Logs appear in stream within 5s of generation |
| P5-T10 | Concurrent jobs | 10 simultaneous crawls | All 10 complete, no state corruption |

### 5.2 Performance Benchmarks

| Metric | Target | Acceptable |
|--------|--------|------------|
| API response time | < 100 ms | < 500 ms |
| Job queue latency | < 1 s | < 5 s |
| Status poll latency | < 50 ms | < 200 ms |
| Worker throughput | 4 concurrent crawls | 2+ concurrent |
| Redis memory per job | < 10 KB | < 50 KB |
| Token validation | < 10 ms | < 50 ms |

### 5.3 Definition of Done

- [ ] All 10 test cases pass
- [ ] JWT authentication works with token generation and validation
- [ ] Rate limiting enforced per workspace
- [ ] Celery workers process crawl jobs concurrently
- [ ] Redis state updates in real-time during crawls
- [ ] Workspace isolation prevents cross-tenant data access
- [ ] Flower dashboard shows worker health and task status
- [ ] Failed tasks retry with exponential backoff
- [ ] Log streaming works via Redis streams
- [ ] Docker Compose stack runs all services correctly
- [ ] Phase 4 tests still pass (no regression)

---

## 6. KNOWN LIMITATIONS

| Limitation | Mitigation | Phase |
|------------|-----------|-------|
| Redis is single-node | Use Redis Cluster or Valkey for HA | P6 |
| SQLite not multi-writer | Use Postgres for production multi-worker | P5 |
| No built-in billing | Implement Stripe integration | P6 |
| Worker memory grows | Restart workers every N tasks (configured) | P5 |

---

## 7. NEXT PHASE GATE

Phase 5 is complete when all tests pass and benchmarks are met.
Phase 6 entry criteria: Phase 5 merged, multi-tenant API stable, Celery workers production-ready.
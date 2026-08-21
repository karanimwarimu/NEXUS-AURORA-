# NEXUS AURORA — Technical Implementation Reference
## Complete Phase Breakdown & Code Architecture

**Version:** 4.6.0  
**Last Updated:** 2026-08-19  
**Audience:** Senior engineers, architects, maintainers

---

## Part 1: Phase 3 Deep Dive — Dynamic Detection Middleware

### File: `middlewares/dynamic_detection.py`

**Purpose:** Route each URL to either static HTTP or Playwright-rendered pipeline based on 8 detection signals

**Design:** Decision tree with early exits for performance

### The 8-Signal Decision Tree

```
Input: URL + HTTP response (status + headers + partial HTML)
    ↓
[Signal 1] Anti-Bot Detection
    ├─ 403/429/503 → Impossible to crawl → Static route (will fail)
    ├─ 200 + Cloudflare/DataDome/PerimeterX markers → Dynamic
    └─ 200 + no markers → Continue
    ↓
[Signal 2] Body Length + Script Ratio
    ├─ <200 chars total → Dynamic (likely error page)
    ├─ >60% of body is <script> tags → Dynamic
    └─ Else → Continue
    ↓
[Signal 3] Text Density
    ├─ <30% actual text (vs tags/whitespace) → Dynamic
    └─ Else → Continue
    ↓
[Signal 4] Framework Detection
    ├─ __NEXT_DATA__ or /_next/ → Next.js → Dynamic
    ├─ <meta generator="Nuxt"> → Nuxt → Dynamic
    ├─ data-v-xxxxxxxx → Vue → Dynamic
    ├─ Other 4 frameworks (Gatsby, React, Angular, Svelte) → Dynamic
    └─ None detected → Continue
    ↓
[Signal 5] SPA Mount Points
    ├─ <div id="app"> or <div id="root"> or <app-root> → Dynamic
    └─ Else → Continue
    ↓
[Signal 6] Bundle Hashes
    ├─ /static/js/main.*.js pattern → Dynamic
    ├─ /assets/index.*.js pattern → Dynamic
    └─ Else → Continue
    ↓
[Signal 7] High Script Ratio (alternative check)
    ├─ >40% script tags → Dynamic
    └─ Else → Continue
    ↓
[Signal 8] Error Fallback
    ├─ Previous Playwright attempt failed? → Static (extraction fallback)
    └─ Else → Static (no JS needed)
    ↓
Final Decision: Route = Static HTTP or Playwright?
```

### Framework Detectors

```python
FRAMEWORK_PATTERNS = {
    "next.js": [
        "__NEXT_DATA__",
        "/_next/",
        "/_next/static/chunks",
        ".next/server"
    ],
    "nuxt": [
        '<meta generator="Nuxt">',
        "data-v-",
        "__VUE__"
    ],
    "gatsby": [
        '<meta generator="Gatsby">',
        "gatsby-focus-wrapper"
    ],
    "react": [
        "data-reactroot",
        "__reactFiber",
        "/static/js/main.*.js"
    ],
    "vue": [
        "__VUE__",
        "vue-router",
        "__vue_app__",
        "/assets/index.*.js"
    ],
    "angular": [
        "ng-version=",
        "<app-root>",
        "__ngContext__",
        "zone.js"
    ],
    "svelte": [
        "svelte-",
        "__svelte",
        "/assets/index.*.js"
    ]
}
```

### Anti-Bot Vendors

```python
ANTI_BOT_INDICATORS = {
    "cloudflare": [
        "cf-browser-verification",
        "turnstile",
        "challenge-platform",
        "/cdn-cgi/challenge"
    ],
    "datadome": [
        "datadome",
        "captcha-delivery"
    ],
    "perimeterx": [
        "perimeterx",
        "px-captcha"
    ],
    "recaptcha": [
        "g-recaptcha",
        "grecaptcha"
    ],
    "hcaptcha": [
        "h-captcha"
    ]
}
```

### Stealth Capabilities

```javascript
// In Playwright setup:

// 1. navigator.webdriver → undefined
await page.evaluateOnNewDocument(() => {
    delete navigator.__proto__.webdriver;
});

// 2. navigator.plugins → realistic Chrome plugins
await page.evaluateOnNewDocument(() => {
    navigator.plugins = [
        { name: "Chrome PDF Plugin", description: "Portable Document Format" },
        { name: "Chrome PDF Viewer", description: "" },
        { name: "Native Client Executable", description: "" }
    ];
});

// 3. navigator.mimeTypes → realistic MIME types
await page.evaluateOnNewDocument(() => {
    navigator.mimeTypes = [
        { type: "application/pdf", description: "Portable Document Format" },
        { type: "application/x-google-chrome-extension", description: "" }
    ];
});

// 4. WebGL vendor → Intel Iris Xe Graphics
await page.evaluateOnNewDocument(() => {
    const getParameter = WebGLRenderingContext.prototype.getParameter;
    WebGLRenderingContext.prototype.getParameter = function(parameter) {
        if (parameter === 37445) return "Intel Inc.";
        if (parameter === 37446) return "Intel Iris Xe Graphics";
        return getParameter(parameter);
    };
});

// 5. window.chrome object
await page.evaluateOnNewDocument(() => {
    window.chrome = {
        runtime: {}
    };
});
```

### Resource Blocking (Route-Level)

```python
# In Playwright setup:

BLOCKED_RESOURCE_TYPES = ["image", "font", "media", "ping"]

async def on_route(route):
    if route.request.resource_type in BLOCKED_RESOURCE_TYPES:
        await route.abort()
    else:
        await route.continue_()

await page.route("**/*", on_route)
```

**Benefit:** Blocks before network request is made (saves 20-40% bandwidth)

---

## Part 2: Phase 4A Deep Dive — Storage Engine

### Pipeline Chain (Priority Order)

#### 1. MarkdownExtractionPipeline (Priority 110)

**Input:** Raw HTML + extracted content from Phase 1  
**Output:** Clean Markdown, multimodal records

```python
class MarkdownExtractionPipeline:
    def process_item(self, item):
        # Convert HTML to Markdown via Trafilatura
        html = item.get("body_html")
        markdown = trafilatura.extract(html, output_format='markdown')
        
        # Expected: >50% token reduction vs HTML
        # E.g., 50KB HTML → 25KB Markdown
        
        item["markdown"] = markdown
        
        # Extract multimodal (images/videos)
        soup = BeautifulSoup(html, 'html.parser')
        images = []
        for img in soup.find_all('img'):
            images.append({
                "src": img.get('src'),
                "alt": img.get('alt', ''),
                "width": img.get('width'),
                "height": img.get('height')
            })
        
        item["images"] = images
        return item
```

#### 2. NexoraStylePipeline (Priority 150)

**Input:** Raw HTML + CSS  
**Output:** Style analysis (framework, colors, fonts, animations)

```python
class NexoraStylePipeline:
    def process_item(self, item):
        item["style_analysis"] = {
            "css_framework": detect_framework(item["body_html"]),
            "dark_mode": has_dark_mode_css(item["body_html"]),
            "colors": extract_palette(item["body_html"]),
            "fonts": extract_fonts(item["body_html"]),
            "animations": has_animations(item["body_html"]),
            "layout_type": detect_layout(item["body_html"])
        }
        return item
```

#### 3. UnifiedSchemaEnricher (Priority 160)

**Input:** All previous fields  
**Output:** 60+ field unified schema with guaranteed defaults

```python
class UnifiedSchemaEnricher:
    def process_item(self, item):
        # Merge all extracted fields into one dict
        unified = {
            # Basic metadata
            "url": item["url"],
            "title": item.get("title", ""),
            "description": item.get("description", ""),
            "keywords": item.get("keywords", ""),
            
            # Content
            "markdown": item.get("markdown", ""),
            "markdown_preview": item["markdown"][:500] + "..." if item.get("markdown") else "",
            
            # Extracted entities
            "images": item.get("images", []),
            "videos": item.get("videos", []),
            "internal_links": item.get("internal_links", []),
            "external_links": item.get("external_links", []),
            
            # Design
            "style_analysis": item.get("style_analysis", {}),
            
            # Quality scores
            "quality_scores": {
                "readability": estimate_readability(item.get("markdown", "")),
                "completeness": estimate_completeness(item)
            },
            
            # Metadata
            "website_type": detect_website_type(item),  # e-commerce, blog, docs, article, unknown
            "language": detect_language(item.get("markdown", "")),
            
            # Traceability
            "crawl_id": item.get("crawl_id", str(uuid.uuid4())),
            "workspace_id": item.get("workspace_id", "default")
        }
        
        # Merge into item
        item.update(unified)
        return item
```

**Website Type Detection Logic:**

```
Check for patterns:
├─ E-commerce: /cart, /shop, /product, add_to_cart, checkout
├─ Blog: published_date, author, category in schema
├─ Documentation: docs/, api/, /reference, code blocks, versioning
├─ Article: article tag, published_date, word count > 500
└─ Unknown: none match
```

#### 4. MetadataIndexerPipeline (Priority 165)

**Input:** Unified item  
**Output:** SQLite persisted with indexes

```python
class MetadataIndexerPipeline:
    def process_item(self, item):
        store = MetadataStore()
        
        # Insert/update page in SQLite
        store.insert_or_update_page({
            "url": item["url"],
            "title": item["title"],
            "description": item["description"],
            "markdown": item["markdown"],
            "markdown_preview": item["markdown_preview"],
            "crawl_id": item["crawl_id"],
            "workspace_id": item["workspace_id"],
            "website_type": item["website_type"],
            "language": item["language"],
            
            # Phase 4B fields (if present)
            "ai_summary": item.get("ai_summary", ""),
            "ai_tags_json": json.dumps(item.get("ai_tags", [])),
            "ai_embedding": json.dumps(item.get("ai_embedding", [])),
            
            "created_at": datetime.now().isoformat()
        })
        
        # Indexes used:
        # - domain (for --domain filtering)
        # - crawl_id (for --crawl-id filtering)
        # - workspace_id (for tenant isolation)
        # - website_type (for content type filtering)
        # - language (for i18n)
        
        return item
```

#### 5. ParquetExportPipeline (Priority 450)

**Input:** Unified item  
**Output:** Columnar snappy-compressed Parquet

```python
class ParquetExportPipeline:
    def open_spider(self, spider):
        self.records = []
    
    def process_item(self, item):
        # Flatten nested structures for Parquet
        record = {
            "url": item["url"],
            "title": item["title"],
            "markdown_length": len(item.get("markdown", "")),
            "image_count": len(item.get("images", [])),
            "link_count": len(item.get("internal_links", [])) + len(item.get("external_links", [])),
            "website_type": item["website_type"],
            "language": item["language"],
            # ... more fields
        }
        self.records.append(record)
        return item
    
    def close_spider(self, spider):
        # Write Parquet with snappy compression
        df = pd.DataFrame(self.records)
        df.to_parquet(
            f"output/parquet/nexora_{timestamp}.parquet",
            compression="snappy"
        )
```

**Benefits:**
- Column-oriented: Only read needed columns
- Compression: <30% of JSON size
- ML-ready: Direct integration with pandas/dask

---

## Part 3: Phase 4B Deep Dive — AI Enrichment

### Pipeline Priorities (Conditional on NEXORA_ENRICH_MODE)

#### 1. AIEnrichmentPipeline (Priority 250, Eager Only)

```python
class AIEnrichmentPipeline:
    def open_spider(self, spider):
        self.llm_client = LiteLLM(
            provider=settings.NEXORA_AI_PROVIDER,
            model=settings.NEXORA_AI_MODEL,
            api_key=settings.NEXORA_AI_API_KEY
        )
        self.consecutive_failures = 0
        self.breaker_open = False
    
    def process_item(self, item):
        if self.breaker_open:
            # Circuit breaker is OPEN — skip AI
            return item
        
        try:
            markdown = item.get("markdown", "")[:2000]  # Limit to 2K tokens
            
            # 1. Generate summary
            summary = self.llm_client.chat_completion(
                messages=[
                    {"role": "system", "content": "Summarize in 2-3 sentences."},
                    {"role": "user", "content": markdown}
                ],
                max_tokens=150
            )
            item["ai_summary"] = summary
            
            # 2. Generate tags
            tags = self.llm_client.chat_completion(
                messages=[
                    {"role": "system", "content": "Generate 3-5 topic tags."},
                    {"role": "user", "content": markdown}
                ],
                max_tokens=50
            )
            item["ai_tags"] = parse_tags(tags)
            
            # 3. Generate embedding (page-level)
            embedding = embedding_engine.embed_text(markdown)
            item["ai_embedding"] = embedding
            
            # Reset failure counter on success
            self.consecutive_failures = 0
            
        except Exception as e:
            self.consecutive_failures += 1
            logger.warning(f"AI enrichment failed: {e} ({self.consecutive_failures})")
            
            if self.consecutive_failures >= settings.NEXORA_AI_FAILFAST_THRESHOLD:
                logger.error("Circuit breaker OPEN — AI enrichment disabled for this run")
                self.breaker_open = True
                
                # Try fallback provider
                if settings.NEXORA_AI_FALLBACK_PROVIDER:
                    logger.info(f"Routing to fallback provider: {settings.NEXORA_AI_FALLBACK_PROVIDER}")
                    # Attempt same operations with fallback credentials
        
        return item
```

**Circuit Breaker Logic:**
```
Track consecutive failures
    ↓
Threshold reached (default: 3)?
    ├─ YES → Breaker OPEN
    │   ├─ Skip further AI calls
    │   └─ Try fallback provider (if configured)
    └─ NO → Continue
```

#### 2. StructuralChunkingPipeline (Priority 260, Eager Only)

```python
class StructuralChunkingPipeline:
    def process_item(self, item):
        markdown = item.get("markdown", "")
        
        # Split by semantic boundaries (headings, paragraphs)
        chunks = self._chunk_by_structure(
            markdown,
            target_size=settings.NEXORA_CHUNK_SIZE,  # ~512 tokens
            overlap=settings.NEXORA_CHUNK_OVERLAP    # ~128 tokens
        )
        
        # Per-chunk embeddings (replaces page-level)
        chunk_objects = []
        for i, chunk_text in enumerate(chunks):
            chunk_id = str(uuid.uuid4())
            
            # Embed each chunk
            embedding = embedding_engine.embed_text(chunk_text)
            
            chunk_obj = NexoraChunk(
                chunk_id=chunk_id,
                page_url=item["url"],
                chunk_text=chunk_text,
                chunk_index=i,
                embedding=embedding,
                ai_summary=item.get("ai_summary", ""),  # Inherit
                ai_tags=item.get("ai_tags", []),        # Inherit
                source_type="webpage"
            )
            chunk_objects.append(chunk_obj)
        
        item["chunks"] = chunk_objects
        item["chunk_count"] = len(chunk_objects)
        item["chunk_ids"] = [c.chunk_id for c in chunk_objects]
        
        return item
    
    def _chunk_by_structure(self, markdown, target_size, overlap):
        """Split markdown at semantic boundaries (headings, blank lines)"""
        chunks = []
        current_chunk = []
        current_size = 0
        
        lines = markdown.split("\n")
        for line in lines:
            line_tokens = len(line) // 4.5  # Rough estimate
            
            # Heading = boundary
            if line.startswith("#"):
                if current_chunk and current_size > target_size - overlap:
                    chunks.append("\n".join(current_chunk))
                    # Overlap: keep last N tokens
                    current_chunk = current_chunk[-overlap_lines:]
                    current_size = overlap_lines * 4.5
            
            current_chunk.append(line)
            current_size += line_tokens
            
            # Size threshold
            if current_size > target_size:
                chunks.append("\n".join(current_chunk))
                current_chunk = current_chunk[-overlap_lines:]
                current_size = overlap_lines * 4.5
        
        if current_chunk:
            chunks.append("\n".join(current_chunk))
        
        return chunks
```

**Key: Per-Chunk Embeddings**

Why per-chunk?
- Page-level embedding is too coarse (entire page in one vector)
- Chunk-level allows semantic search within pages
- Overlap provides context continuity

#### 3. VectorIndexPipeline (Priority 270, Eager Only)

```python
class VectorIndexPipeline:
    def open_spider(self, spider):
        self.vector_store = build_vector_store()  # Async singleton
    
    def process_item(self, item):
        # Convert NexoraChunk objects to VectorRecords
        vector_records = []
        for chunk in item.get("chunks", []):
            record = VectorRecord(
                id=chunk.chunk_id,
                vector=chunk.embedding,
                metadata={
                    "page_url": chunk.page_url,
                    "chunk_index": chunk.chunk_index,
                    "ai_summary": chunk.ai_summary,
                    "ai_tags": chunk.ai_tags,
                    "source_type": chunk.source_type
                }
            )
            vector_records.append(record)
        
        # Persist to vector store
        if vector_records:
            self.vector_store.add_batch(vector_records)
            item["has_embedding"] = True
        
        return item
```

### UnifiedEmbeddingEngine (Provider-Aware)

```python
class UnifiedEmbeddingEngine:
    def __init__(self, provider, model, api_key=None):
        self.provider = provider
        self.model = model
        self.api_key = api_key
    
    def embed_text(self, text: str) -> list[float]:
        if self.provider == "huggingface":
            return self._embed_huggingface(text)
        elif self.provider == "ollama":
            return self._embed_ollama(text)
        else:
            return self._embed_litellm(text)
    
    def _embed_huggingface(self, text: str) -> list[float]:
        """
        Use legacy /pipeline/feature-extraction endpoint
        (NOT the broken OpenAI-compat /v1/embeddings)
        """
        import requests
        response = requests.post(
            f"{HF_ROUTER_URL}/pipeline/feature-extraction",
            json={"inputs": text},
            headers={"Authorization": f"Bearer {self.api_key}"}
        )
        # Result: list[float] of 384 dimensions
        return response.json()[0]
    
    def _embed_ollama(self, text: str) -> list[float]:
        """Local Ollama embeddings"""
        import requests
        response = requests.post(
            "http://localhost:11434/api/embeddings",
            json={"model": self.model, "prompt": text}
        )
        return response.json()["embedding"]
    
    def _embed_litellm(self, text: str) -> list[float]:
        """OpenAI-compatible providers via LiteLLM"""
        from litellm import aembedding
        response = aembedding(
            model=f"{self.provider}/{self.model}",
            input=text,
            api_key=self.api_key
        )
        return response.data[0]["embedding"]
    
    def embed_batch(self, texts: list[str]) -> list[list[float]]:
        """Batch embedding with rate limit awareness"""
        embeddings = []
        for text in texts:
            try:
                embeddings.append(self.embed_text(text))
            except RateLimitError:
                logger.warning("Rate limited — stopping batch")
                break
        return embeddings
```

**Why HuggingFace Legacy Endpoint?**

The OpenAI-compatible `/v1/embeddings` endpoint on the HF router:
- ❌ **Does NOT** support sentence-transformers models
- ✅ The legacy `/pipeline/feature-extraction` endpoint does
- ✅ Returns 384-dim embeddings (all-MiniLM-L6-v2)

---

## Part 4: Phase 4C Deep Dive — API Layer

### FastAPI App Structure

```
api/
├── __init__.py              # FastAPI app definition
├── __main__.py              # python -m nexora_crawler.api
├── auth.py                  # JWT + API key validation
├── database/
│   ├── __init__.py
│   └── connection.py        # Async DB (aiosqlite/asyncpg)
├── routes/
│   ├── __init__.py
│   ├── search.py            # /v1/search/* endpoints
│   ├── webhooks.py          # /v1/webhooks/* CRUD
│   ├── jobs.py              # /v1/jobs/* submission + status
│   ├── gdpr.py              # /v1/gdpr/erase
│   ├── extract.py           # /v1/extract/schema
│   └── health.py            # /health endpoints
├── jobs/
│   ├── __init__.py
│   └── registry.py          # Job type registry
└── tasks/
    ├── __init__.py
    └── dispatcher.py        # In-process job dispatch
```

### Authentication Flow

```python
# File: api/auth.py

async def get_workspace_id(request: Request) -> str:
    """
    Validate request auth, return workspace_id.
    Used as Depends() on all protected routes.
    """
    
    # Step 1: Try JWT (Authorization header)
    auth_header = request.headers.get("Authorization", "")
    if auth_header.startswith("Bearer "):
        token = auth_header[7:]
        try:
            payload = jwt.decode(token, settings.JWT_SECRET, algorithms=["HS256"])
            workspace_id = payload.get("workspace_id")
            if workspace_id:
                return workspace_id
        except jwt.ExpiredSignatureError:
            raise HTTPException(status_code=401, detail="Token expired")
        except jwt.InvalidTokenError:
            raise HTTPException(status_code=401, detail="Invalid token")
    
    # Step 2: Try API Key (X-Api-Key header)
    api_key = request.headers.get("X-Api-Key")
    if api_key:
        # Format: "{key_id}.{raw_key}"
        key_id = api_key.split(".")[0] if "." in api_key else api_key[:8]
        raw_key = api_key.split(".", 1)[1] if "." in api_key else api_key
        
        store = MetadataStore()
        
        # Step 2a: Get stored hash (already active-only)
        stored_hash = store.get_api_key_hash(key_id)
        if not stored_hash:
            raise HTTPException(status_code=401, detail="Invalid API key")
        
        # Step 2b: Compare hashes
        expected_hash = hashlib.sha256(raw_key.encode()).hexdigest()
        if expected_hash != stored_hash:
            raise HTTPException(status_code=401, detail="Invalid API key")
        
        # Step 2c: Retrieve metadata (defense-in-depth active check)
        key_row = store.get_api_key_by_id(key_id, active_only=True)
        if not key_row:
            raise HTTPException(status_code=401, detail="Invalid API key")
        
        # Step 2d: Return workspace_id
        return key_row["workspace_id"]
    
    # Step 3: Try dev bypass (X-Workspace-Id header)
    if settings.NEXORA_AUTH_BYPASS_ENABLED:
        workspace_id = request.headers.get("X-Workspace-Id")
        if workspace_id:
            logger.warning(f"Dev bypass used for workspace: {workspace_id}")
            return workspace_id
    
    # Step 4: No auth
    raise HTTPException(status_code=401, detail="Unauthorized")
```

### Workspace Isolation Pattern

Every protected route uses:
```python
@app.post("/v1/webhooks")
async def create_webhook(
    webhook_in: WebhookCreateIn,
    workspace_id: str = Depends(get_workspace_id)
):
    # workspace_id is automatically extracted from auth
    # Routes can ONLY see/modify resources in this workspace
    
    # Insert with workspace_id constraint
    store = MetadataStore()
    store.insert_webhook({
        "url": webhook_in.url,
        "workspace_id": workspace_id,  # <-- ENFORCED
        "event_types": webhook_in.event_types
    })
```

### Async DB Connection Layer

```python
# File: api/database/connection.py

class AsyncDB:
    def __init__(self, db_path: str):
        self.db_path = db_path
        self.connection = None
        self.is_asyncpg = self.db_path.startswith("postgresql://")
    
    async def connect(self):
        if self.is_asyncpg:
            import asyncpg
            self.connection = await asyncpg.connect(self.db_path)
        else:
            import aiosqlite
            self.connection = await aiosqlite.connect(self.db_path)
    
    async def execute(self, query: str, params: tuple = ()):
        """Execute query, handle dialect differences"""
        # Convert placeholders: ? (SQLite) vs $n (asyncpg)
        if self.is_asyncpg:
            query = self._convert_to_asyncpg(query)
        
        result = await self.connection.execute(query, params)
        return result
    
    async def commit(self):
        """CRITICAL: All mutations must be followed by commit()"""
        if self.connection:
            if self.is_asyncpg:
                await self.connection.execute("COMMIT")
            else:
                await self.connection.commit()
    
    def _convert_to_asyncpg(self, query: str) -> str:
        """Convert ? placeholders to $1, $2, etc."""
        i = 1
        while "?" in query:
            query = query.replace("?", f"${i}", 1)
            i += 1
        return query
```

### Jobs Registry & Dispatcher

```python
# File: jobs/registry.py

REGISTERED_JOBS = {
    "crawl": {
        "description": "Start web crawl",
        "handler_cls": CrawlJobHandler,  # Implements handle(job_id, params)
        "required_params": ["urls", "strategy"]
    },
    "schema_extract": {
        "description": "Extract structured data from URL",
        "handler_cls": SchemaExtractJobHandler,
        "required_params": ["url", "schema_id"]
    },
    "index_search": {
        "description": "Semantic search in vector index",
        "handler_cls": IndexSearchJobHandler,
        "required_params": ["query", "top_k"]
    },
    "index_add": {
        "description": "Add URLs to vector index",
        "handler_cls": IndexAddJobHandler,
        "required_params": ["urls"]
    },
    "export": {
        "description": "Export crawl results",
        "handler_cls": ExportJobHandler,
        "required_params": ["format", "crawl_id"]
    }
}

# File: tasks/dispatcher.py

class SimpleJobDispatcher:
    def __init__(self):
        self._live_tasks = {}  # Track async tasks to prevent GC
    
    async def dispatch(self, job_id: str, job_type: str, params: dict):
        """Dispatch job asynchronously"""
        job_def = REGISTERED_JOBS[job_type]
        handler_cls = job_def["handler_cls"]
        
        if handler_cls is None:
            # Stub job — return 501
            return {"status": "not_implemented", "job_id": job_id}
        
        # Create async task
        task = asyncio.create_task(
            handler_cls().handle(job_id, params)
        )
        
        # Track to prevent GC
        self._live_tasks[job_id] = task
        
        # Clean up when done
        task.add_done_callback(lambda t: self._live_tasks.pop(job_id, None))
        
        return {"status": "queued", "job_id": job_id}
```

### Phase 4C Database Tables

```sql
-- Webhooks
CREATE TABLE webhooks (
    id TEXT PRIMARY KEY,
    workspace_id TEXT NOT NULL,
    url TEXT NOT NULL,
    event_types JSON,
    secret TEXT,
    is_active BOOLEAN DEFAULT 1,
    created_at TEXT,
    FOREIGN KEY (workspace_id) REFERENCES workspaces(id)
);

-- Webhook Delivery Tracking
CREATE TABLE webhook_deliveries (
    id TEXT PRIMARY KEY,
    webhook_id TEXT NOT NULL,
    event TEXT,
    status TEXT,
    response_code INTEGER,
    response_body TEXT,
    timestamp TEXT,
    FOREIGN KEY (webhook_id) REFERENCES webhooks(id)
);

-- API Keys
CREATE TABLE api_keys (
    id TEXT PRIMARY KEY,
    workspace_id TEXT NOT NULL,
    key_hash TEXT NOT NULL,
    name TEXT,
    is_active BOOLEAN DEFAULT 1,
    created_at TEXT,
    FOREIGN KEY (workspace_id) REFERENCES workspaces(id)
);

-- Usage Records (for rate limiting)
CREATE TABLE usage_records (
    id TEXT PRIMARY KEY,
    workspace_id TEXT NOT NULL,
    endpoint TEXT,
    timestamp TEXT,
    request_id TEXT,
    FOREIGN KEY (workspace_id) REFERENCES workspaces(id)
);

-- Audit Logs (compliance)
CREATE TABLE audit_logs (
    id TEXT PRIMARY KEY,
    workspace_id TEXT NOT NULL,
    action TEXT,
    resource TEXT,
    changes_json JSON,
    timestamp TEXT,
    FOREIGN KEY (workspace_id) REFERENCES workspaces(id)
);

-- Extraction Schemas
CREATE TABLE extraction_schemas (
    id TEXT PRIMARY KEY,
    workspace_id TEXT NOT NULL,
    schema_json JSON,
    created_at TEXT,
    FOREIGN KEY (workspace_id) REFERENCES workspaces(id)
);
```

---

## Part 5: Key Configuration Variables

### Enrichment Control

| Variable | Default | Effect |
|----------|---------|--------|
| `NEXORA_ENRICH_MODE` | `on_demand` | `on_demand` = fast crawl + offline enrich; `eager` = inline AI |
| `NEXORA_AI_ENABLED` | `true` | Disable AI entirely |
| `NEXORA_AI_FAILFAST_THRESHOLD` | `3` | Consecutive failures before breaker opens (0 = disabled) |

### Provider Configuration

| Variable | Default | Effect |
|----------|---------|--------|
| `NEXORA_AI_PROVIDER` | `huggingface` | LLM provider: `huggingface`, `ollama`, `openai`, `anthropic` |
| `NEXORA_AI_MODEL` | `Qwen/Qwen2.5-7B-Instruct` | LLM model name |
| `NEXORA_AI_API_KEY` | (empty) | API key for provider |
| `NEXORA_AI_BASE_URL` | (provider-specific) | Custom base URL for provider |

### Fallback Provider

| Variable | Default | Effect |
|----------|---------|--------|
| `NEXORA_AI_FALLBACK_PROVIDER` | (empty) | Secondary provider when primary breaker opens |
| `NEXORA_AI_FALLBACK_MODEL` | (empty) | Secondary model name |
| `NEXORA_AI_FALLBACK_BASE_URL` | (empty) | Secondary provider base URL |
| `NEXORA_AI_FALLBACK_API_KEY` | (empty) | Secondary provider API key |

### Embedding Configuration

| Variable | Default | Effect |
|----------|---------|--------|
| `NEXORA_AI_EMBEDDING_MODEL` | `sentence-transformers/all-MiniLM-L6-v2` | Embedding model (HF format) |
| `NEXORA_EMBEDDING_DIM` | `384` | Vector dimension (MUST match model) |

### Vector Store Configuration

| Variable | Default | Effect |
|----------|---------|--------|
| `NEXORA_VECTOR_BACKEND` | `chroma` | Backend: `chroma` (dev) / `pgvector` (prod) |
| `NEXORA_CHROMA_PATH` | `./data/chroma` | Chroma storage directory |
| `NEXORA_DATABASE_URL` | (empty) | Postgres URL for pgvector (Supabase format) |

### Chunking Configuration

| Variable | Default | Effect |
|----------|---------|--------|
| `NEXORA_CHUNK_SIZE` | `512` | Target tokens per chunk |
| `NEXORA_CHUNK_OVERLAP` | `128` | Overlap tokens between chunks |

### Security Configuration

| Variable | Default | Effect |
|----------|---------|--------|
| `NEXORA_JWT_SECRET_KEY` | `change-me-in-production` | JWT signing key (**MUST CHANGE**) |
| `NEXORA_AUTH_BYPASS_ENABLED` | `false` | Enable dev X-Workspace-Id bypass |
| `NEXORA_CORS_ORIGINS` | `["http://localhost:3000"]` | Allowed CORS origins (JSON list) |

### Database Configuration

| Variable | Default | Effect |
|----------|---------|--------|
| `NEXORA_METADATA_DB` | `./data/nexora_metadata.db` | SQLite path (or postgres:// for prod) |

---

## Part 6: Common Workflows

### Workflow 1: Single-Page Static Extraction

```bash
cd "Nexora application/Crawler"

# Extract static HTML page
scrapy crawl nexora -a urls="https://example.com"
# → Phase 3 detects: static site
# → Runs Phase 1-4A pipelines (no Playwright)
# → Outputs: JSON, CSV, Markdown, Parquet, SQLite
```

### Workflow 2: Multi-Page Crawl with On-Demand Enrichment

```bash
cd "Nexora application/Crawler"

# Fast crawl (no AI)
export NEXORA_ENRICH_MODE=on_demand
scrapy crawl nexora -a urls="https://example.com" -a strategy="whole-website" -a max_pages=100

# Wait for crawl to finish...
# Then enrich offline
python enrich.py --limit 50  # Enrich first 50 unenriched pages
```

### Workflow 3: Real-Time Enrichment (Eager Mode)

```bash
cd "Nexora application/Crawler"

# Inline AI enrichment during crawl
export NEXORA_ENRICH_MODE=eager
scrapy crawl nexora -a urls="https://example.com" -a strategy="single-page"
# → All 11 pipelines run
# → Slower but embeddings ready immediately
```

### Workflow 4: Switch to Ollama (Local LLM)

No code changes — just environment variables:

```bash
export NEXORA_ENRICH_MODE=eager
export NEXORA_AI_PROVIDER=ollama
export NEXORA_AI_MODEL=neural-chat
export NEXORA_AI_BASE_URL=http://localhost:11434
export NEXORA_AI_EMBEDDING_MODEL=nomic-embed-text
export NEXORA_EMBEDDING_DIM=384

# Start Ollama server first
ollama serve

# In another terminal:
cd "Nexora application/Crawler"
scrapy crawl nexora -a urls="https://example.com"
# → AI routes to local Ollama
```

### Workflow 5: Vector Search

```bash
# Start API server
python -m nexora_crawler.api --server

# In another terminal:
curl -X POST http://localhost:8000/v1/search/semantic \
  -H "Content-Type: application/json" \
  -H "X-Workspace-Id: my-workspace" \
  -d '{
    "query": "best practices for web scraping",
    "top_k": 5
  }'
```

---

## Part 7: Troubleshooting

### Issue: enrich.py NameError

```
NameError: name '_build_crawler' is not defined
```

**Cause:** enrich.py helpers not implemented (BLOCKING BUG)

**Fix:** See recommendations section — helpers need implementation

### Issue: Vector Store HTTP 500

```
HTTPException(status_code=500, detail="Vector store not initialized")
```

**Cause:** Async singleton not initialized

**Fix:** Use `await get_vector_store()` in routes (already done in Phase 4C)

### Issue: Workspace Isolation Bypass

```
Unauthenticated request with X-Workspace-Id header succeeds
```

**Cause:** NEXORA_AUTH_BYPASS_ENABLED=true (default before v4.6.0)

**Fix:** Set `NEXORA_AUTH_BYPASS_ENABLED=false` in .env

### Issue: Chunk Size Overshoots

```
Expected ~512 tokens/chunk, getting ~680
```

**Cause:** Overlap mechanism + token estimation variance

**Status:** Acceptable; tracked as nice-to-have for future tuning

---

**End of Technical Reference**

*For implementation details, see phase-specific pipeline code.*  
*For API routes, see api/routes/*.py files.*  
*For database schema, see storage/local_sqlite.py.*

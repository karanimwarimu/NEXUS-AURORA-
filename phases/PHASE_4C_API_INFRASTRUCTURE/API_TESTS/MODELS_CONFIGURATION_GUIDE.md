# NEXUS AURORA v4.5.0 — Models Configuration Guide

**Date:** 2026-08-18  
**Purpose:** Complete reference for all models used across all phases  
**Scope:** Framework detection, embedding models, LLM models, vector backends

---

## Quick Reference

| Category | Model/Component | Purpose | Status |
|----------|-----------------|---------|--------|
| **Framework Detection** | 7 patterns (regex) | Detect Next.js, Nuxt, Gatsby, React, Vue, Angular, Svelte | ✅ Deployed |
| **Anti-Bot Detection** | 5 vendors (regex) | Detect Cloudflare, DataDome, PerimeterX, reCAPTCHA, hCaptcha | ✅ Deployed |
| **Embedding Model** | sentence-transformers/all-MiniLM-L6-v2 | 384-dim sentence embeddings (HF router) | ✅ Deployed |
| **LLM Model** | Qwen/Qwen2.5-7B-Instruct | Summary + tag generation | ✅ Deployed |
| **Vector Backend** | ChromaDB (local) or pgvector (prod) | Store + retrieve vectors | ✅ Deployed |
| **Language Detection** | FastText (lid.176.ftz) | Detect page language (optional) | ✅ Available |

---

## Phase 3: Framework & Anti-Bot Detection

### Framework Detection (7 Frameworks)

**Location:** `nexora_crawler/middlewares/dynamic_detection.py`

All frameworks use regex patterns (no ML model):

| Framework | Key Patterns | Example Sites |
|-----------|--------------|----------------|
| **Next.js** | `__NEXT_DATA__`, `/_next/`, `__NEXT_F__` | react.dev, vercel.com, supabase.com |
| **Nuxt** | `data-v-xxxxxxxx`, `__VUE__`, generator meta | vuejs.org, nuxt.com, gitlab.com |
| **Gatsby** | `gatsby-focus-wrapper`, generator meta | Various Gatsby sites |
| **React** | `data-reactroot`, `__reactFiber`, bundle paths | Generic React SPAs |
| **Vue** | `__VUE__`, `vue-router`, bundle paths | behance.net, laravel.com |
| **Angular** | `ng-version=`, `__ngContext__`, bundle paths | angular.io, rxjs.dev |
| **Svelte** | `svelte-xxxxxx`, `__svelte`, bundle paths | svelte.dev, kit.svelte.dev |

**Detection Accuracy:** ~85-90% (static patterns, no false positives from this phase alone)

### Anti-Bot Detection (5 Vendors)

**Location:** `nexora_crawler/middlewares/dynamic_detection.py`

All anti-bot detection uses regex patterns (no ML):

| Vendor | Indicators | Stealth Response |
|--------|------------|------------------|
| **Cloudflare** | `cf-browser-verification`, `turnstile`, `/cdn-cgi/challenge` | navigator.webdriver → undefined |
| **DataDome** | `datadome`, `captcha-delivery` | navigator.plugins → Chrome plugin list |
| **PerimeterX** | `perimeterx`, `px-captcha` | navigator.mimeTypes → MIME types |
| **reCAPTCHA** | `recaptcha`, `g.recaptcha` | WebGL vendor → Intel Iris Xe |
| **hCaptcha** | `hcaptcha`, `h.captcha` | permissions.query → safe API handling |

**Stealth Evasion:** ✅ Implemented (4 spoofing mechanisms)

---

## Phase 4B: AI Models

### Embedding Model

**Model:** `sentence-transformers/all-MiniLM-L6-v2`  
**Dimensions:** 384  
**Provider:** HuggingFace router (legacy `/pipeline/feature-extraction` endpoint)  
**Use Case:** Convert text chunks to vectors for semantic search  
**Performance:** Fast (~50ms per chunk), free, serverless

**Why This Model?**
- ✅ Small (22M params) but high quality
- ✅ Widely adopted in RAG systems
- ✅ Fast inference (~50ms per 512-token chunk)
- ✅ Free via HF router
- ✅ No GPU required (CPU-inference friendly)

**Configuration:**
```python
NEXORA_AI_EMBEDDING_MODEL = "sentence-transformers/all-MiniLM-L6-v2"
NEXORA_EMBEDDING_DIM = 384
```

**How to Switch Models:**

```python
# Option 1: Stay with HuggingFace (same router)
NEXORA_AI_EMBEDDING_MODEL = "sentence-transformers/all-mpnet-base-v2"  # 768-dim
NEXORA_EMBEDDING_DIM = 768

# Option 2: Use Ollama locally
NEXORA_AI_PROVIDER = "ollama"
NEXORA_AI_EMBEDDING_MODEL = "nomic-embed-text"  # 768-dim, local
NEXORA_EMBEDDING_DIM = 768
NEXORA_AI_BASE_URL = "http://localhost:11434"

# Option 3: Use OpenAI
NEXORA_AI_PROVIDER = "openai"
NEXORA_AI_EMBEDDING_MODEL = "text-embedding-3-small"  # 1536-dim
NEXORA_EMBEDDING_DIM = 1536
NEXORA_AI_BASE_URL = "https://api.openai.com/v1"
NEXORA_AI_API_KEY = "<your-key>"
```

**⚠️ Important:** When changing embedding model dimension, delete `data/chroma` and rebuild the index (HNSW index bakes in the dimension).

### LLM Model (Summary & Tags)

**Model:** `Qwen/Qwen2.5-7B-Instruct`  
**Provider:** HuggingFace router  
**Use Case:** Generate 2-3 sentence summary + 3-5 topic tags  
**JSON-Friendly:** ✅ Yes (built for structured output)

**Why This Model?**
- ✅ Instruct-tuned (good at following instructions)
- ✅ JSON-friendly (strong structured output)
- ✅ Fast inference via HF router
- ✅ Free via community access on HF
- ✅ Competitive quality vs paid APIs

**Configuration:**
```python
NEXORA_AI_PROVIDER = "huggingface"
NEXORA_AI_MODEL = "Qwen/Qwen2.5-7B-Instruct"
NEXORA_AI_BASE_URL = "https://router.huggingface.co/v1"
NEXORA_AI_API_KEY = "<your-hf-token>"  # or HF_TOKEN env var
NEXORA_AI_TIMEOUT = 60
NEXORA_AI_MAX_CONCURRENT = 2
```

**How to Switch Models:**

```python
# Option 1: Stay with HuggingFace (different model)
NEXORA_AI_MODEL = "meta-llama/Llama-3.1-8B-Instruct"  # Alternative Instruct model

# Option 2: Use Ollama locally
NEXORA_AI_PROVIDER = "ollama"
NEXORA_AI_MODEL = "llama2:13b-instruct"
NEXORA_AI_BASE_URL = "http://localhost:11434"
# No API key needed for local Ollama

# Option 3: Use OpenAI
NEXORA_AI_PROVIDER = "openai"
NEXORA_AI_MODEL = "gpt-4-turbo"
NEXORA_AI_BASE_URL = "https://api.openai.com/v1"
NEXORA_AI_API_KEY = "<your-openai-key>"

# Option 4: Use Anthropic
NEXORA_AI_PROVIDER = "anthropic"
NEXORA_AI_MODEL = "claude-3-sonnet-20240229"
NEXORA_AI_BASE_URL = ""  # Not used
NEXORA_AI_API_KEY = "<your-anthropic-key>"
```

**Circuit Breaker Configuration:**
```python
# After 3 consecutive failures, stop trying AI calls for this run
NEXORA_AI_FAILFAST_THRESHOLD = 3

# Optional: fallback provider when primary quota exhausted
NEXORA_AI_FALLBACK_PROVIDER = "ollama"
NEXORA_AI_FALLBACK_MODEL = "llama2:13b-instruct"
NEXORA_AI_FALLBACK_BASE_URL = "http://localhost:11434"
NEXORA_AI_FALLBACK_API_KEY = ""
```

---

## Phase 4B: Chunking Configuration

### Chunking Strategy (No ML Model)

**Algorithm:** Structural chunking (semantic boundaries, not token-count fixed)

**Configuration:**
```python
NEXORA_CHUNK_SIZE = 512      # Target tokens per chunk
NEXORA_CHUNK_OVERLAP = 128   # Overlap tokens between chunks
```

**How It Works:**
1. Split Markdown at heading/paragraph boundaries (structural)
2. Aim for ~512 tokens per chunk (actual: 400-680 due to overlap)
3. 128-token overlap between adjacent chunks
4. Each chunk inherits parent page's summary + tags
5. Each chunk gets its own embedding

**Actual Behavior:**
- Average chunk: ~680 tokens (slightly above target due to overlap mechanism)
- Range: 400-800 tokens
- Status: Acceptable (tracked as nice-to-have improvement)

---

## Phase 4B: Vector Store Backend

### Primary Backend: ChromaDB (Local)

**Configuration:**
```python
NEXORA_VECTOR_BACKEND = "chroma"
NEXORA_VECTOR_INDEX_ENABLED = True
NEXORA_CHROMA_PATH = "data/chroma"  # Local SQLite + HNSW index
```

**How to Use:**
- Default for development
- No external service required
- Data persisted to `data/chroma/chroma.sqlite3`
- HNSW index for fast semantic search

### Production Backend: pgvector (Supabase/PostgreSQL)

**Configuration:**
```python
NEXORA_VECTOR_BACKEND = "pgvector"
NEXORA_DATABASE_URL = "postgresql://user:pass@host:5432/nexora"
```

**How to Use:**
- For production deployments
- Requires Postgres with pgvector extension
- Use Supabase direct connection (port 5432, not 6543 pooler)
- Same API interface as Chroma (abstracted)

### Switching Backends:

```bash
# Use ChromaDB (local, default)
export NEXORA_VECTOR_BACKEND=chroma

# Use pgvector (production)
export NEXORA_VECTOR_BACKEND=pgvector
export NEXORA_DATABASE_URL=postgresql://...

# Use Qdrant (alternative, if implemented)
export NEXORA_VECTOR_BACKEND=qdrant
export NEXORA_QDRANT_URL=http://localhost:6333
```

---

## Phase 3: Language Detection (Optional)

### FastText Language Model

**Model:** `lid.176.ftz` (FastText)  
**Location:** `Nexora application/Models/lid.176.ftz` (optional)  
**Use Case:** Detect page language (ISO-639-1 code)  
**Languages Supported:** 176 languages

**Configuration:**
```python
# Language detection is optional — if model not found, detection is skipped
# gracefully. No required setting in settings.py.
```

**How to Enable:**
1. Download `lid.176.ftz` from Facebook Research
2. Place at `Nexora application/Models/lid.176.ftz`
3. Restart crawler — language detection auto-enabled

**Usage:**
```python
from fasttext import load_model

model = load_model("path/to/lid.176.ftz")
predictions = model.predict("This is English text")
# Output: (['__label__en'], [0.98])
```

---

## How Models Are Used (Data Flow)

### During Crawl (On-Demand Mode, Default)

```
URL → Middleware (Framework detection via regex patterns)
    → Extraction (structured HTML parsing)
    → Markdown (Trafilatura HTML→text, no ML)
    → Schema (defaults, no ML)
    → Storage (SQLite, no ML)
    → Export (JSON/CSV/Parquet, no ML)
```

**No AI models called.** Fast, free, no timeouts.

### During On-Demand Enrichment (enrich.py)

```
Saved Page (Markdown) → AIEnrichmentPipeline
                    ├─ LLM (Qwen2.5) → Summary + tags
                    └─ Embedding (MiniLM) → 384-dim vector
                    
                    → StructuralChunkingPipeline
                    └─ Split Markdown → Chunks
                    
                    → VectorIndexPipeline
                    └─ Embedding (MiniLM) → Chunk vectors
                    
                    → Vector Store (Chroma/pgvector)
```

**All AI models called.** Slower, optional, can timeout (circuit breaker handles).

### During Eager Enrichment (NEXORA_ENRICH_MODE=eager)

Same as on-demand, but **during the crawl** (inline with extraction).

---

## Configuration Reference

### For Development

```bash
# .env or environment variables
NEXORA_ENRICH_MODE=on_demand              # Default: fast crawls, no AI
NEXORA_AI_ENABLED=true
NEXORA_AI_PROVIDER=huggingface
NEXORA_AI_MODEL=Qwen/Qwen2.5-7B-Instruct
NEXORA_AI_EMBEDDING_MODEL=sentence-transformers/all-MiniLM-L6-v2
NEXORA_EMBEDDING_DIM=384
HF_TOKEN=<your-hf-token>                  # Or NEXORA_AI_API_KEY
NEXORA_VECTOR_BACKEND=chroma
NEXORA_CHUNK_SIZE=512
NEXORA_CHUNK_OVERLAP=128
```

### For Production (Supabase + OpenAI)

```bash
NEXORA_ENRICH_MODE=on_demand              # Crawl fast, enrich offline
NEXORA_AI_ENABLED=true
NEXORA_AI_PROVIDER=openai
NEXORA_AI_MODEL=gpt-4-turbo
NEXORA_AI_EMBEDDING_MODEL=text-embedding-3-small
NEXORA_EMBEDDING_DIM=1536
NEXORA_AI_API_KEY=<your-openai-key>
NEXORA_VECTOR_BACKEND=pgvector
NEXORA_DATABASE_URL=postgresql://user:pass@db.supabase.co:5432/postgres
NEXORA_CHUNK_SIZE=512
NEXORA_CHUNK_OVERLAP=128
```

### For Local-Only (Ollama, No API Keys)

```bash
NEXORA_ENRICH_MODE=eager                  # Inline enrichment
NEXORA_AI_ENABLED=true
NEXORA_AI_PROVIDER=ollama
NEXORA_AI_MODEL=llama2:13b-instruct
NEXORA_AI_EMBEDDING_MODEL=nomic-embed-text
NEXORA_EMBEDDING_DIM=768
NEXORA_AI_BASE_URL=http://localhost:11434
NEXORA_VECTOR_BACKEND=chroma
NEXORA_CHUNK_SIZE=512
NEXORA_CHUNK_OVERLAP=128
```

---

## Model Performance & Costs

### HuggingFace Router (Free Community Access)

| Model | Speed | Quality | Cost | Notes |
|-------|-------|---------|------|-------|
| **Qwen2.5-7B (LLM)** | ~3s/page | Good | Free | JSON-friendly, instruct-tuned |
| **all-MiniLM-L6-v2 (Embedding)** | ~50ms/chunk | Good | Free | Fast, small footprint, 384-dim |

### OpenAI (Paid)

| Model | Speed | Quality | Cost | Notes |
|-------|-------|---------|------|-------|
| **gpt-4-turbo (LLM)** | ~5s/page | Excellent | $0.01/page | Best quality, structured output |
| **text-embedding-3-small** | ~100ms/chunk | Good | $0.02/1M tokens | Fast, 1536-dim |

### Ollama (Local, Free)

| Model | Speed | Quality | Cost | Notes |
|-------|-------|---------|------|-------|
| **llama2:13b (LLM)** | ~10s/page | Decent | Free | Local, no API keys |
| **nomic-embed-text** | ~200ms/chunk | Good | Free | Local, 768-dim |

---

## Troubleshooting

### Issue: "ModuleNotFoundError: No module named 'sentence_transformers'"

**Solution:** Install extras
```bash
pip install sentence-transformers transformers torch
```

### Issue: "HF_TOKEN not set or invalid"

**Solution:** Set token
```bash
export HF_TOKEN=hf_xxxxxxxxxxxxx
# Or in .env
echo "HF_TOKEN=hf_xxxxxxxxxxxxx" >> Crawler/nexora_crawler/.env
```

### Issue: "Chunk embeddings timeout / LLM too slow"

**Solution:** Use faster fallback
```bash
NEXORA_AI_FAILFAST_THRESHOLD=3
NEXORA_AI_FALLBACK_PROVIDER=ollama
NEXORA_AI_FALLBACK_MODEL=nomic-embed-text:latest
NEXORA_AI_FALLBACK_BASE_URL=http://localhost:11434
```

### Issue: "Vector dimension mismatch (expected 384, got 1536)"

**Solution:** Rebuild vector store
```bash
rm -rf data/chroma
python enrich.py  # Rebuilds with new dimension
```

---

## Summary

**Models Used in NEXUS AURORA v4.5.0:**

✅ **Framework Detection:** 7 regex patterns (no ML)  
✅ **Anti-Bot Detection:** 5 regex patterns (no ML)  
✅ **Embeddings:** sentence-transformers/all-MiniLM-L6-v2 (384-dim)  
✅ **LLM:** Qwen/Qwen2.5-7B-Instruct (summary + tags)  
✅ **Vector Storage:** ChromaDB (local) or pgvector (prod)  
✅ **Language Detection:** FastText lid.176.ftz (optional)  
✅ **Chunking:** Structural (no ML, heading-based boundaries)  

**All configurable:** Change provider, model, backend via settings only (no code changes).


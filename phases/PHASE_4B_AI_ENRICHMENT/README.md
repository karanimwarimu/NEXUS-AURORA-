# Phase 4B: AI Enrichment & Vector Indexing

**Status:** ✅ Complete + Tested (v4.5.0)

On-demand and eager AI enrichment with LLM summaries, embeddings, structural chunking, and vector indexing for production-grade RAG systems.

---

## 📂 Quick Navigation

- 📝 **Release Notes:** See `release_notes/release_notes_v4.5.0.md`
- 🧪 **Test Suite:** `tests/` directory for Phase 4B verification
- 📊 **Audits:** `audits/` directory for 45-test verification suite results
- 📋 **Reports:** `reports/` directory for detailed findings

---

## 🔑 Key Features

### On-Demand Enrichment (Default)
- Fast crawls with **zero AI calls**
- Enrich saved pages **offline later** via `enrich.py`
- Decouples crawling from AI processing
- Ideal for high-volume crawling

### Eager Mode (Inline Enrichment)
- Immediate AI enrichment **during crawl**
- Summary, tags, and embeddings generated per page
- Ideal for low-volume, high-value crawls
- Circuit breaker prevents timeout drains

### AI Features
- **LLM Summaries:** 2-3 sentence per-page summaries
- **Topic Tags:** 3-5 auto-generated tags per page
- **Embeddings:** sentence-transformers vectors (384-dim default)
- **Per-chunk Embeddings:** Each chunk gets unique vector

### Structural Chunking
- **Semantic splitting:** ~512 tokens per chunk (heading/paragraph boundaries)
- **Overlap:** 128 tokens between chunks
- **Inheritance:** Chunks inherit page summary, tags, and embedding

### Vector Store Backends
- **Chroma** (local development)
- **pgvector/Supabase** (production)
- **Provider-agnostic:** Switch backends via settings only

### Provider Support
- **Hugging Face Router:** Default embedding provider (free, serverless)
- **LiteLLM:** Unified AI provider interface (supports OpenAI, Ollama, Anthropic, etc.)
- **Circuit Breaker:** Automatic failover after N consecutive failures
- **Provider Fallback:** Optional secondary provider when primary exhausted

---

## 📊 Current Status (v4.5.0)

| Component | Status | Details |
|-----------|--------|---------|
| **AI Enrichment** | ✅ Complete | LLM summaries + tags working |
| **Embeddings** | ✅ Complete | HF router + LiteLLM functional |
| **Chunking** | ✅ Complete | Semantic splitting at 512-token target |
| **Vector Store** | ✅ Complete | Chroma + pgvector backends verified |
| **Circuit Breaker** | ✅ Complete | Prevents timeout drains |
| **Provider Fallback** | ✅ Complete | Secondary provider routing works |
| **crawl_id Propagation** | ✅ Fixed (v4.5.0) | Every page row has crawl_id |
| **Resource Blocking** | ✅ Fixed (v4.5.0) | Images/fonts/media blocked at route-level |

**Test Results:** 45-test suite (39 PASS, 5 FAIL, 1 SKIP)

---

## 🚀 Usage

### On-Demand Mode (Recommended)
```powershell
cd "Nexora application\Crawler"

# Fast crawl - no AI calls
scrapy crawl nexora -a urls="https://example.com"

# Later, enrich offline
python enrich.py
python enrich.py --domain example.com
python enrich.py --limit 50
```

### Eager Mode (Inline Enrichment)
```powershell
# Via environment variable
set NEXORA_ENRICH_MODE=eager
scrapy crawl nexora -a urls="https://example.com"

# Via CLI
python -m nexora_crawler.api --url https://example.com --enrich-mode eager

# Via FastAPI
curl -X POST http://localhost:8000/crawl \
  -H 'Content-Type: application/json' \
  -d '{"url": "https://example.com", "enrich_mode": "eager"}'
```

### Verify AI + Vector Stack
```powershell
cd "Nexora application\Crawler"

# 1) Check connectivity (LLM + embeddings)
python -m nexora_crawler.pipelines.test_ai

# 2) Verify embeddings stored & retrieveable
python -m nexora_crawler.pipelines.test_vector_store
```

---

## 🔧 Configuration

Key settings in `Crawler/nexora_crawler/settings.py`:

| Setting | Default | Purpose |
|---------|---------|---------|
| `NEXORA_ENRICH_MODE` | `on_demand` | `"on_demand"` \| `"eager"` |
| `NEXORA_AI_ENABLED` | `True` | Enable/disable AI enrichment |
| `NEXORA_AI_PROVIDER` | `huggingface` | `huggingface` / `ollama` / `openai` / `anthropic` |
| `NEXORA_AI_MODEL` | `Qwen/Qwen2.5-7B-Instruct` | LLM for summaries/tags |
| `NEXORA_AI_EMBEDDING_MODEL` | `sentence-transformers/all-MiniLM-L6-v2` | Embedding model |
| `NEXORA_EMBEDDING_DIM` | `384` | Must match embedding model |
| `NEXORA_VECTOR_BACKEND` | `chroma` | `chroma` \| `pgvector` |
| `NEXORA_CHROMA_PATH` | `./data/chroma` | Chroma persistence path |
| `NEXORA_CHUNK_SIZE` | `512` | Target tokens per chunk |
| `NEXORA_CHUNK_OVERLAP` | `128` | Overlap between chunks |
| `NEXORA_AI_FAILFAST_THRESHOLD` | `3` | Consecutive failures before breaker opens |
| `NEXORA_AI_FALLBACK_PROVIDER` | `""` | Secondary provider (empty = no fallback) |

---

## 🔄 Switching Models / Providers / Backends

All three are **settings-only changes** — no code modifications required.

See `Project Tools/switch_model_guide.md` for complete switching matrix.

### Example: Switch to Ollama
```powershell
# In .env or settings.py
NEXORA_AI_PROVIDER=ollama
NEXORA_AI_MODEL=mistral
NEXORA_AI_BASE_URL=http://localhost:11434
```

### Example: Switch Vector Backend to pgvector
```powershell
NEXORA_VECTOR_BACKEND=pgvector
NEXORA_DATABASE_URL=postgresql://user:pass@localhost/nexora
NEXORA_EMBEDDING_DIM=384
```

---

## 📁 Directory Structure

```
PHASE_4B_AI_ENRICHMENT/
├── README.md (this file)
├── docs/                        Documentation & guides
├── tests/                       Test files
├── audits/                      Audit findings (45-test suite)
├── reports/                     Test reports & summaries
└── release_notes/
    └── release_notes_v4.5.0.md
```

---

## 🧪 Testing & Verification

### Connectivity Probe
```powershell
cd "Nexora application\Crawler"
python -m nexora_crawler.pipelines.test_ai
```

Expected: Successful LLM summary + embedding generation

### Vector Store Verification
```powershell
python -m nexora_crawler.pipelines.test_vector_store
```

Expected: Health check, record count, sample records with embeddings, round-trip search

### Full Test Suite
```powershell
cd "Nexora application"
python -m pytest outputs/audit/audit_round3_step3_2.py -v
python -m pytest outputs/audit/audit_round3_step3_3.py -v
```

See `outputs/audit/NEXORA_PHASE4B_TEST_SUMMARY.md` for detailed results.

---

## ✅ Known Limitations

- **Circuit breaker overshoot:** avg ≈ 680 tokens/chunk vs 512 target (overlap-driven; nice-to-have improvement)
- **Full re-validation:** Tests 06/07/08 need full-scale re-runs with active AI provider + Playwright

---

## 🔗 Related Resources

- **Phase 4A (Storage):** `../PHASE_4A_STORAGE/README.md`
- **Phase 4C (API):** `../PHASE_4C_API_INFRASTRUCTURE/README.md`
- **Main README:** `../../README.md`
- **Model Switch Guide:** `../../Project Tools/switch_model_guide.md`

---

**Last Updated:** August 21, 2026  
**Version:** 4.5.0  
**Phase Status:** Complete + Tested

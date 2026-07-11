# NEXORA PHASE 4B.5 -- UNIFIED MODEL AGNOSTIC AI PIPELINE
# Technical Specification for Agent Implementation
# Version: 1.0.0 | Date: 2026-07-11
# Purpose: Combine local (Ollama/HuggingFace) and cloud (OpenAI/Gemini) models
#          with seamless switching, no code changes required.

---

## TABLE OF CONTENTS

1. Architectural Vision
2. The Three-Engine Architecture
3. Engine 1: EmbeddingEngine (Local + Cloud)
4. Engine 2: SummaryEngine (Cloud-first, Local fallback)
5. Engine 3: TagEngine (Shared with SummaryEngine)
6. Unified Configuration System
7. Factory Pattern & Model Registry
8. Pipeline Integration
9. Backend Vector Store (Supabase/pgvector)
10. Migration Guide from Phase 4B
11. Agent Implementation Checklist

---

## 1. ARCHITECTURAL VISION

### Core Principle

> **One config change switches the entire AI layer from local to cloud and back. No code changes. No pipeline rewrites.**

Nexora's AI layer is split into **three independent engines**, each with its own provider, model, and backend. This allows:

- **Embeddings** to run locally (free, private, fast) while **summaries** run on cloud (high quality)
- **Instant fallback**: if cloud is down, auto-switch to local
- **Cost optimization**: use cheap local embeddings + premium cloud summaries
- **Future-proofing**: add new providers (Cohere, Mistral AI, etc.) by registering them in the factory

### Default Configuration (Out-of-the-Box)

| Engine | Default Provider | Default Model | Backend |
|--------|-----------------|---------------|---------|
| **Embeddings** | `huggingface` (local) | `all-MiniLM-L6-v2` | SentenceTransformers |
| **Summaries** | `openai` (cloud) | `gpt-4o-mini` | OpenAI API |
| **Tags** | `openai` (cloud) | `gpt-4o-mini` | OpenAI API (same as summaries) |

### Alternative Configuration (One-Line Switch)

| Engine | Provider | Model | Use Case |
|--------|----------|-------|----------|
| **Embeddings** | `huggingface` | `BAAI/bge-small-en-v1.5` | Higher quality local embeddings |
| **Summaries** | `google` | `gemini-1.5-flash` | Cheaper/faster than GPT |
| **Tags** | `google` | `gemini-1.5-flash` | Same as summaries |

---

## 2. THE THREE-ENGINE ARCHITECTURE

```
+-----------------------------------------------------------------------------+
|                         NEXORA AI LAYER (Phase 4B.5)                        |
+-----------------------------------------------------------------------------+
|                                                                              |
|   +---------------------------------------------------------------------+   |
|   |                    UnifiedConfig (settings.py)                      |   |
|   |  +-------------+  +-------------+  +-----------------------------+  |   |
|   |  |  EMBEDDING  |  |  SUMMARY    |  |  TAGS                       |  |   |
|   |  |  Config     |  |  Config     |  |  Config (inherits Summary)  |  |   |
|   |  +------+------+  +------+------+  +-----------------------------+  |   |
|   +--------+---------------+----------------------------------------------+   |
|            |               |                                                |
|            v               v                                                |
|   +-----------------+  +-----------------+                                  |
|   | EmbeddingEngine |  |  SummaryEngine  |                                  |
|   |  (Factory)      |  |   (Factory)     |                                  |
|   |  -----------    |  |   -----------   |                                  |
|   |  * HuggingFace  |  |  * OpenAI       |                                  |
|   |  * Ollama       |  |  * Google       |                                  |
|   |  * OpenAI       |  |  * Ollama       |                                  |
|   |  * LiteLLM      |  |  * LiteLLM      |                                  |
|   +--------+--------+  +--------+--------+                                  |
|            |                    |                                             |
|            v                    v                                             |
|   +---------------------------------------------------------------------+    |
|   |              AIEnrichmentPipeline (Priority 250)                  |    |
|   |  --------------------------------------------                     |    |
|   |  async def process_item(item, spider):                            |    |
|   |      embedding = await embedding_engine.embed(markdown)           |    |
|   |      summary   = await summary_engine.generate(markdown)          |    |
|   |      tags      = await tag_engine.generate(markdown)              |    |
|   |      item["ai_embedding"] = embedding                             |    |
|   |      item["ai_summary"]   = summary                               |    |
|   |      item["ai_tags"]      = tags                                  |    |
|   +---------------------------------------------------------------------+    |
|            |                                                                  |
|            v                                                                  |
|   +---------------------------------------------------------------------+    |
|   |           StructuralChunkingPipeline (Priority 260)                 |    |
|   |  -----------------------------------------------                  |    |
|   |  * Inherits ai_embedding from parent (NO second embed call)      |    |
|   |  * Splits into ~512-token chunks                                 |    |
|   |  * Preserves heading hierarchy                                   |    |
|   +---------------------------------------------------------------------+    |
|            |                                                                  |
|            v                                                                  |
|   +---------------------------------------------------------------------+    |
|   |            VectorIndexPipeline (Priority 270)                       |    |
|   |  --------------------------------------------                     |    |
|   |  * Converts chunks to VectorRecords                               |    |
|   |  * Factory: build_vector_store("pgvector" or "chroma")           |    |
|   |  * Stores in Supabase / local ChromaDB                            |    |
|   +---------------------------------------------------------------------+    |
|                                                                              |
+-----------------------------------------------------------------------------+
```

---

## 3. ENGINE 1: EMBEDDING ENGINE

### 3.1 Design Philosophy

The EmbeddingEngine is **model-agnostic**. It supports:

| Provider | Library | Models | Speed | Quality | Cost |
|----------|---------|--------|-------|---------|------|
| `huggingface` | `sentence-transformers` | `all-MiniLM-L6-v2`, `BAAI/bge-small-en-v1.5`, `BAAI/bge-large-en-v1.5` | Fast (GPU) | Good | Free |
| `ollama` | Ollama API | `nomic-embed-text`, `mxbai-embed-large` | Medium | Good | Free |
| `openai` | LiteLLM | `text-embedding-3-small`, `text-embedding-3-large` | Fast (cloud) | Excellent | Pay-per-use |
| `google` | LiteLLM | `text-embedding-004` | Fast (cloud) | Excellent | Pay-per-use |

### 3.2 Implementation

```python
# nexora_crawler/ai/embedding_engine.py
# Phase 4B.5 -- UNIFIED EMBEDDING ENGINE
# Supports: HuggingFace (local), Ollama (local), OpenAI (cloud), Google (cloud)

import asyncio
import logging
from typing import List, Optional, Protocol
from dataclasses import dataclass
from enum import Enum

logger = logging.getLogger(__name__)


class EmbeddingProvider(Enum):
    """Supported embedding providers. Add new ones here."""
    HUGGINGFACE = "huggingface"
    OLLAMA = "ollama"
    OPENAI = "openai"
    GOOGLE = "google"


@dataclass
class EmbeddingConfig:
    """Immutable configuration for an embedding provider."""
    provider: str
    model: str
    base_url: Optional[str] = None
    api_key: Optional[str] = None
    timeout: int = 30
    max_concurrent: int = 3
    device: str = "cpu"  # "cpu" or "cuda" or "mps" (for HuggingFace)
    normalize: bool = True
    trust_remote_code: bool = False  # for HuggingFace models

    @property
    def litellm_model(self) -> str:
        """LiteLLM format: provider/model"""
        return self.provider + "/" + self.model


class BaseEmbeddingBackend(Protocol):
    """Protocol that ALL embedding backends must implement."""

    async def embed(self, text: str) -> Optional[List[float]]:
        ...

    async def embed_batch(self, texts: List[str]) -> List[Optional[List[float]]]:
        ...

    def get_dimension(self) -> int:
        ...

    def health_check(self) -> bool:
        ...


class HuggingFaceBackend:
    """
    Local embedding backend via sentence-transformers.
    Runs entirely offline. No API calls. No keys needed.

    Models:
      - all-MiniLM-L6-v2      -> 384-dim, fastest, good baseline
      - BAAI/bge-small-en-v1.5 -> 384-dim, better quality
      - BAAI/bge-large-en-v1.5 -> 1024-dim, best quality, slower
    """

    DIMENSION_MAP = {
        "all-MiniLM-L6-v2": 384,
        "all-MiniLM-L12-v2": 384,
        "BAAI/bge-small-en-v1.5": 384,
        "BAAI/bge-base-en-v1.5": 768,
        "BAAI/bge-large-en-v1.5": 1024,
    }

    def __init__(self, config: EmbeddingConfig):
        self.config = config
        self._model = None
        self._semaphore = asyncio.Semaphore(config.max_concurrent)

    def _load_model(self):
        """Lazy-load the sentence-transformer model."""
        if self._model is not None:
            return

        from sentence_transformers import SentenceTransformer

        logger.info(
            "[HuggingFace] Loading model: %s (device=%s)",
            self.config.model, self.config.device
        )

        self._model = SentenceTransformer(
            self.config.model,
            device=self.config.device,
            trust_remote_code=self.config.trust_remote_code,
        )
        logger.info("[HuggingFace] Model loaded. Dim=%d", self.get_dimension())

    def get_dimension(self) -> int:
        if self.config.model in self.DIMENSION_MAP:
            return self.DIMENSION_MAP[self.config.model]
        # Fallback: load and check
        self._load_model()
        return self._model.get_sentence_embedding_dimension()

    async def embed(self, text: str) -> Optional[List[float]]:
        if not text or len(text.strip()) < 10:
            return None

        async with self._semaphore:
            try:
                # sentence-transformers is synchronous -- run in thread pool
                loop = asyncio.get_event_loop()
                return await loop.run_in_executor(
                    None, self._embed_sync, text[:8000]
                )
            except Exception as exc:
                logger.warning("[HuggingFace] Embed failed: %s", exc)
                return None

    def _embed_sync(self, text: str) -> List[float]:
        self._load_model()
        embedding = self._model.encode(
            text,
            normalize_embeddings=self.config.normalize,
            convert_to_numpy=True,
        )
        return embedding.tolist()

    async def embed_batch(self, texts: List[str]) -> List[Optional[List[float]]]:
        if not texts:
            return []

        async with self._semaphore:
            try:
                loop = asyncio.get_event_loop()
                return await loop.run_in_executor(
                    None, self._embed_batch_sync, texts
                )
            except Exception as exc:
                logger.warning("[HuggingFace] Batch embed failed: %s", exc)
                return [None] * len(texts)

    def _embed_batch_sync(self, texts: List[str]) -> List[List[float]]:
        self._load_model()
        embeddings = self._model.encode(
            [t[:8000] for t in texts if t and len(t.strip()) >= 10],
            normalize_embeddings=self.config.normalize,
            convert_to_numpy=True,
            batch_size=32,
            show_progress_bar=False,
        )
        return [e.tolist() for e in embeddings]

    def health_check(self) -> bool:
        try:
            self._load_model()
            test = self._model.encode("test", convert_to_numpy=True)
            return len(test) == self.get_dimension()
        except Exception:
            return False


class OllamaEmbeddingBackend:
    """
    Local embedding backend via Ollama.
    Requires Ollama running locally.

    Models:
      - nomic-embed-text    -> 768-dim
      - mxbai-embed-large   -> 1024-dim
    """

    def __init__(self, config: EmbeddingConfig):
        self.config = config
        self._semaphore = asyncio.Semaphore(config.max_concurrent)

    async def embed(self, text: str) -> Optional[List[float]]:
        if not text or len(text.strip()) < 10:
            return None

        async with self._semaphore:
            try:
                from litellm import aembedding
                base = self.config.base_url or "http://localhost:11434"
                key = self.config.api_key or "not-needed"
                response = await aembedding(
                    model=self.config.litellm_model,
                    input=text[:8000],
                    api_base=base,
                    api_key=key,
                    timeout=self.config.timeout,
                )
                return response.data[0]["embedding"]
            except Exception as exc:
                logger.warning("[Ollama] Embed failed: %s", exc)
                return None

    async def embed_batch(self, texts: List[str]) -> List[Optional[List[float]]]:
        tasks = [self.embed(t) for t in texts]
        return await asyncio.gather(*tasks, return_exceptions=False)

    def get_dimension(self) -> int:
        # Ollama model dims (hardcoded for known models)
        dims = {
            "nomic-embed-text": 768,
            "mxbai-embed-large": 1024,
        }
        return dims.get(self.config.model, 768)

    def health_check(self) -> bool:
        import httpx
        try:
            url = (self.config.base_url or "http://localhost:11434") + "/api/tags"
            r = httpx.get(url, timeout=5)
            return r.status_code == 200
        except Exception:
            return False


class LiteLLMEmbeddingBackend:
    """
    Cloud embedding backend via LiteLLM.
    Supports OpenAI, Google, Cohere, Azure, etc.

    Models:
      - openai/text-embedding-3-small    -> 1536-dim
      - openai/text-embedding-3-large    -> 3072-dim
      - google/text-embedding-004      -> 768-dim
    """

    DIMENSION_MAP = {
        "text-embedding-3-small": 1536,
        "text-embedding-3-large": 3072,
        "text-embedding-ada-002": 1536,
        "text-embedding-004": 768,
    }

    def __init__(self, config: EmbeddingConfig):
        self.config = config
        self._semaphore = asyncio.Semaphore(config.max_concurrent)

    async def embed(self, text: str) -> Optional[List[float]]:
        if not text or len(text.strip()) < 10:
            return None

        async with self._semaphore:
            try:
                from litellm import aembedding
                response = await aembedding(
                    model=self.config.litellm_model,
                    input=text[:8000],
                    api_base=self.config.base_url,
                    api_key=self.config.api_key,
                    timeout=self.config.timeout,
                )
                return response.data[0]["embedding"]
            except Exception as exc:
                logger.warning(
                    "[%s] Embed failed: %s",
                    self.config.provider, exc
                )
                return None

    async def embed_batch(self, texts: List[str]) -> List[Optional[List[float]]]:
        tasks = [self.embed(t) for t in texts]
        return await asyncio.gather(*tasks, return_exceptions=False)

    def get_dimension(self) -> int:
        return self.DIMENSION_MAP.get(self.config.model, 1536)

    def health_check(self) -> bool:
        import httpx
        try:
            if self.config.provider == "openai":
                url = "https://api.openai.com/v1/models"
                headers = {"Authorization": "Bearer " + self.config.api_key}
                r = httpx.get(url, headers=headers, timeout=10)
                return r.status_code == 200
            return bool(self.config.api_key)
        except Exception:
            return False


# ===================================================================
# FACTORY: Build the right backend from config
# ===================================================================

BACKEND_REGISTRY = {
    EmbeddingProvider.HUGGINGFACE.value: HuggingFaceBackend,
    EmbeddingProvider.OLLAMA.value: OllamaEmbeddingBackend,
    EmbeddingProvider.OPENAI.value: LiteLLMEmbeddingBackend,
    EmbeddingProvider.GOOGLE.value: LiteLLMEmbeddingBackend,
}


def build_embedding_backend(config: EmbeddingConfig) -> BaseEmbeddingBackend:
    """Factory: create the correct backend from config."""
    provider = config.provider.lower()
    if provider not in BACKEND_REGISTRY:
        supported = list(BACKEND_REGISTRY.keys())
        raise ValueError(
            "Unknown embedding provider: " + provider +
            ". Supported: " + str(supported)
        )
    backend_cls = BACKEND_REGISTRY[provider]
    return backend_cls(config)


# ===================================================================
# UNIFIED EMBEDDING ENGINE (Public API)
# ===================================================================

class UnifiedEmbeddingEngine:
    """
    SINGLE SOURCE OF TRUTH for all embedding generation.

    Usage:
        # Default: HuggingFace local
        engine = UnifiedEmbeddingEngine.from_settings(settings)
        vec = await engine.embed("text to embed")

        # Or explicit config
        config = EmbeddingConfig(
            provider="huggingface",
            model="all-MiniLM-L6-v2",
            device="cuda"
        )
        engine = UnifiedEmbeddingEngine(config)
    """

    def __init__(self, config: EmbeddingConfig):
        self.config = config
        self.backend = build_embedding_backend(config)
        self.stats = {
            "embeddings_generated": 0,
            "batches_processed": 0,
            "errors": 0,
        }

    @classmethod
    def from_settings(cls, settings) -> "UnifiedEmbeddingEngine":
        """Build engine from Scrapy settings."""
        config = EmbeddingConfig(
            provider=settings.get('NEXORA_EMBEDDING_PROVIDER', 'huggingface'),
            model=settings.get('NEXORA_EMBEDDING_MODEL', 'all-MiniLM-L6-v2'),
            base_url=settings.get('NEXORA_EMBEDDING_BASE_URL', None),
            api_key=settings.get('NEXORA_EMBEDDING_API_KEY', None),
            timeout=settings.getint('NEXORA_EMBEDDING_TIMEOUT', 30),
            max_concurrent=settings.getint('NEXORA_EMBEDDING_MAX_CONCURRENT', 3),
            device=settings.get('NEXORA_EMBEDDING_DEVICE', 'cpu'),
            normalize=settings.getbool('NEXORA_EMBEDDING_NORMALIZE', True),
            trust_remote_code=settings.getbool('NEXORA_EMBEDDING_TRUST_REMOTE', False),
        )
        return cls(config)

    async def embed(self, text: str) -> Optional[List[float]]:
        result = await self.backend.embed(text)
        if result is not None:
            self.stats["embeddings_generated"] += 1
        else:
            self.stats["errors"] += 1
        return result

    async def embed_batch(self, texts: List[str]) -> List[Optional[List[float]]]:
        results = await self.backend.embed_batch(texts)
        self.stats["batches_processed"] += 1
        self.stats["embeddings_generated"] += sum(1 for r in results if r is not None)
        self.stats["errors"] += sum(1 for r in results if r is None)
        return results

    def get_dimension(self) -> int:
        return self.backend.get_dimension()

    def health_check(self) -> bool:
        return self.backend.health_check()

    def get_stats(self) -> dict:
        return dict(self.stats)
```

### 3.3 Default Embedding Config (settings.py)

```python
# ===================================================================
# EMBEDDING ENGINE CONFIGURATION
# ===================================================================

# --- DEFAULT: HuggingFace all-MiniLM-L6-v2 (384-dim, CPU, offline) ---
NEXORA_EMBEDDING_PROVIDER = "huggingface"
NEXORA_EMBEDDING_MODEL = "all-MiniLM-L6-v2"
NEXORA_EMBEDDING_DEVICE = "cpu"              # "cpu" or "cuda" or "mps"
NEXORA_EMBEDDING_NORMALIZE = True
NEXORA_EMBEDDING_TIMEOUT = 30
NEXORA_EMBEDDING_MAX_CONCURRENT = 3
NEXORA_EMBEDDING_BASE_URL = None
NEXORA_EMBEDDING_API_KEY = None

# ALTERNATIVE EMBEDDING CONFIGS (uncomment to switch):

# --- Option A: Better HuggingFace model ---
# NEXORA_EMBEDDING_MODEL = "BAAI/bge-small-en-v1.5"   # 384-dim, better retrieval
# NEXORA_EMBEDDING_MODEL = "BAAI/bge-large-en-v1.5"   # 1024-dim, best retrieval

# --- Option B: Ollama local ---
# NEXORA_EMBEDDING_PROVIDER = "ollama"
# NEXORA_EMBEDDING_MODEL = "nomic-embed-text"          # 768-dim
# NEXORA_EMBEDDING_BASE_URL = "http://localhost:11434"
# NEXORA_EMBEDDING_API_KEY = "not-needed"

# --- Option C: OpenAI cloud ---
# NEXORA_EMBEDDING_PROVIDER = "openai"
# NEXORA_EMBEDDING_MODEL = "text-embedding-3-small"    # 1536-dim
# NEXORA_EMBEDDING_BASE_URL = "https://api.openai.com/v1"
# NEXORA_EMBEDDING_API_KEY = os.environ.get("OPENAI_API_KEY")

# --- Option D: Google cloud ---
# NEXORA_EMBEDDING_PROVIDER = "google"
# NEXORA_EMBEDDING_MODEL = "text-embedding-004"          # 768-dim
# NEXORA_EMBEDDING_BASE_URL = "https://generativelanguage.googleapis.com/v1"
# NEXORA_EMBEDDING_API_KEY = os.environ.get("GOOGLE_API_KEY")
```

---

## 4. ENGINE 2: SUMMARY ENGINE

### 4.1 Design Philosophy

The SummaryEngine is **cloud-first by default** (OpenAI GPT-4o-mini) but supports:

| Provider | Models | Use Case |
|----------|--------|----------|
| `openai` | `gpt-4o`, `gpt-4o-mini`, `gpt-3.5-turbo` | High quality, reliable |
| `google` | `gemini-1.5-flash`, `gemini-1.5-pro` | Cheaper, faster, good quality |
| `ollama` | `llama3`, `mistral`, `phi3` | Free local fallback |

### 4.2 Implementation

```python
# nexora_crawler/ai/summary_engine.py
# Phase 4B.5 -- SUMMARY & TAG GENERATION ENGINE

import asyncio
import json
import logging
from typing import List, Optional, Protocol
from dataclasses import dataclass
from enum import Enum

from litellm import acompletion

logger = logging.getLogger(__name__)


class SummaryProvider(Enum):
    OPENAI = "openai"
    GOOGLE = "google"
    OLLAMA = "ollama"
    ANTHROPIC = "anthropic"


@dataclass
class SummaryConfig:
    """Configuration for summary/tag generation."""
    provider: str
    model: str
    base_url: Optional[str] = None
    api_key: Optional[str] = None
    timeout: int = 60
    max_concurrent: int = 5
    max_tokens_summary: int = 200
    max_tokens_tags: int = 100
    temperature: float = 0.3

    @property
    def litellm_model(self) -> str:
        return self.provider + "/" + self.model


class BaseSummaryBackend(Protocol):
    async def generate_summary(self, text: str) -> str: ...
    async def generate_tags(self, text: str) -> List[str]: ...
    def health_check(self) -> bool: ...


class LiteLLMSummaryBackend:
    """
    Cloud/local LLM backend via LiteLLM.
    Supports OpenAI, Google Gemini, Ollama, Anthropic.
    """

    def __init__(self, config: SummaryConfig):
        self.config = config
        self._semaphore = asyncio.Semaphore(config.max_concurrent)

    async def generate_summary(self, text: str) -> str:
        prompt = ("Summarize the following web page content in 2-3 sentences.\n"
                  "Be concise and capture the main points.\n\nContent:\n"
                  + text[:4000] + "\n\nSummary:")

        async with self._semaphore:
            try:
                response = await acompletion(
                    model=self.config.litellm_model,
                    messages=[{"role": "user", "content": prompt}],
                    api_base=self.config.base_url,
                    api_key=self.config.api_key,
                    timeout=self.config.timeout,
                    max_tokens=self.config.max_tokens_summary,
                    temperature=self.config.temperature,
                )
                return response.choices[0].message.content.strip()
            except Exception as exc:
                logger.warning(
                    "[%s] Summary failed: %s",
                    self.config.provider, exc
                )
                return ""

    async def generate_tags(self, text: str) -> List[str]:
        prompt = ("Extract 3-5 relevant topic tags from the following content.\n"
                  "Return ONLY a JSON array of strings, no other text.\n\nContent:\n"
                  + text[:3000] + "\n\nTags (JSON array):")

        async with self._semaphore:
            try:
                response = await acompletion(
                    model=self.config.litellm_model,
                    messages=[{"role": "user", "content": prompt}],
                    api_base=self.config.base_url,
                    api_key=self.config.api_key,
                    timeout=self.config.timeout,
                    max_tokens=self.config.max_tokens_tags,
                    temperature=self.config.temperature,
                )
                content = response.choices[0].message.content.strip()
                # Parse JSON array
                if "[" in content and "]" in content:
                    start = content.find("[")
                    end = content.rfind("]") + 1
                    tags = json.loads(content[start:end])
                else:
                    tags = [t.strip() for t in content.split(",")]
                return [str(t) for t in tags[:5]]
            except Exception as exc:
                logger.warning(
                    "[%s] Tags failed: %s",
                    self.config.provider, exc
                )
                return []

    def health_check(self) -> bool:
        import httpx
        try:
            if self.config.provider == "openai":
                r = httpx.get(
                    "https://api.openai.com/v1/models",
                    headers={"Authorization": "Bearer " + self.config.api_key},
                    timeout=10
                )
                return r.status_code == 200
            return bool(self.config.api_key)
        except Exception:
            return False


# Factory
SUMMARY_BACKEND_REGISTRY = {
    SummaryProvider.OPENAI.value: LiteLLMSummaryBackend,
    SummaryProvider.GOOGLE.value: LiteLLMSummaryBackend,
    SummaryProvider.OLLAMA.value: LiteLLMSummaryBackend,
    SummaryProvider.ANTHROPIC.value: LiteLLMSummaryBackend,
}


def build_summary_backend(config: SummaryConfig) -> BaseSummaryBackend:
    provider = config.provider.lower()
    if provider not in SUMMARY_BACKEND_REGISTRY:
        raise ValueError("Unknown summary provider: " + provider)
    return SUMMARY_BACKEND_REGISTRY[provider](config)


# ===================================================================
# UNIFIED SUMMARY ENGINE (Public API)
# ===================================================================

class UnifiedSummaryEngine:
    """
    SINGLE SOURCE OF TRUTH for summary and tag generation.

    Usage:
        engine = UnifiedSummaryEngine.from_settings(settings)
        summary = await engine.generate_summary(markdown)
        tags = await engine.generate_tags(markdown)
    """

    def __init__(self, config: SummaryConfig):
        self.config = config
        self.backend = build_summary_backend(config)
        self.stats = {
            "summaries_generated": 0,
            "tags_generated": 0,
            "errors": 0,
        }

    @classmethod
    def from_settings(cls, settings) -> "UnifiedSummaryEngine":
        config = SummaryConfig(
            provider=settings.get('NEXORA_SUMMARY_PROVIDER', 'openai'),
            model=settings.get('NEXORA_SUMMARY_MODEL', 'gpt-4o-mini'),
            base_url=settings.get('NEXORA_SUMMARY_BASE_URL', None),
            api_key=settings.get('NEXORA_SUMMARY_API_KEY', None),
            timeout=settings.getint('NEXORA_SUMMARY_TIMEOUT', 60),
            max_concurrent=settings.getint('NEXORA_SUMMARY_MAX_CONCURRENT', 5),
            max_tokens_summary=settings.getint('NEXORA_SUMMARY_MAX_TOKENS', 200),
            max_tokens_tags=settings.getint('NEXORA_TAGS_MAX_TOKENS', 100),
            temperature=settings.getfloat('NEXORA_SUMMARY_TEMPERATURE', 0.3),
        )
        return cls(config)

    async def generate_summary(self, text: str) -> str:
        result = await self.backend.generate_summary(text)
        if result:
            self.stats["summaries_generated"] += 1
        else:
            self.stats["errors"] += 1
        return result

    async def generate_tags(self, text: str) -> List[str]:
        result = await self.backend.generate_tags(text)
        if result:
            self.stats["tags_generated"] += 1
        else:
            self.stats["errors"] += 1
        return result

    def health_check(self) -> bool:
        return self.backend.health_check()

    def get_stats(self) -> dict:
        return dict(self.stats)
```

### 4.3 Default Summary Config (settings.py)

```python
# ===================================================================
# SUMMARY & TAGS ENGINE CONFIGURATION
# ===================================================================

# --- DEFAULT: OpenAI Cloud (gpt-4o-mini) ---
NEXORA_SUMMARY_PROVIDER = "openai"
NEXORA_SUMMARY_MODEL = "gpt-4o-mini"           # cheap, fast, good quality
# Alternative OpenAI models:
# NEXORA_SUMMARY_MODEL = "gpt-4o"              # higher quality
# NEXORA_SUMMARY_MODEL = "gpt-3.5-turbo"       # cheapest, acceptable quality

NEXORA_SUMMARY_BASE_URL = "https://api.openai.com/v1"
NEXORA_SUMMARY_API_KEY = os.environ.get("OPENAI_API_KEY")
NEXORA_SUMMARY_TIMEOUT = 60
NEXORA_SUMMARY_MAX_CONCURRENT = 5
NEXORA_SUMMARY_MAX_TOKENS = 200
NEXORA_TAGS_MAX_TOKENS = 100
NEXORA_SUMMARY_TEMPERATURE = 0.3

# ALTERNATIVE SUMMARY CONFIGS (uncomment to switch):

# --- Option A: Better OpenAI model ---
# NEXORA_SUMMARY_MODEL = "gpt-4o"                      # higher quality

# --- Option B: Google Gemini ---
# NEXORA_SUMMARY_PROVIDER = "google"
# NEXORA_SUMMARY_MODEL = "gemini-1.5-flash"            # very fast, very cheap
# NEXORA_SUMMARY_BASE_URL = "https://generativelanguage.googleapis.com/v1"
# NEXORA_SUMMARY_API_KEY = os.environ.get("GOOGLE_API_KEY")

# --- Option C: Ollama local fallback ---
# NEXORA_SUMMARY_PROVIDER = "ollama"
# NEXORA_SUMMARY_MODEL = "llama3"
# NEXORA_SUMMARY_BASE_URL = "http://localhost:11434"
# NEXORA_SUMMARY_API_KEY = "not-needed"
# NEXORA_SUMMARY_TIMEOUT = 120                         # local is slower
```

---

## 5. ENGINE 3: TAG ENGINE

Tags use the **same backend as summaries** by default. No separate engine needed -- `UnifiedSummaryEngine` handles both. If you want tags from a different provider than summaries, instantiate a second engine:

```python
# In AIEnrichmentPipeline:
self.summary_engine = UnifiedSummaryEngine.from_settings(settings)

# Tags from same provider (default):
self.tag_engine = self.summary_engine

# OR tags from different provider:
tag_config = SummaryConfig(
    provider="google",
    model="gemini-1.5-flash",
    api_key=os.environ["GOOGLE_API_KEY"],
)
self.tag_engine = UnifiedSummaryEngine(tag_config)
```

---

## 6. UNIFIED CONFIGURATION SYSTEM

### 6.1 Complete settings.py (Phase 4B.5)

```python
# nexora_crawler/settings.py
# Phase 4B.5 -- UNIFIED MODEL AGNOSTIC CONFIGURATION

import os

# ===================================================================
# MASTER AI SWITCH
# ===================================================================
NEXORA_AI_ENABLED = True

# ===================================================================
# EMBEDDING ENGINE (Local by default -- free, private, fast)
# ===================================================================

# DEFAULT: HuggingFace all-MiniLM-L6-v2 (384-dim, CPU, offline)
NEXORA_EMBEDDING_PROVIDER = "huggingface"
NEXORA_EMBEDDING_MODEL = "all-MiniLM-L6-v2"
NEXORA_EMBEDDING_DEVICE = "cpu"              # "cpu" or "cuda" or "mps"
NEXORA_EMBEDDING_NORMALIZE = True
NEXORA_EMBEDDING_TIMEOUT = 30
NEXORA_EMBEDDING_MAX_CONCURRENT = 3
NEXORA_EMBEDDING_BASE_URL = None
NEXORA_EMBEDDING_API_KEY = None

# ALTERNATIVE EMBEDDING CONFIGS (uncomment to switch):

# --- Option A: Better HuggingFace model ---
# NEXORA_EMBEDDING_MODEL = "BAAI/bge-small-en-v1.5"   # 384-dim, better retrieval
# NEXORA_EMBEDDING_MODEL = "BAAI/bge-large-en-v1.5"   # 1024-dim, best retrieval

# --- Option B: Ollama local ---
# NEXORA_EMBEDDING_PROVIDER = "ollama"
# NEXORA_EMBEDDING_MODEL = "nomic-embed-text"          # 768-dim
# NEXORA_EMBEDDING_BASE_URL = "http://localhost:11434"
# NEXORA_EMBEDDING_API_KEY = "not-needed"

# --- Option C: OpenAI cloud ---
# NEXORA_EMBEDDING_PROVIDER = "openai"
# NEXORA_EMBEDDING_MODEL = "text-embedding-3-small"    # 1536-dim
# NEXORA_EMBEDDING_BASE_URL = "https://api.openai.com/v1"
# NEXORA_EMBEDDING_API_KEY = os.environ.get("OPENAI_API_KEY")

# --- Option D: Google cloud ---
# NEXORA_EMBEDDING_PROVIDER = "google"
# NEXORA_EMBEDDING_MODEL = "text-embedding-004"          # 768-dim
# NEXORA_EMBEDDING_BASE_URL = "https://generativelanguage.googleapis.com/v1"
# NEXORA_EMBEDDING_API_KEY = os.environ.get("GOOGLE_API_KEY")

# ===================================================================
# SUMMARY ENGINE (Cloud by default -- high quality)
# ===================================================================

# DEFAULT: OpenAI gpt-4o-mini (cheap, fast, good)
NEXORA_SUMMARY_PROVIDER = "openai"
NEXORA_SUMMARY_MODEL = "gpt-4o-mini"
NEXORA_SUMMARY_BASE_URL = "https://api.openai.com/v1"
NEXORA_SUMMARY_API_KEY = os.environ.get("OPENAI_API_KEY")
NEXORA_SUMMARY_TIMEOUT = 60
NEXORA_SUMMARY_MAX_CONCURRENT = 5
NEXORA_SUMMARY_MAX_TOKENS = 200
NEXORA_TAGS_MAX_TOKENS = 100
NEXORA_SUMMARY_TEMPERATURE = 0.3

# ALTERNATIVE SUMMARY CONFIGS (uncomment to switch):

# --- Option A: Better OpenAI model ---
# NEXORA_SUMMARY_MODEL = "gpt-4o"                      # higher quality

# --- Option B: Google Gemini ---
# NEXORA_SUMMARY_PROVIDER = "google"
# NEXORA_SUMMARY_MODEL = "gemini-1.5-flash"            # very fast, very cheap
# NEXORA_SUMMARY_BASE_URL = "https://generativelanguage.googleapis.com/v1"
# NEXORA_SUMMARY_API_KEY = os.environ.get("GOOGLE_API_KEY")

# --- Option C: Ollama local fallback ---
# NEXORA_SUMMARY_PROVIDER = "ollama"
# NEXORA_SUMMARY_MODEL = "llama3"
# NEXORA_SUMMARY_BASE_URL = "http://localhost:11434"
# NEXORA_SUMMARY_API_KEY = "not-needed"
# NEXORA_SUMMARY_TIMEOUT = 120                         # local is slower

# ===================================================================
# VECTOR STORE (Supabase/pgvector for production)
# ===================================================================

NEXORA_VECTOR_INDEX_ENABLED = True
NEXORA_VECTOR_BACKEND = "pgvector"                    # "pgvector" or "chroma"
NEXORA_VECTOR_DB_PATH = "./data/vector_db"            # only for chroma

# Supabase connection (free tier works for dev, Pro for production)
NEXORA_DATABASE_URL = os.environ.get(
    "SUPABASE_DATABASE_URL",
    "postgresql://postgres:password@localhost:5432/nexora"
)

# Embedding dimension MUST match your chosen embedding model:
#   all-MiniLM-L6-v2        -> 384
#   BAAI/bge-small-en-v1.5  -> 384
#   BAAI/bge-large-en-v1.5  -> 1024
#   nomic-embed-text        -> 768
#   mxbai-embed-large       -> 1024
#   text-embedding-3-small  -> 1536
#   text-embedding-3-large  -> 3072
#   text-embedding-004      -> 768
NEXORA_EMBEDDING_DIM = 384

# ===================================================================
# CHUNKING
# ===================================================================
NEXORA_CHUNK_SIZE = 512
NEXORA_CHUNK_OVERLAP = 128

# ===================================================================
# PIPELINE REGISTRATION
# ===================================================================
ITEM_PIPELINES = {
    # ... Phase 3 & 4A pipelines ...
    'nexora_crawler.pipelines.ai_enrichment.AIEnrichmentPipeline': 250,
    'nexora_crawler.pipelines.chunking_pipeline.StructuralChunkingPipeline': 260,
    'nexora_crawler.pipelines.vector_index_pipeline.VectorIndexPipeline': 270,
    'nexora_crawler.pipelines.parquet_export.ParquetExportPipeline': 450,
}
```

### 6.2 Environment Variables Template (.env)

```bash
# .env -- copy to project root, add to .gitignore

# --- OpenAI (for summaries) ---
OPENAI_API_KEY=sk-your-openai-key-here

# --- Google Gemini (alternative for summaries) ---
GOOGLE_API_KEY=your-google-api-key-here

# --- Supabase (for vector storage) ---
SUPABASE_DATABASE_URL=postgresql://postgres:[password]@db.[project].supabase.co:5432/postgres

# --- Optional: separate embedding API key ---
# Only needed if embeddings use a different provider than summaries
# OPENAI_API_KEY is reused by default if NEXORA_EMBEDDING_API_KEY is not set
```

---

## 7. FACTORY PATTERN & MODEL REGISTRY

### 7.1 How to Add a New Provider (No Pipeline Changes)

**Example: Adding Cohere embeddings**

```python
# Step 1: Add to BACKEND_REGISTRY in embedding_engine.py
from .cohere_backend import CohereEmbeddingBackend  # new file

BACKEND_REGISTRY = {
    # ... existing ...
    "cohere": CohereEmbeddingBackend,
}

# Step 2: Create cohere_backend.py
class CohereEmbeddingBackend:
    def __init__(self, config: EmbeddingConfig):
        self.config = config

    async def embed(self, text: str) -> Optional[List[float]]:
        # Use cohere SDK or LiteLLM
        from litellm import aembedding
        response = await aembedding(
            model="cohere/embed-english-v3",
            input=text,
            api_key=self.config.api_key,
        )
        return response.data[0]["embedding"]

    def get_dimension(self) -> int:
        return 1024  # cohere-english-v3

# Step 3: Use in settings.py
# NEXORA_EMBEDDING_PROVIDER = "cohere"
# NEXORA_EMBEDDING_MODEL = "embed-english-v3"
# NEXORA_EMBEDDING_API_KEY = os.environ.get("COHERE_API_KEY")
```

**That's it.** The factory picks it up. The pipeline doesn't know or care.

---

## 8. PIPELINE INTEGRATION

### 8.1 Refactored AIEnrichmentPipeline

```python
# nexora_crawler/pipelines/ai_enrichment.py
# Phase 4B.5 -- INTEGRATED WITH UNIFIED ENGINES

import asyncio
import logging
from typing import Dict, List

from nexora_crawler.ai.embedding_engine import UnifiedEmbeddingEngine
from nexora_crawler.ai.summary_engine import UnifiedSummaryEngine

logger = logging.getLogger(__name__)


class AIEnrichmentPipeline:
    """
    Scrapy pipeline for AI-powered content enrichment.
    Priority: 250

    Uses THREE independent engines:
      1. EmbeddingEngine  -> item["ai_embedding"]
      2. SummaryEngine    -> item["ai_summary"]
      3. TagEngine        -> item["ai_tags"]

    Each engine has its own provider, model, and backend.
    """

    def __init__(self, crawler):
        self.crawler = crawler
        self.settings = crawler.settings
        self.enabled = self.settings.getbool('NEXORA_AI_ENABLED', False)

        # --- ENGINE 1: Embeddings ---
        self.embeddings_enabled = self.settings.getbool('NEXORA_EMBEDDINGS_ENABLED', True)
        self.embedding_engine = (
            UnifiedEmbeddingEngine.from_settings(self.settings)
            if self.embeddings_enabled else None
        )

        # --- ENGINE 2: Summaries ---
        self.summary_engine = UnifiedSummaryEngine.from_settings(self.settings)

        # --- ENGINE 3: Tags (same backend as summaries by default) ---
        self.tag_engine = self.summary_engine

        self.stats = {
            "summaries_generated": 0,
            "tags_generated": 0,
            "embeddings_generated": 0,
            "ai_errors": 0,
        }

    @classmethod
    def from_crawler(cls, crawler):
        return cls(crawler)

    async def process_item(self, item, spider):
        if not self.enabled:
            return item

        markdown = item.get("markdown", "")
        if not markdown or len(markdown) < 100:
            return item

        try:
            # Run all three operations concurrently
            tasks = []

            # Summary
            tasks.append(self.summary_engine.generate_summary(markdown))

            # Tags
            tasks.append(self.tag_engine.generate_tags(markdown))

            # Embedding (if enabled)
            if self.embedding_engine:
                tasks.append(self.embedding_engine.embed(markdown[:4000]))
            else:
                tasks.append(asyncio.sleep(0))

            summary, tags, embedding = await asyncio.gather(*tasks)

            item["ai_summary"] = summary
            item["ai_tags"] = tags
            if embedding:
                item["ai_embedding"] = embedding
                self.stats["embeddings_generated"] += 1
            if summary:
                self.stats["summaries_generated"] += 1
            if tags:
                self.stats["tags_generated"] += 1

        except Exception as exc:
            logger.warning(
                "[AI] Enrichment failed for %s: %s",
                item.get("url", "unknown"), exc
            )
            self.stats["ai_errors"] += 1

        return item

    def close_spider(self, spider):
        logger.info("[AI] Pipeline stats: %s", self.stats)
        if self.embedding_engine:
            logger.info(
                "[EmbeddingEngine] Stats: %s",
                self.embedding_engine.get_stats()
            )
        if self.summary_engine:
            logger.info(
                "[SummaryEngine] Stats: %s",
                self.summary_engine.get_stats()
            )
```

---

## 9. BACKEND VECTOR STORE (Supabase)

Use the existing `PgVectorStore` from Phase 4B Additional Integration Patch. No changes needed -- it already supports:

- HNSW index for fast ANN search
- `workspace_id` for multi-tenancy
- Hybrid search (vector + BM25 FTS)
- Full CRUD operations

**Supabase connection:**
```python
NEXORA_DATABASE_URL = "postgresql://postgres:[password]@db.[project].supabase.co:5432/postgres"
```

**Free tier limits** (as noted earlier):
- 500 MB storage -> ~50K-100K chunks
- 2 GB bandwidth/month
- Auto-pauses after 1 week inactivity

**For production:** Upgrade to Supabase Pro ($25/month) or self-host Postgres + pgvector.

---

## 10. MIGRATION GUIDE FROM PHASE 4B

### Files to Create

| File | Purpose |
|------|---------|
| `nexora_crawler/ai/embedding_engine.py` | New -- replaces old UnifiedEmbeddingEngine |
| `nexora_crawler/ai/summary_engine.py` | New -- summary/tag generation |
| `nexora_crawler/ai/__init__.py` | Package init, exports |

### Files to Modify

| File | Change |
|------|--------|
| `nexora_crawler/pipelines/ai_enrichment.py` | Replace old engine imports with new `UnifiedEmbeddingEngine` + `UnifiedSummaryEngine` |
| `nexora_crawler/settings.py` | Replace old AI config with new separated embedding/summary configs |
| `requirements.txt` | Add `sentence-transformers` for HuggingFace backend |

### Files to Delete

| File | Reason |
|------|--------|
| Old `embedding_engine.py` (if exists) | Replaced by new model-agnostic version |

### Dependencies to Add

```bash
pip install sentence-transformers  # for HuggingFace local embeddings
# torch is pulled automatically; for GPU: pip install torch torchvision torchaudio
```

---

## 11. AGENT IMPLEMENTATION CHECKLIST

```markdown
- [ ] Create `nexora_crawler/ai/` package directory
- [ ] Write `embedding_engine.py` with HuggingFace, Ollama, OpenAI, Google backends
- [ ] Write `summary_engine.py` with LiteLLM backend for OpenAI, Google, Ollama
- [ ] Write `__init__.py` exporting `UnifiedEmbeddingEngine`, `UnifiedSummaryEngine`
- [ ] Refactor `ai_enrichment.py` to use both new engines
- [ ] Update `settings.py` with new config keys (embedding_* and summary_* separated)
- [ ] Add `sentence-transformers` to requirements
- [ ] Update `NEXORA_EMBEDDING_DIM` to match chosen model (384 default)
- [ ] Test: `python -c "from nexora_crawler.ai.embedding_engine import UnifiedEmbeddingEngine; print('OK')"`
- [ ] Test: `python -c "from nexora_crawler.ai.summary_engine import UnifiedSummaryEngine; print('OK')"`
- [ ] Run crawler with default config (HuggingFace + OpenAI)
- [ ] Verify embeddings stored in Supabase/pgvector
- [ ] Switch to all-local config (HuggingFace + Ollama) and verify
- [ ] Switch to all-cloud config (OpenAI + OpenAI) and verify
- [ ] Verify no regression in Phase 4A/4B tests
```

---

## APPENDIX A: QUICK CONFIG SWITCHING

### Scenario 1: Fully Local (Free, Private, No API Keys)
```python
NEXORA_EMBEDDING_PROVIDER = "huggingface"
NEXORA_EMBEDDING_MODEL = "all-MiniLM-L6-v2"
NEXORA_EMBEDDING_DEVICE = "cpu"

NEXORA_SUMMARY_PROVIDER = "ollama"
NEXORA_SUMMARY_MODEL = "llama3"
NEXORA_SUMMARY_BASE_URL = "http://localhost:11434"
NEXORA_SUMMARY_API_KEY = "not-needed"

NEXORA_EMBEDDING_DIM = 384
```

### Scenario 2: Fully Cloud (Best Quality, Pay-Per-Use)
```python
NEXORA_EMBEDDING_PROVIDER = "openai"
NEXORA_EMBEDDING_MODEL = "text-embedding-3-small"
NEXORA_EMBEDDING_API_KEY = os.environ["OPENAI_API_KEY"]

NEXORA_SUMMARY_PROVIDER = "openai"
NEXORA_SUMMARY_MODEL = "gpt-4o"
NEXORA_SUMMARY_API_KEY = os.environ["OPENAI_API_KEY"]

NEXORA_EMBEDDING_DIM = 1536
```

### Scenario 3: Hybrid Recommended (Best Cost/Quality Balance)
```python
# Embeddings: Local (free, fast, private)
NEXORA_EMBEDDING_PROVIDER = "huggingface"
NEXORA_EMBEDDING_MODEL = "BAAI/bge-small-en-v1.5"  # better than MiniLM
NEXORA_EMBEDDING_DEVICE = "cuda"                    # if GPU available

# Summaries: Cloud (high quality)
NEXORA_SUMMARY_PROVIDER = "openai"
NEXORA_SUMMARY_MODEL = "gpt-4o-mini"
NEXORA_SUMMARY_API_KEY = os.environ["OPENAI_API_KEY"]

NEXORA_EMBEDDING_DIM = 384
```

### Scenario 4: Google-First (Cheaper than OpenAI)
```python
NEXORA_EMBEDDING_PROVIDER = "google"
NEXORA_EMBEDDING_MODEL = "text-embedding-004"
NEXORA_EMBEDDING_API_KEY = os.environ["GOOGLE_API_KEY"]

NEXORA_SUMMARY_PROVIDER = "google"
NEXORA_SUMMARY_MODEL = "gemini-1.5-flash"
NEXORA_SUMMARY_API_KEY = os.environ["GOOGLE_API_KEY"]

NEXORA_EMBEDDING_DIM = 768
```

---

## APPENDIX B: MODEL DIMENSION REFERENCE

| Model | Provider | Dimension | Speed | Quality | Best For |
|-------|----------|-----------|-------|---------|----------|
| `all-MiniLM-L6-v2` | HuggingFace | 384 | *** Fast | ** Good | Default, balanced |
| `BAAI/bge-small-en-v1.5` | HuggingFace | 384 | ** Fast | *** Better | Better retrieval |
| `BAAI/bge-large-en-v1.5` | HuggingFace | 1024 | * Slow | **** Best | Max quality, local |
| `nomic-embed-text` | Ollama | 768 | ** Medium | *** Better | Ollama ecosystem |
| `text-embedding-3-small` | OpenAI | 1536 | *** Fast | **** Excellent | Cloud, cost-effective |
| `text-embedding-3-large` | OpenAI | 3072 | ** Fast | ***** Best | Cloud, max quality |
| `text-embedding-004` | Google | 768 | *** Fast | **** Excellent | Google ecosystem |

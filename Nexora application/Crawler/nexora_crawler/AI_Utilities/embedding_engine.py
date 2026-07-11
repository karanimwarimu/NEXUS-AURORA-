# Crawler/nexora_crawler/AI_pipeline/embedding_engine.py
# UnifiedEmbeddingEngine — Phase 4B
# SINGLE SOURCE OF TRUTH for all embedding generation.
#
# Multi-provider, settings-driven. Switching models/providers = change settings.
#
#   - Non-HuggingFace providers (ollama, openai, anthropic, ...) use LiteLLM's
#     async OpenAI-compatible embedding API.
#   - provider == "huggingface" uses the HF router's LEGACY inference endpoint
#     (.../hf-inference/models/<model>/pipeline/feature-extraction) because the
#     router's OpenAI-compatible /v1/embeddings does NOT support
#     sentence-transformers models. This is the path test_ai.py proved works.

import asyncio
import functools
import logging
from typing import List, Optional

try:
    from litellm import aembedding
except ImportError:  # pragma: no cover - litellm optional for HF-only use
    aembedding = None

try:
    import requests
except ImportError:  # pragma: no cover - only needed for HF legacy path
    requests = None

logger = logging.getLogger(__name__)  # will show up in the main logger of the app


class UnifiedEmbeddingEngine:
    """
    Unified embedding generator.

    Supports:
    - ollama (local):  provider="ollama",  model="nomic-embed-text"
    - openai (cloud):  provider="openai",  model="text-embedding-3-small"
    - huggingface:     provider="huggingface",
                        model="sentence-transformers/all-MiniLM-L6-v2"
    - Any other LiteLLM-compatible provider

    The provider string is what decides HOW embeddings are generated:
      * "huggingface" -> legacy HF feature-extraction endpoint (direct HTTP)
      * everything else -> LiteLLM aembedding (OpenAI-compatible)

    Usage:
        engine = UnifiedEmbeddingEngine()  # or pass provider/model from settings
        embedding = await engine.embed("text to embed")
        embeddings = await engine.embed_batch(["text1", "text2"])
    """

    def __init__(
        self,
        provider: str = "ollama",
        model: str = "nomic-embed-text",
        base_url: str = "http://localhost:11434",
        api_key: str = "not-needed",
        timeout: int = 30,
        max_concurrent: int = 3,
    ):
        self.provider = (provider or "ollama").lower()
        self.model = model
        self.base_url = base_url
        self.api_key = api_key
        self.timeout = timeout
        self.semaphore = asyncio.Semaphore(max_concurrent)  # caps concurrent embedding requests (rate-limit / overload guard)

        # LiteLLM model string format: "provider/model" (used by non-HF paths)
        self.litellm_model = f"{provider}/{model}"

        # For the HF provider, derive the legacy feature-extraction URL from
        # the configured base_url so it stays a settings-only change.
        # base_url looks like "https://router.huggingface.co/v1".
        if self.provider == "huggingface":
            host = self.base_url.split("/v1")[0] if "/v1" in self.base_url else "https://router.huggingface.co"
            model_slug = self.model.replace("/", "%2F")
            self.hf_embed_url = (
                f"{host}/hf-inference/models/{model_slug}/pipeline/feature-extraction"
            )
        else:
            self.hf_embed_url = None

        self.stats = {
            "embeddings_generated": 0,
            "batches_processed": 0,
            "errors": 0,
        }

    async def embed(self, text: str) -> Optional[List[float]]:
        """Embed a single text string. Returns vector or None on failure."""
        if not text or len(text.strip()) < 10:
            return None

        async with self.semaphore:
            try:
                if self.provider == "huggingface":
                    embedding = await asyncio.to_thread(self._embed_hf_sync, text)
                else:
                    embedding = await self._embed_litellm(text)

                if embedding:
                    self.stats["embeddings_generated"] += 1
                return embedding
            except Exception as exc:
                logger.warning("[EmbeddingEngine] Failed for text (%d chars): %s",
                              len(text), exc)
                self.stats["errors"] += 1
                return None

    async def _embed_litellm(self, text: str) -> Optional[List[float]]:
        """OpenAI-compatible embedding via LiteLLM (ollama/openai/etc.)."""
        if aembedding is None:
            raise RuntimeError("litellm is not installed; required for non-HF providers")
        response = await aembedding(
            model=self.litellm_model,
            input=text[:8000],  # Truncate to safe limit
            api_base=self.base_url,
            api_key=self.api_key,
            timeout=self.timeout,
        )
        return response.data[0]["embedding"]

    def _embed_hf_sync(self, text: str) -> List[float]:
        """
        Synchronous HF router legacy embedding.

        Runs in a thread (see embed()) so it doesn't block the event loop.
        Mirrors test_ai.py's validated approach.
        """
        if requests is None:
            raise RuntimeError("requests is not installed; required for the huggingface provider")
        if not self.hf_embed_url:
            raise RuntimeError("HF embedding URL not configured")

        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }
        payload = {"inputs": text[:8000]}

        resp = requests.post(
            self.hf_embed_url,
            headers=headers,
            json=payload,
            timeout=self.timeout,
        )
        resp.raise_for_status()
        vec = resp.json()

        # Response can be [[float, ...]] or [float, ...] depending on the model
        if isinstance(vec, list) and len(vec) > 0 and isinstance(vec[0], list):
            vec = vec[0]

        return [float(x) for x in vec]

    async def embed_batch(self, texts: List[str]) -> List[Optional[List[float]]]:
        """Embed multiple texts concurrently."""
        if not texts:
            return []

        tasks = [self.embed(text) for text in texts]
        results = await asyncio.gather(*tasks, return_exceptions=True)
        embeddings = []
        for result in results:
            if isinstance(result, Exception):
                logger.warning("[EmbeddingEngine] Batch embedding failed: %s", result)
                embeddings.append(None)
                self.stats["errors"] += 1
            else:
                embeddings.append(result)

        self.stats["batches_processed"] += 1
        return embeddings

    def get_stats(self) -> dict:
        return dict(self.stats)

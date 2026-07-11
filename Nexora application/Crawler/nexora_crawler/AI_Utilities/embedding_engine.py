# Crawler/nexora_crawler/AI_pipeline/embedding_engine.py
# UnifiedEmbeddingEngine — Phase 4B
# SINGLE SOURCE OF TRUTH for all embedding generation.
# Uses LiteLLM for multi-provider support (Ollama, OpenAI, etc.)


import asyncio
import logging
from typing import List, Optional

from litellm import aembedding

logger = logging.getLogger(__name__) # will show up in the main logger of the app, which is configured in main.py.


class UnifiedEmbeddingEngine:
    """
    Unified embedding generator via LiteLLM.

    Supports:
    - Ollama (local): model="ollama/nomic-embed-text"
    - OpenAI (cloud): model="openai/text-embedding-3-small"
    - Any LiteLLM-compatible provider

    Usage:
        engine = UnifiedEmbeddingEngine()
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
        self.provider = provider
        self.model = model
        self.base_url = base_url
        self.api_key = api_key
        self.timeout = timeout
        self.semaphore = asyncio.Semaphore(max_concurrent) # what is the maximum number of concurrent embedding requests allowed. This helps prevent overwhelming the provider's API and manages rate limits.
        
          # LiteLLM model string format: "provider/model"
        self.litellm_model = f"{provider}/{model}"

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
                response = await aembedding(
                    model=self.litellm_model,
                    input=text[:8000],  # Truncate to safe limit
                    api_base=self.base_url,
                    api_key=self.api_key,
                    timeout=self.timeout,
                )
                embedding = response.data[0]["embedding"]
                self.stats["embeddings_generated"] += 1
                return embedding
            except Exception as exc:
                logger.warning("[EmbeddingEngine] Failed for text (%d chars): %s",
                              len(text), exc)
                self.stats["errors"] += 1
                return None

    async def embed_batch(self, texts: List[str]) -> List[Optional[List[float]]]:
        """Embed multiple texts concurrently."""
        if not texts:
            return []

        tasks = [self.embed(text) for text in texts]
        results = await asyncio.gather(*tasks, return_exceptions=True) #asynco.gather - isused to run multiple coroutines concurrently and wait for all of them to complete. The return_exceptions=True argument allows the function to return exceptions as part of the results list instead of raising them immediately.
 # *tasks - is used to unpack the list of tasks into individual arguments for asyncio.gather. This allows each task to be executed concurrently.
        embeddings = []
        for result in results:
            if isinstance(result, Exception): #filters out any exceptions that may have occurred during the embedding process. If an exception is found, it logs a warning and appends None to the embeddings list, indicating that the embedding for that particular text failed.
                logger.warning("[EmbeddingEngine] Batch embedding failed: %s", result)
                embeddings.append(None)
                self.stats["errors"] += 1
            else:
                embeddings.append(result)

        self.stats["batches_processed"] += 1
        return embeddings

    def get_stats(self) -> dict:
        return dict(self.stats)
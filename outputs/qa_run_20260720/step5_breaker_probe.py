import asyncio, sys, time
sys.path.insert(0, r"F:\DSF\stsh projects\NEXUS AURORA\Nexora application\Crawler")

from nexora_crawler.AI_Utilities.embedding_engine import UnifiedEmbeddingEngine

# Unroutable endpoint + short timeout = guaranteed failures, fast.
engine = UnifiedEmbeddingEngine(
    provider="huggingface",
    model="sentence-transformers/all-MiniLM-L6-v2",
    base_url="https://127.0.0.1:9/v1",
    api_key="dead",
    timeout=2,
    max_concurrent=2,
    failfast_threshold=3,
)

async def main():
    texts = [f"sample text number {i} padded to be long enough" for i in range(10)]
    t0 = time.perf_counter()
    out = await engine.embed_batch(texts)
    t1 = time.perf_counter()
    print(f"batch of {len(texts)} -> {sum(x is None for x in out)} None, took {t1-t0:.1f}s")
    print("breaker open:", engine._breaker_open,
          "| consecutive failures:", engine._consecutive_failures,
          "| errors counted:", engine.stats["errors"])
    t0 = time.perf_counter()
    out2 = await engine.embed_batch(texts)
    t1 = time.perf_counter()
    print(f"second batch (breaker open) took {t1-t0:.3f}s  -> all None: {all(x is None for x in out2)}")

asyncio.run(main())

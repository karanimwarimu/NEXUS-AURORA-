"""
test_vector_store.py -- Verify embeddings are actually STORED in and
RETRIEVEABLE from the configured vector backend (defaults to Chroma).

Run from the Crawler/ directory:
    python -m nexora_crawler.pipelines.test_vector_store
    # or:  python nexora_crawler/pipelines/test_vector_store.py

What it does:
  1. Builds the backend via build_vector_store() (honours NEXORA_VECTOR_BACKEND).
  2. health_check() + count()  -- proves the store is live and has records.
  3. list_all()             -- dumps a few stored records (id, content, dim).
  4. Round-trip retrieval   -- uses a STORED embedding as the query vector and
     runs search(). This proves the vectors are indexed and retrieveable with
     NO network / no HF call required.
  5. (Optional, online) Generates a fresh HF embedding for a sample query and
     searches again -- proves end-to-end embedding -> storage -> retrieval.

IMPORTANT: If the store is EMPTY, run a crawl first. The AI/Vector pipelines
must succeed (NEXORA_AI_ENABLED + NEXORA_VECTOR_INDEX_ENABLED = True) for
records to exist. A dimension mismatch (e.g. old 768-dim vectors left in
./data/chroma while using 384-dim MiniLM) will make add()/search() fail --
delete ./data/chroma to start clean after a model switch.
"""

import os
import sys
import asyncio

_HERE = os.path.dirname(os.path.abspath(__file__))
_PROJECT_ROOT = os.path.abspath(os.path.join(_HERE, "..", ".."))
if _PROJECT_ROOT not in sys.path:
    sys.path.insert(0, _PROJECT_ROOT)

import nexora_crawler.settings as settings
from nexora_crawler.vector_store.factory import build_vector_store
from nexora_crawler.vector_store.base import SearchQuery


async def main():
    backend = getattr(settings, "NEXORA_VECTOR_BACKEND", "chroma")
    print(f"=== Vector Store Verification (backend={backend}) ===")

    store = build_vector_store(backend)
    await store.initialize()

    ok = await store.health_check()
    print(f"  health_check : {ok}")
    if not ok:
        print("  [X] store not reachable -- aborting")
        return

    total = await store.count()
    print(f"  count        : {total} records")
    if total == 0:
        print("  [!] store is EMPTY -- run a crawl first so the VectorIndexPipeline indexes chunks.")
        return

    # --- Dump a few stored records ---
    sample = await store.list_all(limit=5)
    print(f"\n  --- stored records (first {len(sample)}) ---")
    for r in sample:
        emb = r.embedding
        dim = len(emb) if emb is not None else 0  # chroma returns np arrays; avoid truthiness
        print(f"   id={r.id[:36]}... source={r.source_type} dim={dim}")
        print(f"      content: {r.content[:80]!r}")
        print(f"      meta  : parent_title={r.metadata.get('parent_title')!r} "
              f"chunk={r.metadata.get('chunk_index')}/{r.metadata.get('chunk_count')}")

    # --- Round-trip: use a STORED embedding as the query (offline proof) ---
    q = sample[0]
    qvec = q.embedding
    if hasattr(qvec, "tolist"):  # chroma returns numpy arrays
        qvec = qvec.tolist()
    print(f"\n=== Round-trip search (query = stored chunk {q.id[:8]}...) ===")
    results = await store.search(SearchQuery(
        vector=qvec,
        workspace_id=q.workspace_id,
        top_k=3,
        min_similarity=0.0,
    ))
    print(f"  hits: {len(results)}")
    for hit in results:
        print(f"   score={hit.score:.4f}  id={hit.id[:36]}...  content={hit.content[:70]!r}")

    # --- Optional live query via the HF embedding engine ---
    try:
        from nexora_crawler.AI_Utilities.embedding_engine import UnifiedEmbeddingEngine
        eng = UnifiedEmbeddingEngine(
            provider=settings.NEXORA_AI_PROVIDER,
            model=settings.NEXORA_AI_EMBEDDING_MODEL,
            base_url=settings.NEXORA_AI_BASE_URL,
            api_key=settings.NEXORA_AI_API_KEY,
            timeout=settings.NEXORA_AI_TIMEOUT,
        )
        query_text = (sample[0].content or "Retrieval augmented generation")[:4000]
        print(f"\n=== Live HF query embedding + search ===")
        qvec2 = await eng.embed(query_text)
        if qvec2:
            results2 = await store.search(SearchQuery(
                vector=qvec2,
                workspace_id=q.workspace_id,
                top_k=3,
                min_similarity=0.0,
            ))
            print(f"  query dim={len(qvec2)}  hits={len(results2)}")
            for hit in results2:
                print(f"   score={hit.score:.4f}  content={hit.content[:70]!r}")
        else:
            print("  [!] embedding engine returned None (HF unreachable / misconfigured)")
    except Exception as e:
        print(f"  [skip] live query failed: {type(e).__name__}: {e}")


if __name__ == "__main__":
    asyncio.run(main())

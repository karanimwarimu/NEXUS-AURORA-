"""
Standalone runner for Phase 4A vector integration checks.
Runs without pytest to avoid conftest.py dependency issues.
"""

import os
import sys
import asyncio
from pathlib import Path

_PROJECT_ROOT = Path(__file__).resolve().parents[1] / "Nexora application"
# Need both Nexora application/ (for Extractor/, Models/, etc.) and 
# Nexora application/Crawler/ (for nexora_crawler package import)
_CRAWLER_DIR = _PROJECT_ROOT / "Crawler"
if str(_CRAWLER_DIR) not in sys.path:
    sys.path.insert(0, str(_CRAWLER_DIR))
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

PASS = 0
FAIL = 0

def check(name, condition, detail=""):
    global PASS, FAIL
    if condition:
        print(f"  [PASS] {name}")
        PASS += 1
    else:
        print(f"  [FAIL] {name}")
        if detail:
            print(f"         -> {detail}")
        FAIL += 1

# ---------------------------------------------------------------------------
# 1. Package structure
# ---------------------------------------------------------------------------
print("\n[1] Package Structure")
vector_store_dir = _PROJECT_ROOT / "Crawler" / "nexora_crawler" / "vector_store"
init_file = vector_store_dir / "__init__.py"
init_py_bad = vector_store_dir / "__init.py"

check("vector_store/__init__.py exists", init_file.exists())
check("vector_store/__init.py does NOT exist (misnamed)", not init_py_bad.exists())

# ---------------------------------------------------------------------------
# 2. Base module imports
# ---------------------------------------------------------------------------
print("\n[2] Base Module Imports")
try:
    from nexora_crawler.vector_store.base import (
        BaseVectorStore, VectorRecord, SearchQuery, SearchResult,
        VectorStoreProtocol, VectorStoreError, BackendNotFoundError,
        TenantIsolationError,
    )
    check("BaseVectorStore importable", True)
    check("VectorRecord importable", True)
    check("SearchQuery importable", True)
    check("SearchResult importable", True)
    check("VectorStoreProtocol importable", True)
    check("BackendNotFoundError importable", True)
    check("TenantIsolationError importable", True)
except Exception as exc:
    check("vector_store.base imports", False, str(exc))

# ---------------------------------------------------------------------------
# 3. Factory imports
# ---------------------------------------------------------------------------
print("\n[3] Factory Imports")
try:
    from nexora_crawler.vector_store.factory import build_vector_store
    check("build_vector_store importable", True)
    check("build_vector_store is callable", callable(build_vector_store))
except Exception as exc:
    check("vector_store.factory imports", False, str(exc))

# ---------------------------------------------------------------------------
# 4. Package __all__ exports
# ---------------------------------------------------------------------------
print("\n[4] Package Exports")
try:
    from nexora_crawler.vector_store import (
        BaseVectorStore, VectorRecord, SearchQuery, SearchResult,
        VectorStoreProtocol, VectorStoreError, BackendNotFoundError,
        build_vector_store,
    )
    check("Package __all__ exports complete", True)
except Exception as exc:
    check("Package __all__ exports", False, str(exc))

# ---------------------------------------------------------------------------
# 5. Settings integrity
# ---------------------------------------------------------------------------
print("\n[5] Settings Integrity")
try:
    import nexora_crawler.settings as settings
    check("settings module loads", True)

    check("NEXORA_VECTOR_BACKEND is str", 
          hasattr(settings, "NEXORA_VECTOR_BACKEND") and isinstance(settings.NEXORA_VECTOR_BACKEND, str),
          f"value={getattr(settings, 'NEXORA_VECTOR_BACKEND', 'MISSING')}")
    
    check("NEXORA_DATABASE_URL is str",
          hasattr(settings, "NEXORA_DATABASE_URL") and isinstance(settings.NEXORA_DATABASE_URL, str),
          f"value={getattr(settings, 'NEXORA_DATABASE_URL', 'MISSING')}")
    
    dim = getattr(settings, "NEXORA_EMBEDDING_DIM", None)
    dim_ok = isinstance(dim, int) and not isinstance(dim, tuple)
    check("NEXORA_EMBEDDING_DIM is int (not tuple)", dim_ok, f"type={type(dim).__name__}, value={dim!r}")
    
    check("NEXORA_CHROMA_PATH is str",
          hasattr(settings, "NEXORA_CHROMA_PATH") and isinstance(settings.NEXORA_CHROMA_PATH, str),
          f"value={getattr(settings, 'NEXORA_CHROMA_PATH', 'MISSING')}")

except Exception as exc:
    check("settings module loads", False, str(exc))

# ---------------------------------------------------------------------------
# 6. Items contract
# ---------------------------------------------------------------------------
print("\n[6] Items Contract")
try:
    import scrapy
    from nexora_crawler.items import NexoraPageItem
    check("NexoraPageItem importable", True)
    check("workspace_id in NexoraPageItem.fields", "workspace_id" in NexoraPageItem.fields)
    check("workspace_id is scrapy.Field", 
          isinstance(NexoraPageItem.fields.get("workspace_id"), scrapy.Field))
except Exception as exc:
    check("items imports", False, str(exc))

# ---------------------------------------------------------------------------
# 7. Schema enricher workspace_id logic
# ---------------------------------------------------------------------------
print("\n[7] Schema Enricher Integration")
try:
    from nexora_crawler.pipelines.schema_enricher import UnifiedSchemaEnricher
    
    enricher = UnifiedSchemaEnricher()
    mock_spider = type("MockSpider", (), {"workspace_id": "default"})()
    mock_crawler = type("MockCrawler", (), {"spider": mock_spider})()
    enricher.crawler = mock_crawler
    
    item = {"url": "https://example.com", "workspace_id": ""}
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    try:
        result = loop.run_until_complete(enricher.process_item(dict(item)))
        check("workspace_id default applied", result.get("workspace_id") == "default")
    finally:
        loop.close()
        asyncio.set_event_loop(None)

except Exception as exc:
    check("schema_enricher workspace_id", False, str(exc))

# ---------------------------------------------------------------------------
# 8. Factory backend map
# ---------------------------------------------------------------------------
print("\n[8] Factory Backend Map")
try:
    from nexora_crawler.vector_store.factory import build_vector_store
    from nexora_crawler.vector_store.base import BaseVectorStore, BackendNotFoundError
    
    # Test chroma (no external deps needed for import check beyond what we have)
    try:
        store = build_vector_store("chroma")
        check("chroma backend instantiates", True)
        check("chroma returns BaseVectorStore instance", isinstance(store, BaseVectorStore))
        check("chroma backend_name() returns str", isinstance(store.backend_name(), str))
    except Exception as exc:
        check("chroma backend instantiates", False, str(exc))
    
    # Test unknown backend
    try:
        build_vector_store("nonexistent_xyz")
        check("unknown backend raises BackendNotFoundError", False, "No exception raised")
    except BackendNotFoundError:
        check("unknown backend raises BackendNotFoundError", True)
    except Exception as exc:
        check("unknown backend raises BackendNotFoundError", False, f"Wrong exception: {type(exc).__name__}: {exc}")

except Exception as exc:
    check("factory backend tests", False, str(exc))

# ---------------------------------------------------------------------------
# 9. No conflicting BaseVectorStore
# ---------------------------------------------------------------------------
print("\n[9] No Conflicting BaseVectorStore Definitions")
try:
    from nexora_crawler.storage.base import BaseVectorStore as OldBase
    from nexora_crawler.vector_store.base import BaseVectorStore as NewBase
    
    check("Old BaseVectorStore has add_chunks", hasattr(OldBase, "add_chunks"))
    check("New BaseVectorStore has add", hasattr(NewBase, "add"))
    check("New BaseVectorStore has upsert", hasattr(NewBase, "upsert"))
    check("New BaseVectorStore has hybrid_search", hasattr(NewBase, "hybrid_search"))
    check("New BaseVectorStore has health_check", hasattr(NewBase, "health_check"))
    check("Old and New BaseVectorStore are different classes", OldBase is not NewBase)
except Exception as exc:
    check("BaseVectorStore conflict check", False, str(exc))

# ---------------------------------------------------------------------------
# 10. Dataclass contracts
# ---------------------------------------------------------------------------
print("\n[10] Dataclass Contracts")
try:
    from nexora_crawler.vector_store.base import VectorRecord, SearchQuery, SearchResult
    
    vr = VectorRecord(id="t1", content="hello", embedding=[0.1, 0.2])
    check("VectorRecord default workspace_id='default'", vr.workspace_id == "default")
    check("VectorRecord default source_type='chunk'", vr.source_type == "chunk")
    
    sq = SearchQuery()
    check("SearchQuery default top_k=10", sq.top_k == 10)
    check("SearchQuery default min_similarity=0.0", sq.min_similarity == 0.0)
    
    sr = SearchResult(id="r1", score=0.9, content="text", metadata={}, workspace_id="default")
    check("SearchResult has expected fields", all(hasattr(sr, f) for f in ["id", "score", "content", "metadata", "workspace_id"]))
except Exception as exc:
    check("Dataclass contracts", False, str(exc))

# ---------------------------------------------------------------------------
# Summary
# ---------------------------------------------------------------------------
print("\n" + "="*60)
print(f"RESULTS: {PASS} passed, {FAIL} failed out of {PASS+FAIL} checks")
print("="*60)

if FAIL > 0:
    print("\nACTION REQUIRED: Fix the failing checks above before proceeding to Phase 4B.")
    sys.exit(1)
else:
    print("\nAll Phase 4A vector integration checks passed.")
    sys.exit(0)

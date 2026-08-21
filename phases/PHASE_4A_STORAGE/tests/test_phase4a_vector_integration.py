"""
test_phase4a_vector_integration.py
====================================
Validates the Phase 4A vector store integration patch from:
  Project Tools/Phase 4 Documentation/phase_4a_additional_integration.md

This test suite verifies:
  1. Package structure: vector_store/ is importable as a Python package
  2. Settings integrity: NEXORA_VECTOR_* settings exist with correct types
  3. Items contract: workspace_id field exists on NexoraPageItem
  4. Pipeline integration: schema_enricher applies workspace_id defaults
  5. Factory interface: build_vector_store() loads with correct backend map
  6. No conflicting BaseVectorStore definitions between storage/base.py and vector_store/base.py
  7. Dataclass contracts: VectorRecord, SearchQuery, SearchResult have expected fields
"""

import importlib
import os
import sys
import pytest
from pathlib import Path

# Ensure Nexora application root is on path
_PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))


class TestVectorPackageStructure:
    """Verify vector_store package can be imported."""

    def test_init_file_is_valid_python_package(self):
        """__init.py is misnamed — must be __init__.py for Python package recognition."""
        vector_store_dir = _PROJECT_ROOT / "Nexora application" / "Crawler" / "nexora_crawler" / "vector_store"
        init_file = vector_store_dir / "__init__.py"
        init_py_bad = vector_store_dir / "__init.py"

        # The correct file must exist
        assert init_file.exists(), (
            f"vector_store/__init__.py is missing. Found __init.py instead. "
            f"Python cannot recognize the directory as a package without __init__.py."
        )

        # The misnamed file should NOT exist (or should be removed)
        if init_py_bad.exists():
            pytest.fail(
                f"Misnamed file found: {init_py_bad}. "
                f"Remove __init.py and keep only __init__.py"
            )

    def test_base_module_imports(self):
        """Base module exports expected classes."""
        from nexora_crawler.vector_store.base import (
            BaseVectorStore,
            VectorRecord,
            SearchQuery,
            SearchResult,
            VectorStoreProtocol,
            VectorStoreError,
            BackendNotFoundError,
            TenantIsolationError,
        )
        assert BaseVectorStore is not None
        assert VectorRecord is not None
        assert SearchQuery is not None
        assert SearchResult is not None

    def test_factory_module_imports(self):
        """Factory module exports build_vector_store."""
        from nexora_crawler.vector_store.factory import build_vector_store
        assert callable(build_vector_store)

    def test_package_all_exports(self):
        """Package __init__.py exports the full public API."""
        from nexora_crawler.vector_store import (
            BaseVectorStore,
            VectorRecord,
            SearchQuery,
            SearchResult,
            VectorStoreProtocol,
            VectorStoreError,
            BackendNotFoundError,
            build_vector_store,
        )
        assert BaseVectorStore is not None
        assert build_vector_store is not None


class TestSettingsIntegrity:
    """Verify NEXORA_VECTOR_* settings exist with correct types."""

    def test_settings_module_loads(self):
        """Settings module must load without syntax errors."""
        import nexora_crawler.settings as settings
        assert settings is not None

    def test_vector_backend_setting_exists(self):
        """NEXORA_VECTOR_BACKEND must be a string."""
        from nexora_crawler import settings
        assert hasattr(settings, "NEXORA_VECTOR_BACKEND")
        assert isinstance(settings.NEXORA_VECTOR_BACKEND, str)
        assert settings.NEXORA_VECTOR_BACKEND in ("pgvector", "chroma", "qdrant", "cloudflare_vectorize")

    def test_database_url_setting_exists(self):
        """NEXORA_DATABASE_URL must be a string."""
        from nexora_crawler import settings
        assert hasattr(settings, "NEXORA_DATABASE_URL")
        assert isinstance(settings.NEXORA_DATABASE_URL, str)

    def test_embedding_dim_is_int_not_tuple(self):
        """NEXORA_EMBEDDING_DIM must be int, not tuple from trailing comma bug."""
        from nexora_crawler import settings
        assert hasattr(settings, "NEXORA_EMBEDDING_DIM")
        dim = settings.NEXORA_EMBEDDING_DIM
        assert isinstance(dim, int), (
            f"NEXORA_EMBEDDING_DIM is {type(dim).__name__} ({dim!r}), expected int. "
            f"Check settings.py line 234 for trailing comma bug."
        )
        assert dim in (768, 1536), f"Embedding dim {dim} is not a recognized value"

    def test_chroma_path_setting_exists(self):
        """NEXORA_CHROMA_PATH must be a string."""
        from nexora_crawler import settings
        assert hasattr(settings, "NEXORA_CHROMA_PATH")
        assert isinstance(settings.NEXORA_CHROMA_PATH, str)


class TestItemsContract:
    """Verify NexoraPageItem has workspace_id field."""

    def test_workspace_id_field_exists(self):
        """workspace_id must be defined on NexoraPageItem."""
        from nexora_crawler.items import NexoraPageItem
        assert "workspace_id" in NexoraPageItem.fields, (
            "NexoraPageItem missing 'workspace_id' field. "
            "Add: workspace_id = scrapy.Field()"
        )

    def test_workspace_id_is_scrapy_field(self):
        """workspace_id must be a scrapy.Field, not a plain class attribute."""
        from nexora_crawler.items import NexoraPageItem
        import scrapy
        field = NexoraPageItem.fields.get("workspace_id")
        assert isinstance(field, scrapy.Field), (
            f"workspace_id is {type(field)}, expected scrapy.Field"
        )


class TestSchemaEnricherIntegration:
    """Verify UnifiedSchemaEnricher applies workspace_id defaults."""

    def test_workspace_id_default_applied(self):
        """Empty workspace_id should be set to 'default'."""
        from nexora_crawler.pipelines.schema_enricher import UnifiedSchemaEnricher

        enricher = UnifiedSchemaEnricher()
        enricher.crawler = type("MockCrawler", (), {"spider": type("MockSpider", (), {"workspace_id": "default"})()})()

        item = {"url": "https://example.com", "workspace_id": ""}
        result = asyncio_run(enricher.process_item(item))
        assert result.get("workspace_id") == "default"

    def test_workspace_id_preserved_if_set(self):
        """Existing workspace_id should not be overwritten."""
        from nexora_crawler.pipelines.schema_enricher import UnifiedSchemaEnricher

        enricher = UnifiedSchemaEnricher()
        enricher.crawler = type("MockCrawler", (), {"spider": type("MockSpider", (), {"workspace_id": "team-alpha"})()})()

        item = {"url": "https://example.com", "workspace_id": "team-alpha"}
        result = asyncio_run(enricher.process_item(item))
        assert result.get("workspace_id") == "team-alpha"


class TestFactoryInterface:
    """Verify build_vector_store() factory contract."""

    def test_factory_returns_base_vector_store_subclass(self):
        """Factory must return an instance of BaseVectorStore."""
        from nexora_crawler.vector_store.base import BaseVectorStore
        from nexora_crawler.vector_store.factory import build_vector_store

        # Force chroma backend to avoid needing Postgres for this test
        store = build_vector_store("chroma")
        assert isinstance(store, BaseVectorStore)

    def test_factory_backend_name_method(self):
        """Returned store must implement backend_name()."""
        from nexora_crawler.vector_store.factory import build_vector_store

        store = build_vector_store("chroma")
        name = store.backend_name()
        assert isinstance(name, str)
        assert len(name) > 0

    def test_factory_rejects_unknown_backend(self):
        """Unknown backend must raise BackendNotFoundError."""
        from nexora_crawler.vector_store.factory import build_vector_store
        from nexora_crawler.vector_store.base import BackendNotFoundError

        with pytest.raises(BackendNotFoundError):
            build_vector_store("nonexistent_backend_xyz")

    def test_factory_supported_backends(self):
        """All documented backends must be handled in factory."""
        from nexora_crawler.vector_store.factory import build_vector_store

        documented_backends = ["pgvector", "chroma", "qdrant", "cloudflare_vectorize"]
        for backend in documented_backends:
            # We just verify the factory doesn't raise BackendNotFoundError
            # Individual backends may raise ImportError for missing deps — that's acceptable
            try:
                store = build_vector_store(backend)
                assert store is not None
            except Exception as exc:
                # ImportError for missing optional deps is acceptable
                if "No module named" in str(exc) or isinstance(exc, ModuleNotFoundError):
                    continue
                raise


class TestNoConflictingBaseVectorStore:
    """Ensure single source of truth for BaseVectorStore."""

    def test_storage_base_vector_store_is_old_interface(self):
        """storage/base.py BaseVectorStore has old interface (add_chunks, search_by_text)."""
        from nexora_crawler.storage.base import BaseVectorStore as OldBase
        assert hasattr(OldBase, "add_chunks"), "storage/base.py BaseVectorStore should have old interface"
        assert hasattr(OldBase, "search_by_text"), "storage/base.py BaseVectorStore should have old interface"

    def test_vector_store_base_is_new_interface(self):
        """vector_store/base.py BaseVectorStore has new interface (add, upsert, hybrid_search)."""
        from nexora_crawler.vector_store.base import BaseVectorStore as NewBase
        assert hasattr(NewBase, "add"), "vector_store/base.py BaseVectorStore should have new 'add' method"
        assert hasattr(NewBase, "upsert"), "vector_store/base.py BaseVectorStore should have new 'upsert' method"
        assert hasattr(NewBase, "hybrid_search"), "vector_store/base.py BaseVectorStore should have new 'hybrid_search' method"
        assert hasattr(NewBase, "list_all"), "vector_store/base.py BaseVectorStore should have new 'list_all' method"
        assert hasattr(NewBase, "health_check"), "vector_store/base.py BaseVectorStore should have new 'health_check' method"

    def test_bases_are_different_classes(self):
        """The two BaseVectorStore classes must not be the same object."""
        from nexora_crawler.storage.base import BaseVectorStore as OldBase
        from nexora_crawler.vector_store.base import BaseVectorStore as NewBase
        assert OldBase is not NewBase, (
            "storage/base.py and vector_store/base.py BaseVectorStore are the same class. "
            "They must remain separate interfaces."
        )


class TestDataclassContracts:
    """Verify VectorRecord, SearchQuery, SearchResult field contracts."""

    def test_vector_record_defaults(self):
        """VectorRecord defaults: workspace_id='default', source_type='chunk'."""
        from nexora_crawler.vector_store.base import VectorRecord
        record = VectorRecord(id="test-1", content="hello", embedding=[0.1, 0.2])
        assert record.workspace_id == "default"
        assert record.source_type == "chunk"
        assert record.source_id is None
        assert record.metadata == {}

    def test_vector_record_custom_workspace(self):
        """VectorRecord accepts custom workspace_id."""
        from nexora_crawler.vector_store.base import VectorRecord
        record = VectorRecord(
            id="test-2",
            content="world",
            embedding=[0.3, 0.4],
            workspace_id="team-alpha",
            source_type="page",
            source_id="page-123",
            metadata={"url": "https://example.com"},
        )
        assert record.workspace_id == "team-alpha"
        assert record.source_type == "page"
        assert record.source_id == "page-123"
        assert record.metadata["url"] == "https://example.com"

    def test_search_query_defaults(self):
        """SearchQuery defaults: top_k=10, min_similarity=0.0."""
        from nexora_crawler.vector_store.base import SearchQuery
        query = SearchQuery()
        assert query.top_k == 10
        assert query.min_similarity == 0.0
        assert query.workspace_id is None
        assert query.filter == {}

    def test_search_result_fields(self):
        """SearchResult has id, score, content, metadata, workspace_id."""
        from nexora_crawler.vector_store.base import SearchResult
        result = SearchResult(
            id="res-1",
            score=0.95,
            content="matched text",
            metadata={"source": "web"},
            workspace_id="default",
        )
        assert result.id == "res-1"
        assert result.score == 0.95
        assert result.workspace_id == "default"


# ---------------------------------------------------------------------------
# Helper for running async pipeline methods in sync test context
# ---------------------------------------------------------------------------

def asyncio_run(coro):
    """Run an async coroutine from a sync test."""
    import asyncio
    try:
        loop = asyncio.get_running_loop()
        # If we're already in an event loop (pytest-asyncio), use it
        import concurrent.futures
        with concurrent.futures.ThreadPoolExecutor() as pool:
            future = pool.submit(asyncio.run, coro)
            return future.result()
    except RuntimeError:
        # No running loop — safe to use asyncio.run
        return asyncio.run(coro)

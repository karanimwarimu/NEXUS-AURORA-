"""
Build vector store backends from config.
Switching backends = changing one env var. Zero code change.

Usage:
    store = build_vector_store()  # uses NEXORA_VECTOR_BACKEND env var
    store = build_vector_store("chroma")  # explicit override
"""

import os
import logging
from .base import BaseVectorStore, BackendNotFoundError

logger = logging.getLogger(__name__)


def build_vector_store(backend_name: str = None) -> BaseVectorStore:
    """
    Build the configured vector store backend.

    Args:
        backend_name: Override env var. If None, reads NEXORA_VECTOR_BACKEND.

    Returns:
        Configured BaseVectorStore instance.

    Raises:
        BackendNotFoundError: If backend is unknown or dependencies missing.
    """
    backend = (backend_name or os.getenv("NEXORA_VECTOR_BACKEND", "pgvector")).lower()

    if backend == "pgvector":
        try:
            from .pgvector_store import PgVectorStore
        except ImportError:
            raise BackendNotFoundError(
                "PgVector backend not available. Install with: pip install psycopg2-binary pgvector"
            )
        return PgVectorStore(
            database_url=os.getenv("NEXORA_DATABASE_URL"),
            embedding_dim=int(os.getenv("NEXORA_EMBEDDING_DIM", "768")),
        )

    elif backend == "chroma":
        try:
            from .chroma_store import ChromaVectorStore
        except ImportError:
            raise BackendNotFoundError(
                "Chroma backend not available. Install with: pip install chromadb"
            )
        return ChromaVectorStore(
            path=os.getenv("NEXORA_CHROMA_PATH", "./data/chroma"),
        )

    elif backend == "qdrant":
        try:
            from .qdrant_store import QdrantVectorStore
        except ImportError:
            raise BackendNotFoundError(
                "Qdrant backend not available. Install with: pip install qdrant-client"
            )
        return QdrantVectorStore(
            url=os.getenv("NEXORA_QDRANT_URL"),
            api_key=os.getenv("NEXORA_QDRANT_API_KEY"),
        )

    elif backend == "cloudflare_vectorize":
        try:
            from .cloudflare_vectorize_store import CloudflareVectorizeStore
        except ImportError:
            raise BackendNotFoundError(
                "Cloudflare Vectorize backend not available. Install with: pip install httpx"
            )
        return CloudflareVectorizeStore(
            account_id=os.getenv("CF_ACCOUNT_ID"),
            api_token=os.getenv("CF_API_TOKEN"),
            index_name=os.getenv("CF_VECTORIZE_INDEX", "nexora-prod"),
        )

    raise BackendNotFoundError(f"Unknown vector backend: {backend}")

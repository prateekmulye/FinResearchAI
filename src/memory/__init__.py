# src/memory package — warehouse-backed verdict cache (WP-2) + local embeddings.
# The embedded-Chroma VectorStore was removed; the cache API below is the public
# surface (src.memory.embeddings powers WP-9 pgvector semantic search).
from src.memory.cache import get_cached_verdict, store_verdict

__all__ = ["get_cached_verdict", "store_verdict"]

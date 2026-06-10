# src/warehouse/embeddings.py
"""Warehouse-side embedding seam (WP-9): degrade-always access to the fastembed
BGE-small embedder for the pgvector write path and /api/search.

Why a separate seam instead of calling ``src.memory.embeddings.get_embedder()``
directly:

- **Degrade, never raise.** The ingest layer's never-raise contract extends to
  embeddings: a missing/broken fastembed install must mean "rows land without
  embeddings", not "news ingest fails". ``get_warehouse_embedder`` resolves the
  backend lazily, caches the outcome (including failure -> ``None``), and warns
  exactly once — unlike ``get_embedder``, whose ``lru_cache`` re-attempts the
  slow model load on every call after a failure.
- **Offline-test injectability.** Constructing the real embedder downloads an
  ONNX model on first use, so offline tests must never reach it. The module
  global is the injection point: ``set_embedder_for_testing(fake_or_none)``
  pins it, ``reset_embedder()`` restores lazy resolution (the autouse conftest
  fixture pins ``None`` for every test).

``embed_or_none`` is synchronous CPU work — call it via ``asyncio.to_thread``
from async code, and always OUTSIDE any DB session (model inference is slow;
same fetch-outside-session rule as ``ingest.refresh_prices``).
"""
from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:  # import-light: fastembed must not load at module import time
    from src.memory.embeddings import Embedder

_LOG = logging.getLogger(__name__)

# Tri-state module global: _UNRESOLVED -> not attempted yet; None -> unavailable
# (cached, warned once); anything else -> the resolved/injected Embedder.
_UNRESOLVED: Any = object()
_embedder: Any = _UNRESOLVED


def set_embedder_for_testing(embedder: "Embedder | None") -> None:
    """Pin the seam to a fake Embedder (or None = embeddings unavailable)."""
    global _embedder
    _embedder = embedder


def reset_embedder() -> None:
    """Forget any injected/cached embedder; next access resolves lazily again."""
    global _embedder
    _embedder = _UNRESOLVED


def get_warehouse_embedder() -> "Embedder | None":
    """Lazy cached embedder; ``None`` (warning once) when fastembed is unusable."""
    global _embedder
    if _embedder is _UNRESOLVED:
        try:
            from src.memory.embeddings import get_embedder

            _embedder = get_embedder()
        except Exception as exc:
            _LOG.warning(
                "warehouse embeddings unavailable (semantic search/index degraded "
                "to keyword/none): %s", exc,
            )
            _embedder = None
    return _embedder


def embed_or_none(texts: list[str]) -> list[list[float]] | None:
    """Embed ``texts`` or return ``None`` (no embedder, empty input, or failure).

    Never raises — embedding failure degrades to "store rows without vectors".
    """
    if not texts:
        return None
    embedder = get_warehouse_embedder()
    if embedder is None:
        return None
    try:
        return embedder.embed(texts)
    except Exception as exc:
        _LOG.warning("warehouse embedding failed for %d text(s): %s", len(texts), exc)
        return None

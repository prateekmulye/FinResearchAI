# src/memory/embeddings.py
"""Local, key-free text embeddings (fastembed / BGE-small) behind a swap seam.

The vector backend is isolated here so it can be swapped later (e.g. an
Ollama Cloud /v1/embeddings client) without touching store.py or cache.py.
"""
from __future__ import annotations

from functools import lru_cache
from typing import Protocol, runtime_checkable

from fastembed import TextEmbedding

from src.config.settings import get_settings

# BAAI/bge-small-en-v1.5 produces 384-dimensional vectors (verified via Context7).
BGE_SMALL_DIM = 384


@runtime_checkable
class Embedder(Protocol):
    """Swap seam: any backend providing these two methods is a valid embedder."""

    def embed(self, texts: list[str]) -> list[list[float]]: ...

    def embed_one(self, text: str) -> list[float]: ...


class FastEmbedEmbedder:
    """Default embedder: local fastembed TextEmbedding (CPU, no API key)."""

    def __init__(self, model_name: str | None = None) -> None:
        self.model_name = model_name or get_settings().embedding_model
        # Constructing TextEmbedding downloads the ONNX model on first use,
        # then runs fully offline. Deterministic for a given input + model.
        self._model = TextEmbedding(model_name=self.model_name)

    def embed(self, texts: list[str]) -> list[list[float]]:
        # .embed() returns a generator of numpy float32 arrays; convert to
        # plain python float lists for Chroma compatibility + JSON safety.
        return [vec.tolist() for vec in self._model.embed(texts)]

    def embed_one(self, text: str) -> list[float]:
        return self.embed([text])[0]


@lru_cache(maxsize=1)
def get_embedder() -> Embedder:
    """Cached default embedder. NOTE: lru_cache does NOT cache exceptions —
    a failed model load re-attempts on every call. Catch RuntimeError at startup.

    Swap seam: change this to return a different Embedder implementation
    (e.g. an Ollama Cloud embeddings client) to switch backends; callers depend
    only on the Embedder protocol.
    """
    try:
        return FastEmbedEmbedder()
    except Exception as exc:
        raise RuntimeError(
            f"FastEmbed model load failed ({exc}). Check the ONNX model cache "
            "or inject a custom embedder via store construction."
        ) from exc

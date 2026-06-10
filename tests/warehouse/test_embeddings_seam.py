# tests/warehouse/test_embeddings_seam.py
"""WP-9 warehouse-side embedding seam: lazy singleton over src.memory.embeddings,
degrade-to-None on unavailability, warn-once, and the test injection hooks.

These tests NEVER construct a real fastembed model (the conftest autouse
``no_real_embedder`` fixture pins the seam to None; tests inject fakes or
monkeypatch the underlying factory).
"""
from __future__ import annotations

import logging

import src.memory.embeddings as memory_embeddings
from src.warehouse.embeddings import (
    embed_or_none,
    get_warehouse_embedder,
    reset_embedder,
    set_embedder_for_testing,
)


class _FakeEmbedder:
    def __init__(self):
        self.calls: list[list[str]] = []

    def embed(self, texts):
        self.calls.append(list(texts))
        return [[float(len(t))] * 384 for t in texts]

    def embed_one(self, text):
        return self.embed([text])[0]


class _BoomEmbedder:
    def embed(self, texts):
        raise RuntimeError("onnx exploded")

    def embed_one(self, text):
        raise RuntimeError("onnx exploded")


# ------------------------------------------------------------------ injection


def test_injected_embedder_is_returned():
    fake = _FakeEmbedder()
    set_embedder_for_testing(fake)
    assert get_warehouse_embedder() is fake


def test_injected_none_disables_embeddings():
    set_embedder_for_testing(None)
    assert get_warehouse_embedder() is None
    assert embed_or_none(["a"]) is None


def test_reset_embedder_restores_lazy_resolution(monkeypatch):
    sentinel = _FakeEmbedder()
    monkeypatch.setattr(memory_embeddings, "get_embedder", lambda: sentinel)
    set_embedder_for_testing(_FakeEmbedder())
    reset_embedder()
    # After reset, resolution goes back through src.memory.embeddings.get_embedder.
    assert get_warehouse_embedder() is sentinel


# ------------------------------------------------------- lazy init + degrade


def test_init_failure_degrades_to_none_and_warns_once(monkeypatch, caplog):
    def _boom():
        raise RuntimeError("fastembed unavailable")

    monkeypatch.setattr(memory_embeddings, "get_embedder", _boom)
    reset_embedder()
    with caplog.at_level(logging.WARNING, logger="src.warehouse.embeddings"):
        assert get_warehouse_embedder() is None
        assert get_warehouse_embedder() is None  # cached: no re-attempt
    warnings = [r for r in caplog.records if "embed" in r.message.lower()]
    assert len(warnings) == 1, "unavailability must be logged exactly once"


def test_init_success_is_cached_singleton(monkeypatch):
    calls = []

    def _factory():
        calls.append(1)
        return _FakeEmbedder()

    monkeypatch.setattr(memory_embeddings, "get_embedder", _factory)
    reset_embedder()
    first = get_warehouse_embedder()
    second = get_warehouse_embedder()
    assert first is second
    assert len(calls) == 1


# --------------------------------------------------------------- embed_or_none


def test_embed_or_none_returns_vectors_via_embedder():
    fake = _FakeEmbedder()
    set_embedder_for_testing(fake)
    vecs = embed_or_none(["alpha", "bb"])
    assert vecs == [[5.0] * 384, [2.0] * 384]
    assert fake.calls == [["alpha", "bb"]]


def test_embed_or_none_degrades_when_embedder_raises(caplog):
    set_embedder_for_testing(_BoomEmbedder())
    with caplog.at_level(logging.WARNING, logger="src.warehouse.embeddings"):
        assert embed_or_none(["a"]) is None
    assert any("embed" in r.message.lower() for r in caplog.records)


def test_embed_or_none_empty_texts_is_none():
    set_embedder_for_testing(_FakeEmbedder())
    assert embed_or_none([]) is None

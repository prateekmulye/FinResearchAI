# tests/test_embeddings.py
from src.memory.embeddings import (
    Embedder,
    FastEmbedEmbedder,
    get_embedder,
    BGE_SMALL_DIM,
)


def test_bge_small_dim_constant_is_384():
    assert BGE_SMALL_DIM == 384


def test_embed_returns_fixed_dim_vectors():
    emb = FastEmbedEmbedder()
    vectors = emb.embed(["hello world", "second document"])
    assert isinstance(vectors, list)
    assert len(vectors) == 2
    assert all(len(v) == BGE_SMALL_DIM for v in vectors)
    assert all(isinstance(x, float) for x in vectors[0])  # plain python floats, not numpy


def test_embed_is_deterministic_for_same_input():
    emb = FastEmbedEmbedder()
    a = emb.embed(["deterministic text"])[0]
    b = emb.embed(["deterministic text"])[0]
    assert a == b


def test_embed_one_is_single_vector():
    emb = FastEmbedEmbedder()
    v = emb.embed_one("just one")
    assert len(v) == BGE_SMALL_DIM


def test_get_embedder_returns_embedder_protocol_impl():
    emb = get_embedder()
    assert isinstance(emb, Embedder)  # runtime-checkable protocol


def test_get_embedder_is_cached_singleton():
    assert get_embedder() is get_embedder()


def test_swap_seam_accepts_injected_backend():
    class FakeEmbedder:
        def embed(self, texts):
            return [[0.0, 1.0, 2.0] for _ in texts]

        def embed_one(self, text):
            return [0.0, 1.0, 2.0]

    fake = FakeEmbedder()
    assert isinstance(fake, Embedder)  # structural match satisfies the protocol
    assert fake.embed(["a", "b"]) == [[0.0, 1.0, 2.0], [0.0, 1.0, 2.0]]

# tests/test_cache.py
import json

from src.llm.schemas import FinalDecision
from src.memory import cache as cache_mod
from src.memory.cache import get_cached_verdict, store_verdict


class FakeEmbedder:
    def embed(self, texts):
        return [[1.0, 2.0, 3.0] for _ in texts]

    def embed_one(self, text):
        return [1.0, 2.0, 3.0]


class FakeStore:
    """In-memory stand-in for VectorStore that records calls.

    `query_by` ONLY honors a metadata `where` filter — it has no similarity
    path at all, which is what we assert the cache relies on.
    """

    def __init__(self):
        self.rows = []
        self.query_calls = []
        self.add_calls = []

    def add(self, doc, metadata):
        self.add_calls.append((doc, metadata))
        self.rows.append({"id": str(len(self.rows)), "document": doc, "metadata": metadata})
        return self.rows[-1]["id"]

    def query_by(self, where):
        self.query_calls.append(where)
        return [r for r in self.rows if all(r["metadata"].get(k) == v for k, v in where.items())]


def _decision(action="BUY", score=70):
    return FinalDecision(action=action, conviction=0.8, score=score, rationale="r")


def test_store_then_fresh_hit():
    store = FakeStore()
    store_verdict("AAPL", _decision(), store=store, now=1000)
    got = get_cached_verdict("AAPL", max_age_min=60, store=store, now=1000 + 30 * 60)  # 30 min old
    assert got is not None
    assert isinstance(got, FinalDecision)
    assert got.action == "BUY"
    assert got.score == 70


def test_stale_miss():
    store = FakeStore()
    store_verdict("AAPL", _decision(), store=store, now=1000)
    got = get_cached_verdict("AAPL", max_age_min=60, store=store, now=1000 + 61 * 60)  # 61 min old
    assert got is None


def test_empty_miss():
    store = FakeStore()
    assert get_cached_verdict("AAPL", max_age_min=60, store=store, now=1000) is None


def test_picks_newest_by_ts():
    store = FakeStore()
    store_verdict("AAPL", _decision(action="SELL", score=10), store=store, now=1000)
    store_verdict("AAPL", _decision(action="BUY", score=90), store=store, now=2000)  # newer
    got = get_cached_verdict("AAPL", max_age_min=1000, store=store, now=2000)
    assert got.action == "BUY"
    assert got.score == 90


def test_store_writes_ticker_and_ts_metadata():
    store = FakeStore()
    store_verdict("TSLA", _decision(), store=store, now=4242)
    doc, meta = store.add_calls[0]
    assert meta["ticker"] == "TSLA"
    assert meta["ts"] == 4242
    assert json.loads(doc)["action"] == "BUY"  # verdict serialized as JSON document


def test_freshness_uses_metadata_where_not_similarity():
    """Regression guard for the old defect: recency must be a metadata `where`
    query keyed by ticker, NOT a semantic similarity search."""
    store = FakeStore()
    store_verdict("AAPL", _decision(), store=store, now=1000)
    get_cached_verdict("AAPL", max_age_min=60, store=store, now=1000)
    assert store.query_calls == [{"ticker": "AAPL"}]
    # FakeStore has no query_texts/similarity method — the cache cannot have used one.
    assert not hasattr(store, "query")


def test_default_store_is_constructed_lazily(monkeypatch):
    """When no store is injected, the cache builds a VectorStore on demand."""
    built = {}

    class SpyStore(FakeStore):
        def __init__(self):
            super().__init__()
            built["yes"] = True

    monkeypatch.setattr(cache_mod, "VectorStore", SpyStore)
    store_verdict("NVDA", _decision(), now=7)  # no store= kwarg
    assert built.get("yes") is True


def test_cache_end_to_end_against_real_chroma(tmp_path):
    from src.memory.store import VectorStore

    store = VectorStore(persist_dir=str(tmp_path), collection="verdicts", embedder=FakeEmbedder())
    store_verdict("AAPL", _decision(action="HOLD", score=55), store=store, now=10_000)

    fresh = get_cached_verdict("AAPL", max_age_min=60, store=store, now=10_000 + 10 * 60)
    assert fresh is not None and fresh.action == "HOLD" and fresh.score == 55

    stale = get_cached_verdict("AAPL", max_age_min=5, store=store, now=10_000 + 10 * 60)
    assert stale is None

    missing = get_cached_verdict("ZZZZ", max_age_min=60, store=store, now=10_000)
    assert missing is None

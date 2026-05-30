# tests/test_store.py
from src.memory.store import VectorStore


class FakeEmbedder:
    """Deterministic stub embedder — avoids the fastembed model download in unit tests."""

    def embed(self, texts):
        return [[float(len(t)), 1.0, 2.0] for t in texts]

    def embed_one(self, text):
        return [float(len(text)), 1.0, 2.0]


def _store(tmp_path):
    return VectorStore(persist_dir=str(tmp_path), collection="verdicts", embedder=FakeEmbedder())


def test_add_then_query_by_metadata(tmp_path):
    s = _store(tmp_path)
    s.add(doc="hello", metadata={"ticker": "AAPL", "ts": 100})
    rows = s.query_by({"ticker": "AAPL"})
    assert len(rows) == 1
    assert rows[0]["document"] == "hello"
    assert rows[0]["metadata"]["ticker"] == "AAPL"
    assert rows[0]["metadata"]["ts"] == 100


def test_query_by_filters_out_other_tickers(tmp_path):
    s = _store(tmp_path)
    s.add(doc="a", metadata={"ticker": "AAPL", "ts": 1})
    s.add(doc="t", metadata={"ticker": "TSLA", "ts": 2})
    rows = s.query_by({"ticker": "TSLA"})
    assert len(rows) == 1
    assert rows[0]["document"] == "t"


def test_query_by_empty_when_no_match(tmp_path):
    s = _store(tmp_path)
    s.add(doc="a", metadata={"ticker": "AAPL", "ts": 1})
    assert s.query_by({"ticker": "NVDA"}) == []


def test_add_generates_unique_ids(tmp_path):
    s = _store(tmp_path)
    s.add(doc="a", metadata={"ticker": "AAPL", "ts": 1})
    s.add(doc="b", metadata={"ticker": "AAPL", "ts": 2})  # must NOT collide / overwrite
    rows = s.query_by({"ticker": "AAPL"})
    assert len(rows) == 2


def test_persistence_across_instances(tmp_path):
    s1 = _store(tmp_path)
    s1.add(doc="persisted", metadata={"ticker": "AAPL", "ts": 5})
    s2 = _store(tmp_path)  # new client, same dir + collection
    rows = s2.query_by({"ticker": "AAPL"})
    assert len(rows) == 1
    assert rows[0]["document"] == "persisted"

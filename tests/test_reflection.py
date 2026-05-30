# tests/test_reflection.py
# STRETCH (optional): reflection log — verdict + realized forward return
from src.llm.schemas import FinalDecision
from src.memory.reflection import log_outcome, get_prior_outcomes


class FakeStore:
    def __init__(self):
        self.rows = []

    def add(self, doc, metadata):
        self.rows.append({"id": str(len(self.rows)), "document": doc, "metadata": metadata})
        return self.rows[-1]["id"]

    def query_by(self, where):
        return [r for r in self.rows if all(r["metadata"].get(k) == v for k, v in where.items())]


def _decision():
    return FinalDecision(action="BUY", conviction=0.7, score=65, rationale="r")


def test_log_and_retrieve_outcome():
    store = FakeStore()
    log_outcome("AAPL", _decision(), forward_return=0.05, store=store, now=100)
    outcomes = get_prior_outcomes("AAPL", store=store)
    assert len(outcomes) == 1
    assert outcomes[0]["forward_return"] == 0.05
    assert outcomes[0]["decision"].action == "BUY"
    assert outcomes[0]["ts"] == 100


def test_outcomes_sorted_newest_first():
    store = FakeStore()
    log_outcome("AAPL", _decision(), forward_return=0.01, store=store, now=100)
    log_outcome("AAPL", _decision(), forward_return=0.09, store=store, now=300)
    outcomes = get_prior_outcomes("AAPL", store=store)
    assert [o["ts"] for o in outcomes] == [300, 100]


def test_outcomes_filtered_by_ticker():
    store = FakeStore()
    log_outcome("AAPL", _decision(), forward_return=0.01, store=store, now=100)
    log_outcome("TSLA", _decision(), forward_return=0.02, store=store, now=200)
    assert len(get_prior_outcomes("TSLA", store=store)) == 1

import asyncio

import pytest

from src.eval import harness as harness_mod
from src.eval.harness import PairedResult, run_ab


class _FakeGraph:
    """Stands in for a compiled LangGraph: .ainvoke returns a canned final state."""

    def __init__(self, final_state):
        self._final_state = final_state

    async def ainvoke(self, input_state):
        # echo the ticker through so we can assert pairing is per-ticker
        out = dict(self._final_state)
        out["resolved_ticker"] = input_state["ticker"]
        return out


def _state(action, score, cost, latency):
    return {
        "final_decision": {"action": action, "conviction": 0.6, "score": score, "rationale": "x"},
        "run_metrics": [
            {"node": "n", "prompt_tokens": 10, "completion_tokens": 5,
             "latency_s": latency, "cost_usd": cost},
        ],
    }


def _make_build_graph():
    """Return a build_graph(mode) that hands back distinct on/off canned graphs."""
    def build_graph(debate_mode=None):
        if debate_mode == "on":
            return _FakeGraph(_state("BUY", 80, 0.06, 4.0))
        if debate_mode == "off":
            return _FakeGraph(_state("HOLD", 55, 0.02, 1.5))
        raise AssertionError(f"unexpected debate_mode {debate_mode!r}")
    return build_graph


@pytest.mark.asyncio
async def test_run_ab_pairs_on_and_off_per_ticker(monkeypatch):
    monkeypatch.setattr(harness_mod, "build_graph", _make_build_graph())
    results = await run_ab(["AAPL", "MSFT"], concurrency=2)

    assert len(results) == 2
    assert all(isinstance(r, PairedResult) for r in results)
    by_ticker = {r.ticker: r for r in results}

    aapl = by_ticker["AAPL"]
    assert aapl.decision_on["action"] == "BUY"
    assert aapl.decision_off["action"] == "HOLD"
    assert aapl.score_on == 80
    assert aapl.score_off == 55
    # cost/latency totals summed across run_metrics
    assert aapl.cost_on == pytest.approx(0.06)
    assert aapl.cost_off == pytest.approx(0.02)
    assert aapl.latency_on == pytest.approx(4.0)
    assert aapl.latency_off == pytest.approx(1.5)


@pytest.mark.asyncio
async def test_run_ab_preserves_input_order(monkeypatch):
    monkeypatch.setattr(harness_mod, "build_graph", _make_build_graph())
    results = await run_ab(["AAPL", "MSFT", "GOOG"], concurrency=1)
    assert [r.ticker for r in results] == ["AAPL", "MSFT", "GOOG"]


@pytest.mark.asyncio
async def test_run_ab_drops_failed_ticker_keeps_rest(monkeypatch):
    """A ticker whose graph raises is logged + dropped; completed pairs survive."""
    good = _make_build_graph()

    def build_graph(debate_mode=None):
        inner = good(debate_mode)
        orig = inner.ainvoke

        async def ainvoke(input_state):
            if input_state["ticker"] == "BAD":
                raise RuntimeError("graph blew up")
            return await orig(input_state)

        inner.ainvoke = ainvoke
        return inner

    monkeypatch.setattr(harness_mod, "build_graph", build_graph)
    results = await run_ab(["AAPL", "BAD", "MSFT"], concurrency=3)
    # BAD is dropped; AAPL + MSFT survive in input order.
    assert [r.ticker for r in results] == ["AAPL", "MSFT"]


@pytest.mark.asyncio
async def test_run_ab_bounds_concurrency(monkeypatch):
    """Semaphore must cap simultaneous in-flight pairs at `concurrency`."""
    live = 0
    peak = 0

    class _SlowGraph:
        async def ainvoke(self, input_state):
            nonlocal live, peak
            live += 1
            peak = max(peak, live)
            await asyncio.sleep(0.01)
            live -= 1
            return _state("HOLD", 50, 0.0, 0.0)

    def build_graph(debate_mode=None):
        return _SlowGraph()

    monkeypatch.setattr(harness_mod, "build_graph", build_graph)
    await run_ab(["A", "B", "C", "D"], concurrency=2)
    # 2 tickers * 2 graphs each, but the per-ticker semaphore caps to 2 pairs;
    # each pair runs its two graphs concurrently => peak in-flight ainvoke <= 4,
    # and crucially never all 8 at once.
    assert peak <= 4

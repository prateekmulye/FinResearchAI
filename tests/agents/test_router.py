import pytest

from src.agents import router as router_mod
from src.agents.router import TickerResolution, router
from src.llm.schemas import FinalDecision


class _FakeStructured:
    def __init__(self, result):
        self._result = result

    async def ainvoke(self, messages, config=None):
        return self._result


class _FakeLLM:
    def __init__(self, result):
        self._result = result

    def with_structured_output(self, schema, method=None):
        assert method in {"function_calling", "json_schema"}
        return _FakeStructured(self._result)


@pytest.fixture
def patch_llm(monkeypatch):
    def _install(resolution: TickerResolution):
        monkeypatch.setattr(router_mod, "get_llm", lambda tier: _FakeLLM(resolution))

    return _install


async def test_router_resolves_and_plans(patch_llm, monkeypatch):
    # ensure no cache module short-circuits
    monkeypatch.setattr(router_mod, "_get_cached_verdict", lambda *a, **k: None)
    patch_llm(TickerResolution(resolved_ticker="RELIANCE.NS", screener="india", exchange="NSE"))
    out = await router({"ticker": "RELIANCE", "investor_mode": "Neutral"})
    assert out["resolved_ticker"] == "RELIANCE.NS"
    assert out["screener"] == "india"
    assert out["exchange"] == "NSE"
    assert out["model_plan"]["analysts"] == "quick"
    assert out["model_plan"]["debate"] == "deep"
    assert isinstance(out["run_metrics"], list)
    assert out["run_metrics"][0]["node"] == "router"


async def test_router_us_ticker(patch_llm, monkeypatch):
    monkeypatch.setattr(router_mod, "_get_cached_verdict", lambda *a, **k: None)
    patch_llm(TickerResolution(resolved_ticker="AAPL", screener="america", exchange="NASDAQ"))
    out = await router({"ticker": "AAPL", "investor_mode": "Bullish"})
    assert out["resolved_ticker"] == "AAPL"
    assert out["exchange"] == "NASDAQ"


def test_ticker_resolution_schema_defaults():
    r = TickerResolution(resolved_ticker="MSFT")
    assert r.screener == "america"
    assert r.exchange == "NASDAQ"


async def test_router_cache_short_circuits(patch_llm, monkeypatch):
    patch_llm(TickerResolution(resolved_ticker="AAPL", screener="america", exchange="NASDAQ"))
    cached = FinalDecision(action="BUY", conviction=0.7, score=72, rationale="cached")
    monkeypatch.setattr(router_mod, "_get_cached_verdict", lambda ticker, max_age_min: cached)
    out = await router({"ticker": "AAPL", "investor_mode": "Neutral"})
    assert out["final_decision"]["action"] == "BUY"
    assert out["final_decision"]["score"] == 72
    assert out["model_plan"]["cache_hit"] is True

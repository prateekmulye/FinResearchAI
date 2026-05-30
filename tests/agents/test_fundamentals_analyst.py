
from src.agents.analysts import fundamentals as fund_mod
from src.agents.analysts.fundamentals import fundamentals_analyst
from src.llm.schemas import AnalystReport
from src.tools import ToolError
from src.tools.yfinance import Fundamentals


class _FakeStructured:
    def __init__(self, result):
        self._result = result

    async def ainvoke(self, messages, config=None):
        return self._result


class _FakeLLM:
    def __init__(self, result):
        self._result = result

    def with_structured_output(self, schema, method=None):
        return _FakeStructured(self._result)


def _fund():
    return Fundamentals(
        ticker="AAPL", name="Apple Inc.", sector="Technology", trailing_pe=28.0,
        forward_pe=25.0, earnings_growth=0.1, revenue_growth=0.05, dividend_yield=0.0056,
        payout_ratio=0.15, profit_margins=0.25, gross_margins=0.44,
        market_cap=2.7e12, beta=1.2,
    )


async def test_fundamentals_analyst_happy_path(monkeypatch):
    monkeypatch.setattr(fund_mod, "fetch_fundamentals", lambda t: _fund())
    report = AnalystReport(summary="Healthy margins", key_points=["P/E 28"], confidence=0.65)
    monkeypatch.setattr(fund_mod, "get_llm", lambda tier: _FakeLLM(report))
    out = await fundamentals_analyst({"resolved_ticker": "AAPL"})
    rep = out["analyst_reports"]["fundamentals"]
    assert rep["summary"] == "Healthy margins"
    assert rep["data"]["trailing_pe"] == 28.0  # raw numbers attached for the reporter
    assert out["run_metrics"][0]["node"] == "fundamentals_analyst"


async def test_fundamentals_analyst_tool_failure_degrades(monkeypatch):
    def _boom(t):
        raise ToolError("yfinance", "no fundamentals")

    def _llm_must_not_be_called(tier):
        raise AssertionError("llm called")

    monkeypatch.setattr(fund_mod, "fetch_fundamentals", _boom)
    monkeypatch.setattr(fund_mod, "get_llm", _llm_must_not_be_called)
    out = await fundamentals_analyst({"resolved_ticker": "BAD"})
    assert out["analyst_reports"]["fundamentals"]["confidence"] == 0.0


async def test_fundamentals_analyst_llm_failure_degrades(monkeypatch):
    """If ainvoke raises (e.g. ConnectionError), node must degrade rather than crash."""
    monkeypatch.setattr(fund_mod, "fetch_fundamentals", lambda t: _fund())

    class _FailingStructured:
        async def ainvoke(self, messages, config=None):
            raise ConnectionError("LLM unreachable")

    class _FailingLLM:
        def with_structured_output(self, schema, method=None):
            return _FailingStructured()

    monkeypatch.setattr(fund_mod, "get_llm", lambda tier: _FailingLLM())
    out = await fundamentals_analyst({"resolved_ticker": "AAPL"})
    rep = out["analyst_reports"]["fundamentals"]
    assert rep["confidence"] == 0.0
    assert "Fundamentals unavailable:" in rep["summary"]
    assert "LLM error" in rep["summary"]
    assert out["run_metrics"][0]["node"] == "fundamentals_analyst"

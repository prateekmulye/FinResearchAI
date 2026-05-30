
from src.agents.analysts import technicals as tech_mod
from src.agents.analysts.technicals import technicals_analyst
from src.llm.schemas import AnalystReport
from src.tools import ToolError
from src.tools.tradingview import Technicals


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


def _tech():
    return Technicals(
        ticker="AAPL", exchange="NASDAQ", recommendation="BUY", buy_signals=12,
        neutral_signals=9, sell_signals=7, rsi=55.2, macd=2.4, macd_signal=1.9, close=170.0,
    )


async def test_technicals_analyst_happy_path(monkeypatch):
    monkeypatch.setattr(tech_mod, "fetch_technicals", lambda t, screener, exchange: _tech())
    report = AnalystReport(summary="Bullish momentum", key_points=["RSI 55"], confidence=0.6)
    monkeypatch.setattr(tech_mod, "get_llm", lambda tier: _FakeLLM(report))
    out = await technicals_analyst({"resolved_ticker": "AAPL", "screener": "america", "exchange": "NASDAQ"})
    rep = out["analyst_reports"]["technicals"]
    assert rep["summary"] == "Bullish momentum"
    assert rep["data"]["recommendation"] == "BUY"
    assert out["run_metrics"][0]["node"] == "technicals_analyst"


async def test_technicals_analyst_tool_failure_degrades(monkeypatch):
    def _boom(t, screener, exchange):
        raise ToolError("tradingview", "all exchanges failed")

    def _llm_must_not_be_called(tier):
        raise AssertionError("llm called")

    monkeypatch.setattr(tech_mod, "fetch_technicals", _boom)
    monkeypatch.setattr(tech_mod, "get_llm", _llm_must_not_be_called)
    out = await technicals_analyst({"resolved_ticker": "AAPL", "screener": "america", "exchange": "NASDAQ"})
    assert out["analyst_reports"]["technicals"]["confidence"] == 0.0


async def test_technicals_analyst_llm_failure_degrades(monkeypatch):
    """If ainvoke raises (e.g. ConnectionError), node must degrade rather than crash."""
    monkeypatch.setattr(tech_mod, "fetch_technicals", lambda t, screener, exchange: _tech())

    class _FailingStructured:
        async def ainvoke(self, messages, config=None):
            raise ConnectionError("LLM unreachable")

    class _FailingLLM:
        def with_structured_output(self, schema, method=None):
            return _FailingStructured()

    monkeypatch.setattr(tech_mod, "get_llm", lambda tier: _FailingLLM())
    out = await technicals_analyst({"resolved_ticker": "AAPL", "screener": "america", "exchange": "NASDAQ"})
    rep = out["analyst_reports"]["technicals"]
    assert rep["confidence"] == 0.0
    assert "Technicals unavailable:" in rep["summary"]
    assert "LLM error" in rep["summary"]
    assert out["run_metrics"][0]["node"] == "technicals_analyst"

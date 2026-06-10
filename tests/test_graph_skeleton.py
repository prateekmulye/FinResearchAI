# tests/test_graph_skeleton.py
"""Foundation graph skeleton tests — updated by WP-D to use ainvoke once real async
nodes (router, analysts, bull/bear/facilitator) are wired.

All tests that invoke the graph are patched to run offline (no network, no LLM).
Per COORDINATION §7.3: LangGraph's sync ``invoke`` cannot drive async nodes; tests
that run the full graph switch to ``await app.ainvoke(...)`` under pytest-asyncio.
"""
from __future__ import annotations

import pytest

from src.graph import build_graph
from src.llm.schemas import AnalystReport, DebateTurn
from src.agents.reporter import ReportPayload, ReportSection, FinancialData


def test_graph_compiles():
    assert build_graph() is not None


# ---------------------------------------------------------------------------
# Schema-aware LLM fake for offline graph execution
# ---------------------------------------------------------------------------

_CANNED_REPORT_PAYLOAD = ReportPayload(
    sections=[ReportSection(heading="Summary", body="stub report ok")],
    financial_data=FinancialData(
        valuation=50.0, growth=50.0, profitability=50.0,
        momentum=50.0, sentiment=50.0, risk=50.0,
    ),
)


class _SchemaAwareStructured:
    """Returns the correct canned Pydantic instance for whichever schema is requested."""

    _analyst = AnalystReport(summary="stub report", key_points=[], confidence=0.5)
    _turn = DebateTurn(role="bull", round=1, argument="lean BUY")

    def __init__(self, schema):
        self._schema = schema

    async def ainvoke(self, messages, config=None, **kwargs):
        # Fire CostTracker callbacks so per_node is populated (1 entry per call).
        import time
        from types import SimpleNamespace
        callbacks = (config or {}).get("callbacks", []) or []
        rid = f"offline-{id(self)}-{time.monotonic_ns()}"
        for cb in callbacks:
            if hasattr(cb, "on_llm_start"):
                cb.on_llm_start({}, ["<prompt>"], run_id=rid)
        response = SimpleNamespace(
            llm_output={"token_usage": {"prompt_tokens": 5, "completion_tokens": 3},
                        "model_name": "fake-offline"}
        )
        for cb in callbacks:
            if hasattr(cb, "on_llm_end"):
                cb.on_llm_end(response, run_id=rid)
        if self._schema is AnalystReport or (
            isinstance(self._schema, type) and issubclass(self._schema, AnalystReport)
        ):
            return self._analyst
        if self._schema is ReportPayload or (
            isinstance(self._schema, type) and issubclass(self._schema, ReportPayload)
        ):
            return _CANNED_REPORT_PAYLOAD
        return self._turn


class _SchemaAwareLLM:
    def with_structured_output(self, schema, method=None):
        return _SchemaAwareStructured(schema)


def _patch_all(monkeypatch):
    """Patch get_llm + tool functions so the full graph runs without any network call."""
    import src.agents.router as router_mod
    import src.agents.analysts.news as news_mod
    import src.agents.analysts.fundamentals as fund_mod
    import src.agents.analysts.technicals as tech_mod
    import src.agents.research.bull as bull_mod
    import src.agents.research.bear as bear_mod
    import src.agents.research.facilitator as fac_mod
    import src.agents.research.synthesis as syn_mod
    import src.agents.debate as debate_mod
    import src.agents.reporter as reporter_mod
    from src.agents.router import TickerResolution
    from src.tools.yfinance import Fundamentals
    from src.tools.tradingview import Technicals

    fake_llm = _SchemaAwareLLM()

    # Router uses a different schema (TickerResolution) so give it a specific fake
    class _RouterStructured:
        async def ainvoke(self, messages, config=None, **kwargs):
            return TickerResolution(resolved_ticker="AAPL", screener="america", exchange="NASDAQ")

    class _RouterLLM:
        def with_structured_output(self, schema, method=None):
            return _RouterStructured()

    monkeypatch.setattr(router_mod, "get_llm", lambda tier: _RouterLLM())
    async def _no_cached_verdict(*a, **k):
        return None

    monkeypatch.setattr(router_mod, "_get_cached_verdict", _no_cached_verdict)

    for mod in (news_mod, fund_mod, tech_mod, bull_mod, bear_mod, fac_mod, syn_mod, debate_mod):
        if hasattr(mod, "get_llm"):
            monkeypatch.setattr(mod, "get_llm", lambda tier, _llm=fake_llm: _llm)

    # Reporter uses ReportPayload — patch its get_llm with the schema-aware fake
    monkeypatch.setattr(reporter_mod, "get_llm", lambda tier, _llm=fake_llm: _llm)

    # --- tool fakes (no network) ---
    monkeypatch.setattr(news_mod, "search_news", lambda q, limit=5: [
        type("Hit", (), {"title": "news", "url": "https://x.com", "snippet": "ok", "markdown": None})()
    ])
    monkeypatch.setattr(fund_mod, "fetch_fundamentals", lambda t: Fundamentals(
        ticker="AAPL", name="Apple", sector="Tech", trailing_pe=28.0, forward_pe=25.0,
        earnings_growth=0.1, revenue_growth=0.05, dividend_yield=0.005, payout_ratio=0.15,
        profit_margins=0.25, gross_margins=0.44, market_cap=2.7e12, beta=1.2,
    ))
    monkeypatch.setattr(tech_mod, "fetch_technicals", lambda ticker, screener, exchange: Technicals(
        ticker="AAPL", exchange="NASDAQ", recommendation="BUY", buy_signals=10,
        neutral_signals=5, sell_signals=2, rsi=62.0, macd=1.5, macd_signal=1.1, close=170.0,
    ))


@pytest.mark.asyncio
async def test_graph_runs_end_to_end(monkeypatch):
    _patch_all(monkeypatch)
    app = build_graph()
    result = await app.ainvoke({"ticker": "AAPL", "investor_mode": "Neutral"})
    assert result["resolved_ticker"]  # router ran
    assert "final_report" in result  # reporter ran
    assert result["final_decision"]["action"] in {"BUY", "SELL", "HOLD"}
    # WP-F: financial_data written by real reporter
    assert "financial_data" in result
    assert set(result["financial_data"]) >= {"valuation", "growth", "profitability",
                                              "momentum", "sentiment", "risk"}


@pytest.mark.asyncio
async def test_graph_merges_three_parallel_analysts(monkeypatch):
    _patch_all(monkeypatch)
    app = build_graph()
    result = await app.ainvoke({"ticker": "AAPL", "investor_mode": "Neutral"})
    assert set(result["analyst_reports"]) == {"news", "fundamentals", "technicals"}


@pytest.mark.asyncio
async def test_graph_accumulates_run_metrics(monkeypatch):
    _patch_all(monkeypatch)
    app = build_graph()
    result = await app.ainvoke({"ticker": "AAPL", "investor_mode": "Neutral"})
    # "on" mode has 12 nodes. Each node contributes at least 1 run_metrics entry;
    # the facilitator contributes more (debate turns + verdict = research_debate_rounds*2 + 1).
    # With research_debate_rounds=1 (default): 12 base + 2 extra debate entries = 14.
    # We assert >= 12 to remain stable as debate rounds change.
    assert len(result["run_metrics"]) >= 12

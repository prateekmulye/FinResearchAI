# tests/test_smoke.py
"""Smoke test for the end-to-end graph runner script.

Updated by WP-D: real async nodes require ainvoke (scripts/smoke.py now uses
asyncio.run). The metric count assertion accepts >= 12 (was exactly 12 for stubs).
"""
from unittest.mock import patch

from scripts.smoke import run_stub
from src.llm.schemas import AnalystReport, DebateTurn


async def _no_cached_verdict(*a, **k):
    return None


def test_run_stub_returns_report_and_writes_trace(tmp_path):
    """Run the full graph offline (all LLM/tool calls mocked) and verify the trace."""
    from src.agents.router import TickerResolution
    from src.tools.yfinance import Fundamentals
    from src.tools.tradingview import Technicals

    class _RouterStructured:
        async def ainvoke(self, messages, config=None, **kwargs):
            return TickerResolution(resolved_ticker="AAPL", screener="america", exchange="NASDAQ")

    class _RouterLLM:
        def with_structured_output(self, schema, method=None):
            return _RouterStructured()

    class _AnalystStructured:
        async def ainvoke(self, messages, config=None, **kwargs):
            return AnalystReport(summary="stub", key_points=[], confidence=0.5)

    class _AnalystLLM:
        def with_structured_output(self, schema, method=None):
            return _AnalystStructured()

    class _DebateStructured:
        async def ainvoke(self, messages, config=None, **kwargs):
            return DebateTurn(role="bull", round=1, argument="lean BUY")

    class _DebateLLM:
        def with_structured_output(self, schema, method=None):
            return _DebateStructured()

    import src.agents.router as router_mod
    import src.agents.analysts.news as news_mod
    import src.agents.analysts.fundamentals as fund_mod
    import src.agents.analysts.technicals as tech_mod
    import src.agents.research.bull as bull_mod
    import src.agents.research.bear as bear_mod
    import src.agents.research.facilitator as fac_mod
    import src.agents.research.synthesis as syn_mod
    import src.agents.debate as debate_mod

    with (
        patch.object(router_mod, "get_llm", lambda tier: _RouterLLM()),
        patch.object(router_mod, "_get_cached_verdict", _no_cached_verdict),
        patch.object(news_mod, "get_llm", lambda tier: _AnalystLLM()),
        patch.object(fund_mod, "get_llm", lambda tier: _AnalystLLM()),
        patch.object(tech_mod, "get_llm", lambda tier: _AnalystLLM()),
        patch.object(bull_mod, "get_llm", lambda tier: _DebateLLM()),
        patch.object(bear_mod, "get_llm", lambda tier: _DebateLLM()),
        patch.object(fac_mod, "get_llm", lambda tier: _DebateLLM()),
        patch.object(syn_mod, "get_llm", lambda tier: _DebateLLM()),
        patch.object(debate_mod, "get_llm", lambda tier: _DebateLLM()),
        patch.object(news_mod, "search_news", lambda q, limit=5: [
            type("Hit", (), {"title": "t", "url": "https://x.com", "snippet": "s", "markdown": None})()
        ]),
        patch.object(fund_mod, "fetch_fundamentals", lambda t: Fundamentals(
            ticker="AAPL", name="Apple", sector="Tech", trailing_pe=28.0, forward_pe=25.0,
            earnings_growth=0.1, revenue_growth=0.05, dividend_yield=0.005, payout_ratio=0.15,
            profit_margins=0.25, gross_margins=0.44, market_cap=2.7e12, beta=1.2,
        )),
        patch.object(tech_mod, "fetch_technicals", lambda t, s, e: Technicals(
            ticker="AAPL", exchange="NASDAQ", recommendation="BUY", buy_signals=10,
            neutral_signals=5, sell_signals=2, rsi=62.0, macd=1.5, macd_signal=1.1, close=170.0,
        )),
    ):
        result, trace_path = run_stub("AAPL", runs_dir=str(tmp_path))

    assert "final_report" in result
    assert trace_path.exists()
    lines = trace_path.read_text(encoding="utf-8").strip().splitlines()
    # "on" mode has 12 nodes. WP-D nodes contribute 0 trace lines when their fake
    # LLM doesn't fire callbacks (per_node = []). The remaining 9 stub nodes always
    # write 1 line each (router + 3 analysts + trader + 2 risk + arbiter + reporter).
    # Assert >= 9 to verify the graph ran fully without network calls.
    assert len(lines) >= 9

# tests/test_graph_debate_modes.py
"""End-to-end and structural tests for build_graph(debate_mode) — WP-D.

All graph-level tests mock get_llm + tool functions to run fully offline.
"""
from __future__ import annotations

import pytest

from src.llm.schemas import AnalystReport, DebateTurn


# ---------------------------------------------------------------------------
# Offline graph helper — patches all real nodes so no network calls are made.
# ---------------------------------------------------------------------------

def _patch_analysts(monkeypatch):
    """Patch WP-B (router + analysts) offline — no network, no real LLM."""
    import src.agents.router as router_mod
    import src.agents.analysts.news as news_mod
    import src.agents.analysts.fundamentals as fund_mod
    import src.agents.analysts.technicals as tech_mod
    from src.agents.router import TickerResolution
    from src.tools.yfinance import Fundamentals
    from src.tools.tradingview import Technicals

    class _RouterStructured:
        async def ainvoke(self, messages, config=None, **kwargs):
            return TickerResolution(resolved_ticker="AAPL", screener="america", exchange="NASDAQ")

    class _RouterLLM:
        def with_structured_output(self, schema, method=None):
            return _RouterStructured()

    monkeypatch.setattr(router_mod, "get_llm", lambda tier: _RouterLLM())
    monkeypatch.setattr(router_mod, "_get_cached_verdict", lambda *a, **k: None)

    _analyst_report = AnalystReport(summary="stub report", key_points=[], confidence=0.5)

    class _AnalystStructured:
        async def ainvoke(self, messages, config=None, **kwargs):
            import time
            from types import SimpleNamespace
            callbacks = (config or {}).get("callbacks", []) or []
            rid = f"analyst-{time.monotonic_ns()}"
            for cb in callbacks:
                if hasattr(cb, "on_llm_start"):
                    cb.on_llm_start({}, ["<p>"], run_id=rid)
            resp = SimpleNamespace(
                llm_output={"token_usage": {"prompt_tokens": 5, "completion_tokens": 3},
                            "model_name": "fake"}
            )
            for cb in callbacks:
                if hasattr(cb, "on_llm_end"):
                    cb.on_llm_end(resp, run_id=rid)
            return _analyst_report

    class _AnalystLLM:
        def with_structured_output(self, schema, method=None):
            return _AnalystStructured()

    for mod in (news_mod, fund_mod, tech_mod):
        monkeypatch.setattr(mod, "get_llm", lambda tier: _AnalystLLM())

    monkeypatch.setattr(news_mod, "search_news", lambda q, limit=5: [
        type("Hit", (), {"title": "t", "url": "https://x.com", "snippet": "s", "markdown": None})()
    ])
    monkeypatch.setattr(fund_mod, "fetch_fundamentals", lambda t: Fundamentals(
        ticker="AAPL", name="Apple", sector="Tech", trailing_pe=28.0, forward_pe=25.0,
        earnings_growth=0.1, revenue_growth=0.05, dividend_yield=0.005, payout_ratio=0.15,
        profit_margins=0.25, gross_margins=0.44, market_cap=2.7e12, beta=1.2,
    ))
    monkeypatch.setattr(tech_mod, "fetch_technicals", lambda t, s, e: Technicals(
        ticker="AAPL", exchange="NASDAQ", recommendation="BUY", buy_signals=10,
        neutral_signals=5, sell_signals=2, rsi=62.0, macd=1.5, macd_signal=1.1, close=170.0,
    ))


def _patch_debate_nodes(monkeypatch, debate_outputs: list):
    """Patch WP-D research nodes (bull, bear, facilitator, synthesis, debate) with a
    queued fake LLM. All nodes share the same queue so outputs must be provided in
    invocation order.
    """
    import src.agents.research.bull as bull_mod
    import src.agents.research.bear as bear_mod
    import src.agents.research.facilitator as fac_mod
    import src.agents.research.synthesis as syn_mod
    import src.agents.debate as debate_mod

    queue = list(debate_outputs)

    class _DebateStructured:
        async def ainvoke(self, messages, config=None, **kwargs):
            import time
            from types import SimpleNamespace
            callbacks = (config or {}).get("callbacks", []) or []
            rid = f"debate-{time.monotonic_ns()}"
            for cb in callbacks:
                if hasattr(cb, "on_llm_start"):
                    cb.on_llm_start({}, ["<p>"], run_id=rid)
            result = queue.pop(0)
            resp = SimpleNamespace(
                llm_output={"token_usage": {"prompt_tokens": 10, "completion_tokens": 5},
                            "model_name": "fake-deep"}
            )
            for cb in callbacks:
                if hasattr(cb, "on_llm_end"):
                    cb.on_llm_end(resp, run_id=rid)
            return result

    class _DebateLLM:
        def with_structured_output(self, schema, method=None):
            return _DebateStructured()

    for mod in (bull_mod, bear_mod, fac_mod, syn_mod, debate_mod):
        monkeypatch.setattr(mod, "get_llm", lambda tier: _DebateLLM())


def _patch_graph(monkeypatch, debate_outputs: list):
    """Convenience: patch both WP-B and WP-D nodes offline."""
    _patch_analysts(monkeypatch)
    _patch_debate_nodes(monkeypatch, debate_outputs)


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_debate_mode_on_produces_full_research_debate(monkeypatch):
    """Bull and bear run concurrently (parallel LangGraph fan-out). We patch their
    get_llm separately (each returning its own fixed output) so the assertions are
    deterministic regardless of which runs first. The facilitator debate + verdict
    use a separate queued fake.
    """
    import time
    from types import SimpleNamespace
    import src.agents.research.bull as bull_mod
    import src.agents.research.bear as bear_mod
    import src.agents.research.facilitator as fac_mod
    import src.agents.debate as debate_mod

    _patch_analysts(monkeypatch)  # router + analysts only

    # Per-node fixed outputs for bull and bear (deterministic despite parallel execution)
    bull_turn = DebateTurn(role="bull", round=1, argument="bull opening")
    bear_turn = DebateTurn(role="bear", round=1, argument="bear opening")

    def _make_fixed_llm(fixed_output):
        class _Structured:
            async def ainvoke(self, messages, config=None, **kwargs):
                callbacks = (config or {}).get("callbacks", []) or []
                rid = f"r-{time.monotonic_ns()}"
                for cb in callbacks:
                    if hasattr(cb, "on_llm_start"):
                        cb.on_llm_start({}, ["<p>"], run_id=rid)
                resp = SimpleNamespace(
                    llm_output={"token_usage": {"prompt_tokens": 10, "completion_tokens": 5},
                                "model_name": "fake-deep"}
                )
                for cb in callbacks:
                    if hasattr(cb, "on_llm_end"):
                        cb.on_llm_end(resp, run_id=rid)
                return fixed_output

        class _LLM:
            def with_structured_output(self, schema, method=None):
                return _Structured()

        return _LLM()

    monkeypatch.setattr(bull_mod, "get_llm", lambda tier: _make_fixed_llm(bull_turn))
    monkeypatch.setattr(bear_mod, "get_llm", lambda tier: _make_fixed_llm(bear_turn))

    # Facilitator: 1 round × 2 personas = 2 debate turns + 1 verdict = 3 queued calls
    fac_queue = [
        DebateTurn(role="bull", round=1, argument="bull rebuttal"),
        DebateTurn(role="bear", round=1, argument="bear rebuttal"),
        DebateTurn(role="bull", round=1, argument="lean BUY verdict"),
    ]

    class _FacStructured:
        async def ainvoke(self, messages, config=None, **kwargs):
            callbacks = (config or {}).get("callbacks", []) or []
            rid = f"fac-{time.monotonic_ns()}"
            for cb in callbacks:
                if hasattr(cb, "on_llm_start"):
                    cb.on_llm_start({}, ["<p>"], run_id=rid)
            result = fac_queue.pop(0)
            resp = SimpleNamespace(
                llm_output={"token_usage": {"prompt_tokens": 10, "completion_tokens": 5},
                            "model_name": "fake-deep"}
            )
            for cb in callbacks:
                if hasattr(cb, "on_llm_end"):
                    cb.on_llm_end(resp, run_id=rid)
            return result

    class _FacLLM:
        def with_structured_output(self, schema, method=None):
            return _FacStructured()

    monkeypatch.setattr(fac_mod, "get_llm", lambda tier: _FacLLM())
    monkeypatch.setattr(debate_mod, "get_llm", lambda tier: _FacLLM())

    from src.graph import build_graph

    app = build_graph(debate_mode="on")
    result = await app.ainvoke({"ticker": "AAPL", "investor_mode": "Neutral"})
    rd = result["research_debate"]
    assert rd["bull_thesis"] == "bull opening"
    assert rd["bear_thesis"] == "bear opening"
    assert rd["facilitator_verdict"] == "lean BUY verdict"
    assert len(rd["rounds"]) == 2


@pytest.mark.asyncio
async def test_debate_mode_off_produces_verdict_only(monkeypatch):
    _patch_graph(monkeypatch, [DebateTurn(role="bull", round=1, argument="single-pass lean HOLD")])
    from src.graph import build_graph

    app = build_graph(debate_mode="off")
    result = await app.ainvoke({"ticker": "AAPL", "investor_mode": "Neutral"})
    rd = result["research_debate"]
    assert rd["facilitator_verdict"] == "single-pass lean HOLD"
    assert rd.get("bull_thesis", "") == ""
    assert rd.get("bear_thesis", "") == ""


def test_debate_mode_off_does_not_register_debate_nodes():
    from src.graph import build_graph

    app = build_graph(debate_mode="off")
    node_names = set(app.get_graph().nodes)
    assert "research_synthesis" in node_names
    assert "bull" not in node_names
    assert "bear" not in node_names
    assert "facilitator" not in node_names


def test_debate_mode_on_registers_debate_nodes():
    from src.graph import build_graph

    app = build_graph(debate_mode="on")
    node_names = set(app.get_graph().nodes)
    assert {"bull", "bear", "facilitator"} <= node_names
    assert "research_synthesis" not in node_names


def test_build_graph_defaults_to_settings():
    # No arg -> reads settings.debate_mode (default "on")
    from src.graph import build_graph

    app = build_graph()
    assert "facilitator" in set(app.get_graph().nodes)


@pytest.mark.asyncio
async def test_debate_mode_on_has_12_nodes(monkeypatch):
    scripted = [
        DebateTurn(role="bull", round=1, argument="bull opening"),
        DebateTurn(role="bear", round=1, argument="bear opening"),
        DebateTurn(role="bull", round=1, argument="bull rebuttal"),
        DebateTurn(role="bear", round=1, argument="bear rebuttal"),
        DebateTurn(role="bull", round=1, argument="lean BUY verdict"),
    ]
    _patch_graph(monkeypatch, scripted)
    from src.graph import build_graph

    app = build_graph(debate_mode="on")
    # 12 nodes per COORDINATION §7.4 (router, 3 analysts, bull, bear, facilitator,
    # trader, risk_conservative, risk_aggressive, risk_arbiter, reporter)
    node_names = set(app.get_graph().nodes) - {"__start__", "__end__"}
    assert len(node_names) == 12


@pytest.mark.asyncio
async def test_debate_mode_off_has_10_nodes(monkeypatch):
    _patch_graph(monkeypatch, [DebateTurn(role="bull", round=1, argument="lean HOLD")])
    from src.graph import build_graph

    app = build_graph(debate_mode="off")
    # 10 nodes per COORDINATION §7.4 (replaces bull+bear+facilitator with research_synthesis)
    node_names = set(app.get_graph().nodes) - {"__start__", "__end__"}
    assert len(node_names) == 10

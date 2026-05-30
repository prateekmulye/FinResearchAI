# tests/conftest.py
"""Shared test fixtures for WP-D (and downstream WPs).

``make_structured_llm`` produces a scripted fake LLM whose
``.with_structured_output(...).ainvoke(...)`` yields prepared Pydantic objects in
order and fires LangChain callbacks so CostTracker records one entry per call.

``fake_llm_factory`` is a pytest fixture that installs such an LLM via monkeypatch.
"""
from __future__ import annotations

import importlib
from types import SimpleNamespace
from typing import Any

import pytest

from src.llm.schemas import AnalystReport, DebateTurn, FinalDecision, RiskStance, TradeProposal
from src.agents.reporter import ReportPayload

# ---------------------------------------------------------------------------
# Schema registry — only schemas listed here are accepted by the fake LLM.
# Adding a new schema to production code requires registering it here too;
# an unregistered schema raises KeyError loudly so missing mappings are caught
# immediately rather than silently returning None or a wrong default.
# ---------------------------------------------------------------------------
_KNOWN_SCHEMAS: frozenset = frozenset({
    DebateTurn,
    AnalystReport,
    TradeProposal,
    FinalDecision,
    RiskStance,             # canonical; risk personas now import this (no shadow classes)
    ReportPayload,          # WP-F: reporter structured-output schema
})


def make_structured_llm(outputs: list[Any]):
    """Return a fake LLM whose .with_structured_output(...).ainvoke(...) yields
    the prepared outputs in order. Each ainvoke fires the CostTracker callbacks
    so per-node metrics are recorded with realistic token counts.
    """
    queue = list(outputs)
    call_counter = [0]

    class _Structured:
        async def ainvoke(self, messages, config=None, **kwargs):
            call_counter[0] += 1
            rid = f"run-{call_counter[0]}"
            callbacks = (config or {}).get("callbacks", []) or []
            for cb in callbacks:
                if hasattr(cb, "on_llm_start"):
                    cb.on_llm_start({}, ["<prompt>"], run_id=rid)
            result = queue.pop(0)
            response = SimpleNamespace(
                llm_output={
                    "token_usage": {"prompt_tokens": 10, "completion_tokens": 5},
                    "model_name": "fake-deep",
                }
            )
            # Simulate a tiny delay so latency_s > 0 doesn't confuse assertions.
            for cb in callbacks:
                if hasattr(cb, "on_llm_end"):
                    cb.on_llm_end(response, run_id=rid)
            return result

    class _LLM:
        def with_structured_output(self, schema, method="function_calling"):
            # F6: raise loudly (by identity) for schemas not in the registry so missing
            # mappings fail immediately rather than silently returning wrong data.
            if schema not in _KNOWN_SCHEMAS:
                raise KeyError(
                    f"conftest: no canned instance registered for {schema}"
                )
            return _Structured()

    return _LLM()


@pytest.fixture
def fake_llm_factory(monkeypatch):
    """Patch get_llm everywhere it is imported so nodes receive a scripted LLM.

    Usage::

        fake_llm_factory([turn1, turn2, ...], ["src.agents.debate", "src.agents.research.bull"])

    Patches ``src.llm.factory.get_llm`` and each named module's ``get_llm`` attribute.
    """

    def _install(outputs: list[Any], modules: list[str]) -> Any:
        llm = make_structured_llm(outputs)
        import src.llm.factory as factory_mod

        monkeypatch.setattr(factory_mod, "get_llm", lambda tier: llm)
        for mod_path in modules:
            mod = importlib.import_module(mod_path)
            if hasattr(mod, "get_llm"):
                monkeypatch.setattr(mod, "get_llm", lambda tier, _llm=llm: _llm)
        return llm

    return _install


# ---------------------------------------------------------------------------
# offline_graph — run the FULL compiled graph offline (no network, no LLM).
#
# Added (additively) by WP-G: the API streaming/endpoint tests drive
# ``build_graph().astream(...)`` end-to-end, so every LLM-calling node and every
# tool must be patched. This mirrors the proven ``_patch_all`` helper in
# ``tests/test_graph_skeleton.py`` and is exposed as a reusable fixture so the
# WP-G ``test_api_*`` modules don't duplicate it. Existing fixtures above are
# untouched.
# ---------------------------------------------------------------------------


def _install_offline_graph(monkeypatch) -> None:
    """Patch get_llm + tool functions so ``build_graph()`` runs with zero network."""
    from src.agents.reporter import FinancialData, ReportPayload, ReportSection
    from src.agents.router import TickerResolution
    from src.llm.schemas import (
        AnalystReport,
        DebateTurn,
        FinalDecision,
        RiskStance,
        TradeProposal,
    )
    from src.tools.tradingview import Technicals
    from src.tools.yfinance import Fundamentals

    canned_report = ReportPayload(
        sections=[ReportSection(heading="Summary", body="offline report ok")],
        financial_data=FinancialData(
            valuation=50.0, growth=50.0, profitability=50.0,
            momentum=50.0, sentiment=50.0, risk=50.0,
        ),
    )

    class _SchemaAwareStructured:
        _analyst = AnalystReport(summary="offline report", key_points=[], confidence=0.5)
        _turn = DebateTurn(role="bull", round=1, argument="lean BUY")
        _trade = TradeProposal(action="HOLD", conviction=0.5, score=50, rationale="offline")
        _risk = RiskStance(stance="offline balanced stance")
        _final = FinalDecision(action="HOLD", conviction=0.5, score=50, rationale="offline")

        def __init__(self, schema):
            self._schema = schema

        async def ainvoke(self, messages, config=None, **kwargs):
            import time
            from types import SimpleNamespace

            callbacks = (config or {}).get("callbacks", []) or []
            rid = f"offline-{id(self)}-{time.monotonic_ns()}"
            for cb in callbacks:
                if hasattr(cb, "on_llm_start"):
                    cb.on_llm_start({}, ["<prompt>"], run_id=rid)
            response = SimpleNamespace(
                llm_output={
                    "token_usage": {"prompt_tokens": 5, "completion_tokens": 3},
                    "model_name": "fake-offline",
                }
            )
            for cb in callbacks:
                if hasattr(cb, "on_llm_end"):
                    cb.on_llm_end(response, run_id=rid)
            schema = self._schema
            if isinstance(schema, type) and issubclass(schema, AnalystReport):
                return self._analyst
            if isinstance(schema, type) and issubclass(schema, ReportPayload):
                return canned_report
            if isinstance(schema, type) and issubclass(schema, FinalDecision):
                return self._final
            if isinstance(schema, type) and issubclass(schema, TradeProposal):
                return self._trade
            if isinstance(schema, type) and issubclass(schema, RiskStance):
                return self._risk
            return self._turn

    class _SchemaAwareLLM:
        def with_structured_output(self, schema, method=None):
            return _SchemaAwareStructured(schema)

    class _RouterStructured:
        async def ainvoke(self, messages, config=None, **kwargs):
            return TickerResolution(
                resolved_ticker="AAPL", screener="america", exchange="NASDAQ"
            )

    class _RouterLLM:
        def with_structured_output(self, schema, method=None):
            return _RouterStructured()

    import src.agents.analysts.fundamentals as fund_mod
    import src.agents.analysts.news as news_mod
    import src.agents.analysts.technicals as tech_mod
    import src.agents.debate as debate_mod
    import src.agents.reporter as reporter_mod
    import src.agents.research.bear as bear_mod
    import src.agents.research.bull as bull_mod
    import src.agents.research.facilitator as fac_mod
    import src.agents.research.synthesis as syn_mod
    import src.agents.risk.aggressive as agg_mod
    import src.agents.risk.arbiter as arb_mod
    import src.agents.risk.conservative as cons_mod
    import src.agents.router as router_mod
    import src.agents.trader as trader_mod

    fake_llm = _SchemaAwareLLM()

    monkeypatch.setattr(router_mod, "get_llm", lambda tier: _RouterLLM())
    monkeypatch.setattr(router_mod, "_get_cached_verdict", lambda *a, **k: None)

    for mod in (
        news_mod, fund_mod, tech_mod, bull_mod, bear_mod, fac_mod, syn_mod,
        debate_mod, reporter_mod, trader_mod, cons_mod, agg_mod, arb_mod,
    ):
        if hasattr(mod, "get_llm"):
            monkeypatch.setattr(mod, "get_llm", lambda tier, _llm=fake_llm: _llm)
    # arbiter may call memory.store_verdict (WP-C); neutralize it offline.
    if hasattr(arb_mod, "store_verdict"):
        monkeypatch.setattr(arb_mod, "store_verdict", lambda *a, **k: None)

    monkeypatch.setattr(
        news_mod,
        "search_news",
        lambda q, limit=5: [
            type("Hit", (), {"title": "news", "url": "https://x.com",
                             "snippet": "ok", "markdown": None})()
        ],
    )
    monkeypatch.setattr(
        fund_mod,
        "fetch_fundamentals",
        lambda t: Fundamentals(
            ticker="AAPL", name="Apple", sector="Tech", trailing_pe=28.0, forward_pe=25.0,
            earnings_growth=0.1, revenue_growth=0.05, dividend_yield=0.005, payout_ratio=0.15,
            profit_margins=0.25, gross_margins=0.44, market_cap=2.7e12, beta=1.2,
        ),
    )
    monkeypatch.setattr(
        tech_mod,
        "fetch_technicals",
        lambda ticker, screener, exchange: Technicals(
            ticker="AAPL", exchange="NASDAQ", recommendation="BUY", buy_signals=10,
            neutral_signals=5, sell_signals=2, rsi=62.0, macd=1.5, macd_signal=1.1,
            close=170.0,
        ),
    )


@pytest.fixture
def offline_graph(monkeypatch):
    """Fixture: patch all node LLMs + tools so the compiled graph runs offline."""
    _install_offline_graph(monkeypatch)
    return monkeypatch

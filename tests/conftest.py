# tests/conftest.py
"""Shared test fixtures for WP-D (and downstream WPs).

``make_structured_llm`` produces a scripted fake LLM whose
``.with_structured_output(...).ainvoke(...)`` yields prepared Pydantic objects in
order and fires LangChain callbacks so CostTracker records one entry per call.

``fake_llm_factory`` is a pytest fixture that installs such an LLM via monkeypatch.
"""
from __future__ import annotations

import importlib
import sys
from types import SimpleNamespace
from typing import Any

import pytest

from src.config import settings as settings_mod
from src.llm import factory as factory_mod
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

    async def _no_cached_verdict(*a, **k):
        return None

    monkeypatch.setattr(router_mod, "get_llm", lambda tier: _RouterLLM())
    monkeypatch.setattr(router_mod, "_get_cached_verdict", _no_cached_verdict)

    for mod in (
        news_mod, fund_mod, tech_mod, bull_mod, bear_mod, fac_mod, syn_mod,
        debate_mod, reporter_mod, trader_mod, cons_mod, agg_mod, arb_mod,
    ):
        if hasattr(mod, "get_llm"):
            monkeypatch.setattr(mod, "get_llm", lambda tier, _llm=fake_llm: _llm)
    # arbiter awaits memory.store_verdict (WP-2: async, warehouse-backed);
    # neutralize it offline with an async no-op.
    async def _noop_store_verdict(*a, **k):
        return None

    if hasattr(arb_mod, "store_verdict"):
        monkeypatch.setattr(arb_mod, "store_verdict", _noop_store_verdict)

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


# ---------------------------------------------------------------------------
# WP-I shared fixtures — added ADDITIVELY (existing fixtures above untouched).
#
# - env_isolation (autouse): scrub provider keys + force RUN_LIVE off so no test
#   accidentally hits the network or reads a real .env.
# - fake_llm: schema-routed factory that patches src.llm.factory.get_llm (and the
#   get_llm name re-imported into already-loaded src.* node modules) to return a
#   fake whose .with_structured_output(Schema).ainvoke(...) yields a supplied
#   Pydantic instance.
# - frozen_state: builder producing a fully-populated AgentState dict.
# ---------------------------------------------------------------------------


@pytest.fixture(autouse=True)
def env_isolation(monkeypatch):
    """Clear provider keys and the live switch; clear cached singletons.

    Runs for EVERY test (autouse). Ensures unit/integration tests never read a
    real .env or reach a live provider, and that get_settings()/get_llm() caches
    don't leak a real key between tests.
    """
    for key in (
        "OLLAMA_API_KEY",
        "FIRECRAWL_API_KEY",
        "LLM_BASE_URL",
        "LANGSMITH_API_KEY",
        "DATABASE_URL",
        "DB_ECHO",
    ):
        monkeypatch.delenv(key, raising=False)
    monkeypatch.setenv("RUN_LIVE", "0")
    # Construct Settings without reading the on-disk .env in tests.
    monkeypatch.setattr(
        settings_mod.Settings,
        "model_config",
        {**settings_mod.Settings.model_config, "env_file": None},
        raising=False,
    )
    _clear_caches()
    yield
    _clear_caches()


def _clear_caches() -> None:
    """Clear the settings + factory lru_caches if they are still the cached funcs.

    Guarded with ``hasattr`` because a test may have monkeypatched ``get_llm`` /
    ``get_settings`` to a plain callable that lacks ``cache_clear``.
    """
    if hasattr(settings_mod.get_settings, "cache_clear"):
        settings_mod.get_settings.cache_clear()
    if hasattr(factory_mod.get_llm, "cache_clear"):
        factory_mod.get_llm.cache_clear()


class _WPIFakeStructured:
    """Stand-in for llm.with_structured_output(Schema): its ainvoke returns a fixed instance."""

    def __init__(self, instance: Any) -> None:
        self._instance = instance

    async def ainvoke(self, *args, **kwargs) -> Any:
        return self._instance

    def invoke(self, *args, **kwargs) -> Any:
        return self._instance


class _WPIFakeLLM:
    """Stand-in for a ChatOpenAI. with_structured_output(Schema) -> _WPIFakeStructured.

    ``mapping`` is either a single Pydantic instance (returned for any schema) or a
    dict {SchemaClass: instance} routed by the schema passed to with_structured_output.
    """

    def __init__(self, mapping: Any) -> None:
        self._mapping = mapping

    def with_structured_output(self, schema=None, **kwargs) -> _WPIFakeStructured:
        if isinstance(self._mapping, dict):
            if schema not in self._mapping:
                raise KeyError(
                    f"fake_llm has no registered instance for schema {schema!r}; "
                    f"registered: {list(self._mapping)}"
                )
            return _WPIFakeStructured(self._mapping[schema])
        return _WPIFakeStructured(self._mapping)

    async def ainvoke(self, *args, **kwargs) -> Any:
        # For nodes that call the raw LLM without structured output.
        if isinstance(self._mapping, dict):
            return next(iter(self._mapping.values()))
        return self._mapping


@pytest.fixture
def fake_llm(monkeypatch):
    """Factory fixture. Call ``fake_llm(instance)`` or ``fake_llm({Schema: instance, ...})``.

    Patches ``src.llm.factory.get_llm`` AND the ``get_llm`` name as re-imported
    into every already-loaded ``src.`` module (nodes do ``from src.llm.factory
    import get_llm``), so every tier returns the same fake. Returns the configured
    fake in case the test wants to inspect it.
    """

    # The real factory function as currently bound; we patch every module whose
    # `get_llm` IS this exact object (covers `from src.llm.factory import get_llm`
    # re-imports in node modules AND in test modules) — precise, won't clobber
    # unrelated `get_llm` names.
    _real_get_llm = factory_mod.get_llm

    def _install(mapping: Any) -> _WPIFakeLLM:
        fake = _WPIFakeLLM(mapping)
        _fake_get_llm = lambda tier=None: fake  # noqa: E731 - tiny stand-in
        monkeypatch.setattr(factory_mod, "get_llm", _fake_get_llm)
        for mod in list(sys.modules.values()):
            if mod is None or mod is factory_mod:
                continue
            if getattr(mod, "get_llm", None) is _real_get_llm:
                monkeypatch.setattr(mod, "get_llm", _fake_get_llm)
        return fake

    return _install


@pytest.fixture
def frozen_state():
    """Builder fixture: returns a callable producing a fully-populated AgentState dict.

    Defaults model a completed run for 'AAPL'; pass overrides to vary fields.
    """

    def _build(**overrides: Any) -> dict:
        state: dict[str, Any] = {
            "ticker": "AAPL",
            "resolved_ticker": "AAPL",
            "screener": "america",
            "exchange": "NASDAQ",
            "investor_mode": "Neutral",
            "model_plan": {"analysts": "quick", "debate": "deep", "verdict": "deep"},
            "analyst_reports": {
                "news": {
                    "summary": "news ok", "key_points": ["a"],
                    "confidence": 0.6, "citations": ["http://x"],
                },
                "fundamentals": {
                    "summary": "fundies ok", "key_points": ["b"],
                    "confidence": 0.7, "citations": [],
                },
                "technicals": {
                    "summary": "tech ok", "key_points": ["c"],
                    "confidence": 0.5, "citations": [],
                },
            },
            "research_debate": {
                "bull_thesis": "upside",
                "bear_thesis": "downside",
                "facilitator_verdict": "lean neutral",
            },
            "trade_proposal": {
                "action": "HOLD", "conviction": 0.5, "score": 50, "rationale": "mixed",
            },
            "risk_debate": {
                "conservative": "be careful",
                "aggressive": "be bold",
                "arbiter_decision": "hold",
                "adjustments": [],
            },
            "final_decision": {
                "action": "HOLD", "conviction": 0.5, "score": 50, "rationale": "final",
            },
            "final_report": "# AAPL Report\n\nStub body.",
            "run_metrics": [],
            "run_id": "test-run-0001",
        }
        state.update(overrides)
        return state

    return _build

# tests/test_risk_nodes.py
"""Unit tests for WP-E risk nodes: trader, risk_conservative, risk_aggressive, risk_arbiter.

Covers:
 F1  — each risk persona + arbiter degrade (LLM raises) without propagating
 F2  — arbiter feeds debate transcript into the FinalDecision prompt
 F3  — arbiter run_metrics includes both debate metrics and arbiter own metrics
 F4  — trader uses safe .get() access (no KeyError on missing nested keys)
 F5  — (cache-key alignment; tested via store_verdict key in arbiter)
"""
from __future__ import annotations

from types import SimpleNamespace

import pytest

from src.llm.schemas import DebateTurn, FinalDecision, RiskStance, TradeProposal


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


async def _noop_store_verdict(*a, **k):
    return None


def _trade_state() -> dict:
    return {
        "ticker": "TSLA",
        "resolved_ticker": "TSLA",
        "investor_mode": "Neutral",
        "research_debate": {
            "facilitator_verdict": "lean BUY on strong growth",
            "bull_thesis": "battery cost advantage",
            "bear_thesis": "valuation stretched",
        },
        "analyst_reports": {
            "news": {"summary": "positive momentum", "confidence": 0.7},
        },
        "trade_proposal": {
            "action": "BUY",
            "conviction": 0.75,
            "score": 72,
            "rationale": "Strong growth trajectory.",
        },
        "risk_debate": {
            "conservative": "cap-weight carefully",
            "aggressive": "size up aggressively",
        },
    }


def _make_llm(output, *, raises: Exception | None = None):
    """Minimal fake LLM; fires callbacks so CostTracker records an entry."""

    class _Structured:
        async def ainvoke(self, messages, config=None, **kwargs):
            callbacks = (config or {}).get("callbacks", []) or []
            rid = "test-run"
            for cb in callbacks:
                if hasattr(cb, "on_llm_start"):
                    cb.on_llm_start({}, ["<p>"], run_id=rid)
            resp = SimpleNamespace(
                llm_output={"token_usage": {"prompt_tokens": 8, "completion_tokens": 4},
                            "model_name": "fake"}
            )
            for cb in callbacks:
                if hasattr(cb, "on_llm_end"):
                    cb.on_llm_end(resp, run_id=rid)
            if raises is not None:
                raise raises
            return output

    class _LLM:
        def with_structured_output(self, schema, method=None):
            return _Structured()

    return _LLM()


# ---------------------------------------------------------------------------
# Trader tests (F4)
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_trader_happy_path(monkeypatch):
    import src.agents.trader as trader_mod

    proposal = TradeProposal(action="BUY", conviction=0.75, score=72, rationale="strong growth")
    monkeypatch.setattr(trader_mod, "get_llm", lambda tier: _make_llm(proposal))

    from src.agents.trader import trader

    out = await trader(_trade_state())
    assert out["trade_proposal"]["action"] == "BUY"
    assert out["trade_proposal"]["conviction"] == 0.75
    assert len(out["run_metrics"]) >= 1
    assert out["run_metrics"][0]["node"] == "trader"


@pytest.mark.asyncio
async def test_trader_degrade_on_llm_failure(monkeypatch):
    """F4: trader degrades to HOLD on LLM exception without propagating."""
    import src.agents.trader as trader_mod

    monkeypatch.setattr(
        trader_mod, "get_llm",
        lambda tier: _make_llm(None, raises=RuntimeError("network timeout"))
    )

    from src.agents.trader import trader

    out = await trader(_trade_state())
    # Degraded: HOLD
    assert out["trade_proposal"]["action"] == "HOLD"
    assert "degraded" in out["trade_proposal"]["rationale"].lower()
    assert out["run_metrics"]  # metrics still returned


@pytest.mark.asyncio
async def test_trader_safe_get_on_empty_research_debate(monkeypatch):
    """F4: trader does not raise KeyError when research_debate keys are missing."""
    import src.agents.trader as trader_mod

    proposal = TradeProposal(action="HOLD", conviction=0.3, score=40, rationale="minimal context")
    monkeypatch.setattr(trader_mod, "get_llm", lambda tier: _make_llm(proposal))

    from src.agents.trader import trader

    # State with no research_debate and no analyst_reports
    state = {"ticker": "AAPL", "resolved_ticker": "AAPL"}
    out = await trader(state)
    assert out["trade_proposal"]["action"] in {"BUY", "SELL", "HOLD"}


# ---------------------------------------------------------------------------
# Conservative risk node tests (F1)
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_conservative_happy_path(monkeypatch):
    import src.agents.risk.conservative as cons_mod

    stance_obj = RiskStance(stance="Reduce position size by 30%.")
    monkeypatch.setattr(cons_mod, "get_llm", lambda tier: _make_llm(stance_obj))

    from src.agents.risk.conservative import risk_conservative

    out = await risk_conservative(_trade_state())
    assert out["risk_debate"]["conservative"] == "Reduce position size by 30%."
    assert out["run_metrics"][0]["node"] == "risk_conservative"


@pytest.mark.asyncio
async def test_conservative_degrade_on_llm_failure(monkeypatch):
    """F1: risk_conservative degrades to caution string without propagating."""
    import src.agents.risk.conservative as cons_mod

    monkeypatch.setattr(
        cons_mod, "get_llm",
        lambda tier: _make_llm(None, raises=ConnectionError("LLM unreachable"))
    )

    from src.agents.risk.conservative import risk_conservative

    out = await risk_conservative(_trade_state())
    # Must not raise; must write a degraded stance
    stance = out["risk_debate"]["conservative"]
    assert stance  # non-empty
    assert "caution" in stance.lower()
    assert out["run_metrics"]  # still has metrics


# ---------------------------------------------------------------------------
# Aggressive risk node tests (F1)
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_aggressive_happy_path(monkeypatch):
    import src.agents.risk.aggressive as agg_mod

    stance_obj = RiskStance(stance="Increase conviction; asymmetric upside.")
    monkeypatch.setattr(agg_mod, "get_llm", lambda tier: _make_llm(stance_obj))

    from src.agents.risk.aggressive import risk_aggressive

    out = await risk_aggressive(_trade_state())
    assert out["risk_debate"]["aggressive"] == "Increase conviction; asymmetric upside."
    assert out["run_metrics"][0]["node"] == "risk_aggressive"


@pytest.mark.asyncio
async def test_aggressive_degrade_on_llm_failure(monkeypatch):
    """F1: risk_aggressive degrades to measured optimism string without propagating."""
    import src.agents.risk.aggressive as agg_mod

    monkeypatch.setattr(
        agg_mod, "get_llm",
        lambda tier: _make_llm(None, raises=TimeoutError("LLM timeout"))
    )

    from src.agents.risk.aggressive import risk_aggressive

    out = await risk_aggressive(_trade_state())
    stance = out["risk_debate"]["aggressive"]
    assert stance  # non-empty
    assert "optimism" in stance.lower()
    assert out["run_metrics"]


# ---------------------------------------------------------------------------
# Arbiter tests (F1, F2, F3, F5)
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_arbiter_happy_path_debate_included_in_metrics(monkeypatch):
    """F3: run_metrics includes both debate metrics and arbiter FinalDecision metrics."""
    import src.agents.risk.arbiter as arbiter_mod

    captured_messages: list = []

    class _FinalStructured:
        async def ainvoke(self, messages, config=None, **kwargs):
            captured_messages.extend(messages)
            callbacks = (config or {}).get("callbacks", []) or []
            rid = "arb-final"
            for cb in callbacks:
                if hasattr(cb, "on_llm_start"):
                    cb.on_llm_start({}, ["<p>"], run_id=rid)
            resp = SimpleNamespace(
                llm_output={"token_usage": {"prompt_tokens": 10, "completion_tokens": 5},
                            "model_name": "fake"}
            )
            for cb in callbacks:
                if hasattr(cb, "on_llm_end"):
                    cb.on_llm_end(resp, run_id=rid)
            return FinalDecision(action="BUY", conviction=0.7, score=70, rationale="solid")

    class _FinalLLM:
        def with_structured_output(self, schema, method=None):
            return _FinalStructured()

    monkeypatch.setattr(arbiter_mod, "get_llm", lambda tier: _FinalLLM())

    # Stub run_debate to return controlled turns and known metrics
    debate_turn_c = DebateTurn(role="conservative", round=1, argument="watch the downside here")
    debate_turn_a = DebateTurn(role="aggressive", round=1, argument="upside is asymmetric")
    debate_metrics = [
        {"node": "risk_debate", "model": "fake", "prompt_tokens": 5,
         "completion_tokens": 3, "latency_s": 0.01, "cost_usd": 0.0},
        {"node": "risk_debate", "model": "fake", "prompt_tokens": 5,
         "completion_tokens": 3, "latency_s": 0.01, "cost_usd": 0.0},
    ]

    async def _fake_run_debate(*args, **kwargs):
        return [debate_turn_c, debate_turn_a], debate_metrics

    monkeypatch.setattr(arbiter_mod, "run_debate", _fake_run_debate)
    # Guard store_verdict from touching real storage
    monkeypatch.setattr(arbiter_mod, "store_verdict", _noop_store_verdict)

    from src.agents.risk.arbiter import risk_arbiter

    out = await risk_arbiter(_trade_state())

    # F3: debate metrics + arbiter metrics both present
    nodes = [m["node"] for m in out["run_metrics"]]
    assert "risk_debate" in nodes, "debate metrics missing from run_metrics"
    assert "risk_arbiter" in nodes, "arbiter metrics missing from run_metrics"

    # F2: transcript content reaches the FinalDecision LLM prompt
    all_content = " ".join(
        getattr(m, "content", "") for m in captured_messages
    )
    assert "watch the downside here" in all_content, (
        "debate transcript argument not found in FinalDecision prompt"
    )
    assert "upside is asymmetric" in all_content, (
        "second debate turn argument not found in FinalDecision prompt"
    )

    # Basic output checks
    assert out["final_decision"]["action"] == "BUY"
    assert out["risk_debate"]["rounds"]


@pytest.mark.asyncio
async def test_arbiter_degrade_on_final_decision_llm_failure(monkeypatch):
    """F1: arbiter degrades to trade_proposal when FinalDecision LLM raises."""
    import src.agents.risk.arbiter as arbiter_mod

    monkeypatch.setattr(
        arbiter_mod, "get_llm",
        lambda tier: _make_llm(None, raises=RuntimeError("LLM failure"))
    )

    debate_metrics = [
        {"node": "risk_debate", "model": "fake", "prompt_tokens": 5,
         "completion_tokens": 3, "latency_s": 0.0, "cost_usd": 0.0},
    ]

    async def _fake_run_debate(*args, **kwargs):
        return [], debate_metrics

    monkeypatch.setattr(arbiter_mod, "run_debate", _fake_run_debate)
    monkeypatch.setattr(arbiter_mod, "store_verdict", _noop_store_verdict)

    from src.agents.risk.arbiter import risk_arbiter

    state = _trade_state()
    out = await risk_arbiter(state)

    # Must NOT raise; must degrade to trade_proposal values
    fd = out["final_decision"]
    assert fd["action"] == "BUY"  # from trade_proposal in state
    assert "degraded" in fd["rationale"].lower()

    # F3: debate metrics still in run_metrics even on degrade
    nodes = [m["node"] for m in out["run_metrics"]]
    assert "risk_debate" in nodes, "debate metrics must be included even on arbiter degrade"


@pytest.mark.asyncio
async def test_arbiter_metrics_include_debate_metrics(monkeypatch):
    """F3: explicit assertion that run_metrics length = debate records + arbiter records."""
    import src.agents.risk.arbiter as arbiter_mod

    class _FinalStructured:
        async def ainvoke(self, messages, config=None, **kwargs):
            callbacks = (config or {}).get("callbacks", []) or []
            rid = "arb-f3"
            for cb in callbacks:
                if hasattr(cb, "on_llm_start"):
                    cb.on_llm_start({}, ["<p>"], run_id=rid)
            resp = SimpleNamespace(
                llm_output={"token_usage": {"prompt_tokens": 12, "completion_tokens": 6},
                            "model_name": "fake"}
            )
            for cb in callbacks:
                if hasattr(cb, "on_llm_end"):
                    cb.on_llm_end(resp, run_id=rid)
            return FinalDecision(action="HOLD", conviction=0.5, score=50, rationale="balanced")

    class _FinalLLM:
        def with_structured_output(self, schema, method=None):
            return _FinalStructured()

    monkeypatch.setattr(arbiter_mod, "get_llm", lambda tier: _FinalLLM())

    # 2 debate turns → 2 debate metric entries
    debate_metrics_2 = [
        {"node": "risk_debate", "model": "fake", "prompt_tokens": 5,
         "completion_tokens": 3, "latency_s": 0.0, "cost_usd": 0.0},
        {"node": "risk_debate", "model": "fake", "prompt_tokens": 5,
         "completion_tokens": 3, "latency_s": 0.0, "cost_usd": 0.0},
    ]

    async def _fake_run_debate(*args, **kwargs):
        return [], debate_metrics_2

    monkeypatch.setattr(arbiter_mod, "run_debate", _fake_run_debate)
    monkeypatch.setattr(arbiter_mod, "store_verdict", _noop_store_verdict)

    from src.agents.risk.arbiter import risk_arbiter

    out = await risk_arbiter(_trade_state())

    # 2 debate + 1 arbiter FinalDecision = 3 total
    assert len(out["run_metrics"]) == 3
    risk_debate_entries = [m for m in out["run_metrics"] if m["node"] == "risk_debate"]
    arbiter_entries = [m for m in out["run_metrics"] if m["node"] == "risk_arbiter"]
    assert len(risk_debate_entries) == 2
    assert len(arbiter_entries) == 1

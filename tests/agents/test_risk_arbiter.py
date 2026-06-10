# tests/agents/test_risk_arbiter.py
import logging

import pytest

from src.agents.risk import arbiter as arb_mod
from src.llm.schemas import DebateTurn, FinalDecision


async def _noop_store_verdict(*a, **k):
    return None


def _base_state():
    return {
        "ticker": "AAPL",
        "resolved_ticker": "AAPL",
        "trade_proposal": {"action": "BUY", "conviction": 0.8, "score": 74, "rationale": "r"},
        "risk_debate": {"conservative": "trim size", "aggressive": "press it"},
    }


@pytest.mark.asyncio
async def test_arbiter_produces_valid_final_decision(monkeypatch, make_fake_llm):
    decision = FinalDecision(action="HOLD", conviction=0.55, score=58,
                             rationale="Balanced down from BUY given valuation risk.")
    fake = make_fake_llm([decision])
    monkeypatch.setattr(arb_mod, "get_llm", lambda tier: fake)

    async def fake_run_debate(topic, context, personas, rounds, tier="deep", node_label="debate", **kwargs):
        turns = [DebateTurn(role="conservative", round=1, argument="careful"),
                 DebateTurn(role="aggressive", round=1, argument="bold")]
        return turns, [{"node": node_label, "prompt_tokens": 0, "completion_tokens": 0,
                        "latency_s": 0.0, "cost_usd": 0.0, "model": ""}]
    monkeypatch.setattr(arb_mod, "run_debate", fake_run_debate)
    monkeypatch.setattr(arb_mod, "store_verdict", _noop_store_verdict)

    out = await arb_mod.risk_arbiter(_base_state())

    fd = out["final_decision"]
    assert fd == decision.model_dump()
    assert fd["action"] in {"BUY", "SELL", "HOLD"}
    # risk_debate is enriched with the transcript + arbiter decision + adjustments
    rd = out["risk_debate"]
    assert len(rd["rounds"]) == 2
    assert rd["arbiter_decision"]
    assert isinstance(rd["adjustments"], list)
    assert fake.structured_args[0]["schema"] is FinalDecision
    assert fake.structured_args[0]["method"] == "function_calling"


@pytest.mark.asyncio
async def test_arbiter_calls_store_verdict_with_ticker_and_decision(monkeypatch, make_fake_llm):
    decision = FinalDecision(action="BUY", conviction=0.7, score=70, rationale="ok")
    fake = make_fake_llm([decision])
    monkeypatch.setattr(arb_mod, "get_llm", lambda tier: fake)

    async def fake_run_debate(*a, **k):
        return [], [{"node": "risk_debate", "prompt_tokens": 0, "completion_tokens": 0,
                     "latency_s": 0.0, "cost_usd": 0.0, "model": ""}]
    monkeypatch.setattr(arb_mod, "run_debate", fake_run_debate)

    calls = []

    async def _record_verdict(ticker, dec):
        calls.append((ticker, dec))

    monkeypatch.setattr(arb_mod, "store_verdict", _record_verdict)

    await arb_mod.risk_arbiter(_base_state())

    assert len(calls) == 1
    ticker, dec = calls[0]
    assert ticker == "AAPL"
    # store_verdict receives a FinalDecision instance (per WP-C signature)
    assert isinstance(dec, FinalDecision)
    assert dec.action == "BUY"


@pytest.mark.asyncio
async def test_arbiter_respects_risk_debate_rounds(monkeypatch, make_fake_llm):
    decision = FinalDecision(action="HOLD", conviction=0.5, score=50, rationale="x")
    fake = make_fake_llm([decision])
    monkeypatch.setattr(arb_mod, "get_llm", lambda tier: fake)

    captured = {}

    async def fake_run_debate(topic, context, personas, rounds, tier="deep", node_label="debate", **kwargs):
        captured["rounds"] = rounds
        captured["personas"] = [p[0] for p in personas]
        return [], [{"node": node_label, "prompt_tokens": 0, "completion_tokens": 0,
                     "latency_s": 0.0, "cost_usd": 0.0, "model": ""}]
    monkeypatch.setattr(arb_mod, "run_debate", fake_run_debate)
    monkeypatch.setattr(arb_mod, "store_verdict", _noop_store_verdict)

    # Patch settings so risk_debate_rounds is a known value.
    class _S:
        risk_debate_rounds = 3
    monkeypatch.setattr(arb_mod, "get_settings", lambda: _S())

    await arb_mod.risk_arbiter(_base_state())

    assert captured["rounds"] == 3
    assert captured["personas"] == ["conservative", "aggressive"]


@pytest.mark.asyncio
async def test_arbiter_survives_missing_store_verdict(monkeypatch, make_fake_llm):
    """If WP-C is not merged, store_verdict is None; arbiter must still produce a decision."""
    decision = FinalDecision(action="SELL", conviction=0.6, score=30, rationale="x")
    fake = make_fake_llm([decision])
    monkeypatch.setattr(arb_mod, "get_llm", lambda tier: fake)

    async def fake_run_debate(*a, **k):
        return [], [{"node": "risk_debate", "prompt_tokens": 0, "completion_tokens": 0,
                     "latency_s": 0.0, "cost_usd": 0.0, "model": ""}]
    monkeypatch.setattr(arb_mod, "run_debate", fake_run_debate)
    monkeypatch.setattr(arb_mod, "store_verdict", None)  # simulate unavailable cache

    out = await arb_mod.risk_arbiter(_base_state())
    assert out["final_decision"]["action"] == "SELL"


@pytest.mark.asyncio
async def test_arbiter_survives_store_verdict_failure(monkeypatch, make_fake_llm, caplog):
    """Async store_verdict raising must not abort the node: the arbiter still returns a
    valid FinalDecision-shaped output, and the degrade warning keeps the traceback."""
    decision = FinalDecision(action="BUY", conviction=0.7, score=70, rationale="ok")
    fake = make_fake_llm([decision])
    monkeypatch.setattr(arb_mod, "get_llm", lambda tier: fake)

    async def fake_run_debate(*a, **k):
        return [], [{"node": "risk_debate", "prompt_tokens": 0, "completion_tokens": 0,
                     "latency_s": 0.0, "cost_usd": 0.0, "model": ""}]
    monkeypatch.setattr(arb_mod, "run_debate", fake_run_debate)

    async def _boom_store_verdict(*a, **k):
        raise RuntimeError("db down")

    monkeypatch.setattr(arb_mod, "store_verdict", _boom_store_verdict)

    with caplog.at_level(logging.WARNING, logger="src.agents.risk.arbiter"):
        out = await arb_mod.risk_arbiter(_base_state())  # must not raise

    fd = out["final_decision"]
    assert fd == decision.model_dump()
    assert fd["action"] in {"BUY", "SELL", "HOLD"}
    assert isinstance(out["risk_debate"]["adjustments"], list)
    # The store-failure warning must carry the traceback (exc_info) for diagnosis.
    store_warnings = [r for r in caplog.records if "store_verdict failed" in r.getMessage()]
    assert store_warnings, "expected a store-failure degrade warning"
    assert store_warnings[0].exc_info is not None


@pytest.mark.asyncio
async def test_arbiter_metrics_include_debate_and_arbiter(monkeypatch, make_fake_llm):
    decision = FinalDecision(action="HOLD", conviction=0.5, score=50, rationale="x")
    fake = make_fake_llm([decision])
    monkeypatch.setattr(arb_mod, "get_llm", lambda tier: fake)

    async def fake_run_debate(*a, **k):
        return [], [{"node": "risk_debate", "prompt_tokens": 1, "completion_tokens": 1,
                     "latency_s": 0.0, "cost_usd": 0.0, "model": ""}]
    monkeypatch.setattr(arb_mod, "run_debate", fake_run_debate)
    monkeypatch.setattr(arb_mod, "store_verdict", _noop_store_verdict)

    out = await arb_mod.risk_arbiter(_base_state())
    nodes = {m["node"] for m in out["run_metrics"]}
    assert "risk_debate" in nodes        # from run_debate
    assert "risk_arbiter" in nodes       # from the arbiter's own decision call

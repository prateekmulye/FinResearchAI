# tests/agents/test_risk_personas.py
import pytest

from src.agents.risk import conservative as cons_mod
from src.agents.risk import aggressive as aggr_mod
from src.agents.risk.conservative import RiskStance


@pytest.mark.asyncio
async def test_conservative_writes_conservative_key(monkeypatch, make_fake_llm):
    stance = RiskStance(stance="Trim size; valuation risk into earnings.")
    fake = make_fake_llm([stance])
    monkeypatch.setattr(cons_mod, "get_llm", lambda tier: fake)

    state = {
        "resolved_ticker": "AAPL",
        "trade_proposal": {"action": "BUY", "conviction": 0.8, "score": 74, "rationale": "r"},
    }
    out = await cons_mod.risk_conservative(state)

    assert set(out["risk_debate"]) == {"conservative"}
    assert out["risk_debate"]["conservative"] == "Trim size; valuation risk into earnings."
    assert out["run_metrics"][0]["node"] == "risk_conservative"
    assert fake.structured_args[0]["schema"] is RiskStance
    assert fake.structured_args[0]["method"] == "function_calling"


@pytest.mark.asyncio
async def test_aggressive_writes_aggressive_key(monkeypatch, make_fake_llm):
    from src.agents.risk.aggressive import RiskStance as AggrStance
    stance = AggrStance(stance="Press the position; momentum favors upside.")
    fake = make_fake_llm([stance])
    monkeypatch.setattr(aggr_mod, "get_llm", lambda tier: fake)

    state = {
        "resolved_ticker": "AAPL",
        "trade_proposal": {"action": "BUY", "conviction": 0.8, "score": 74, "rationale": "r"},
    }
    out = await aggr_mod.risk_aggressive(state)

    assert set(out["risk_debate"]) == {"aggressive"}
    assert out["risk_debate"]["aggressive"] == "Press the position; momentum favors upside."
    assert out["run_metrics"][0]["node"] == "risk_aggressive"


@pytest.mark.asyncio
async def test_personas_write_disjoint_keys_for_merge_reducer(monkeypatch, make_fake_llm):
    """conservative + aggressive run in parallel; they must write different sub-keys
    so merge_named_reports combines them without conflict."""
    cons_fake = make_fake_llm([cons_mod.RiskStance(stance="careful")])
    aggr_fake = make_fake_llm([aggr_mod.RiskStance(stance="bold")])
    monkeypatch.setattr(cons_mod, "get_llm", lambda tier: cons_fake)
    monkeypatch.setattr(aggr_mod, "get_llm", lambda tier: aggr_fake)

    proposal = {"action": "HOLD", "conviction": 0.5, "score": 50, "rationale": "r"}
    c = await cons_mod.risk_conservative({"trade_proposal": proposal})
    a = await aggr_mod.risk_aggressive({"trade_proposal": proposal})

    from src.state import merge_named_reports
    merged = merge_named_reports(c["risk_debate"], a["risk_debate"])
    assert merged == {"conservative": "careful", "aggressive": "bold"}

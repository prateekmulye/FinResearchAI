# tests/test_research_nodes.py
"""Unit tests for WP-D research nodes: bull, bear, facilitator, research_synthesis."""
from __future__ import annotations

import pytest

from src.llm.schemas import DebateTurn


def _synthetic_state() -> dict:
    """A minimal AgentState with synthetic analyst_reports injected."""
    return {
        "ticker": "AAPL",
        "resolved_ticker": "AAPL",
        "investor_mode": "Neutral",
        "analyst_reports": {
            "news": {"summary": "positive product cycle", "confidence": 0.7},
            "fundamentals": {"summary": "strong margins, rich valuation", "confidence": 0.6},
            "technicals": {"summary": "RSI 62, uptrend", "confidence": 0.55},
        },
    }


@pytest.mark.asyncio
async def test_bull_writes_thesis_and_metrics(fake_llm_factory):
    fake_llm_factory(
        [DebateTurn(role="bull", round=1, argument="growth runway is underpriced")],
        ["src.agents.research.bull"],
    )
    from src.agents.research.bull import bull

    out = await bull(_synthetic_state())
    assert out["research_debate"]["bull_thesis"] == "growth runway is underpriced"
    assert len(out["run_metrics"]) == 1
    assert out["run_metrics"][0]["node"] == "bull"


@pytest.mark.asyncio
async def test_bear_writes_thesis_and_metrics(fake_llm_factory):
    fake_llm_factory(
        [DebateTurn(role="bear", round=1, argument="valuation leaves no margin of safety")],
        ["src.agents.research.bear"],
    )
    from src.agents.research.bear import bear

    out = await bear(_synthetic_state())
    assert out["research_debate"]["bear_thesis"] == "valuation leaves no margin of safety"
    assert out["run_metrics"][0]["node"] == "bear"


@pytest.mark.asyncio
async def test_facilitator_runs_debate_and_writes_full_research_debate(fake_llm_factory):
    # 1 round x 2 personas = 2 debate turns, then 1 verdict turn.
    fake_llm_factory(
        [
            DebateTurn(role="bull", round=1, argument="bull rebuttal"),
            DebateTurn(role="bear", round=1, argument="bear rebuttal"),
            DebateTurn(role="bull", round=1, argument="On balance, lean BUY: growth outweighs valuation."),
        ],
        ["src.agents.debate", "src.agents.research.facilitator"],
    )
    from src.agents.research.facilitator import facilitator

    state = _synthetic_state()
    # Bull/bear already wrote their theses upstream (merged into research_debate):
    state["research_debate"] = {"bull_thesis": "bull case", "bear_thesis": "bear case"}

    out = await facilitator(state)
    rd = out["research_debate"]
    assert rd["facilitator_verdict"]  # non-empty
    assert len(rd["rounds"]) == 2  # the debate turns
    assert rd["rounds"][0]["role"] == "bull"
    # F4: facilitator writes ONLY rounds + facilitator_verdict; it does NOT re-emit
    # bull_thesis/bear_thesis so the merge reducer preserves the upstream values.
    assert "bull_thesis" not in rd
    assert "bear_thesis" not in rd
    # metrics from the debate (node_label="research_debate") + the facilitator verdict call
    nodes = {m["node"] for m in out["run_metrics"]}
    assert "facilitator" in nodes
    assert "research_debate" in nodes


@pytest.mark.asyncio
async def test_facilitator_merge_preserves_bull_and_bear_theses(fake_llm_factory):
    """After bull→bear→facilitator the merged research_debate retains all three fields.

    Simulates the merge_named_reports reducer by applying bull, bear, and facilitator
    outputs in sequence (as LangGraph would) and asserting the final merged dict has
    bull_thesis, bear_thesis, AND facilitator_verdict all non-empty.
    """
    from src.state import merge_named_reports

    # bull: 1 call, bear: 1 call, facilitator: 2 debate turns + 1 verdict = 5 total
    fake_llm_factory(
        [
            DebateTurn(role="bull", round=1, argument="strong growth runway"),   # bull node
            DebateTurn(role="bear", round=1, argument="valuation risk is real"), # bear node
            DebateTurn(role="bull", round=1, argument="debate bull rebuttal"),   # facilitator debate turn 1
            DebateTurn(role="bear", round=1, argument="debate bear rebuttal"),   # facilitator debate turn 2
            DebateTurn(role="bull", round=1, argument="lean BUY on balance"),    # facilitator verdict
        ],
        ["src.agents.debate", "src.agents.research.bull",
         "src.agents.research.bear", "src.agents.research.facilitator"],
    )
    from src.agents.research.bull import bull
    from src.agents.research.bear import bear
    from src.agents.research.facilitator import facilitator

    state = _synthetic_state()

    bull_out = await bull(state)
    bear_out = await bear(state)

    # Simulate the merge reducer: accumulate research_debate as LangGraph would.
    merged_rd = merge_named_reports({}, bull_out["research_debate"])
    merged_rd = merge_named_reports(merged_rd, bear_out["research_debate"])

    # Feed merged state to facilitator (it reads bull_thesis/bear_thesis from state).
    state["research_debate"] = merged_rd
    fac_out = await facilitator(state)

    # Final merge: apply facilitator's partial dict onto the accumulated state.
    final_rd = merge_named_reports(merged_rd, fac_out["research_debate"])

    assert final_rd["bull_thesis"], "bull_thesis must survive the merge"
    assert final_rd["bear_thesis"], "bear_thesis must survive the merge"
    assert final_rd["facilitator_verdict"], "facilitator_verdict must be non-empty"


@pytest.mark.asyncio
async def test_research_synthesis_writes_verdict_only(fake_llm_factory):
    fake_llm_factory(
        [DebateTurn(role="bull", round=1, argument="Single-pass verdict: lean BUY.")],
        ["src.agents.research.synthesis"],
    )
    from src.agents.research.synthesis import research_synthesis

    out = await research_synthesis(_synthetic_state())
    rd = out["research_debate"]
    assert rd["facilitator_verdict"] == "Single-pass verdict: lean BUY."
    # baseline does NOT manufacture bull/bear theses or rounds
    assert rd.get("bull_thesis", "") == ""
    assert rd.get("bear_thesis", "") == ""
    assert rd.get("rounds", []) == []
    assert out["run_metrics"][0]["node"] == "research_synthesis"

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
    # carried forward from upstream merge (facilitator preserves them)
    assert rd["bull_thesis"] == "bull case"
    assert rd["bear_thesis"] == "bear case"
    # metrics from the debate (node_label="research_debate") + the facilitator verdict call
    nodes = {m["node"] for m in out["run_metrics"]}
    assert "facilitator" in nodes
    assert "research_debate" in nodes


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

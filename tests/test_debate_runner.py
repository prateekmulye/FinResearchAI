# tests/test_debate_runner.py
"""Tests for the shared run_debate bounded-debate runner (WP-D)."""
from __future__ import annotations

import pytest

from src.llm.schemas import DebateTurn


@pytest.mark.asyncio
async def test_run_debate_respects_round_count(fake_llm_factory):
    # 2 rounds x 2 personas = 4 turns expected
    scripted = [
        DebateTurn(role="bull", round=1, argument="b1"),
        DebateTurn(role="bear", round=1, argument="r1"),
        DebateTurn(role="bull", round=2, argument="b2"),
        DebateTurn(role="bear", round=2, argument="r2"),
    ]
    fake_llm_factory(scripted, ["src.agents.debate"])
    from src.agents.debate import run_debate

    personas = [("bull", "you are bullish"), ("bear", "you are bearish")]
    turns, metrics = await run_debate(
        topic="AAPL", context="reports...", personas=personas, rounds=2, node_label="research_debate"
    )
    assert len(turns) == 4
    assert all(isinstance(t, DebateTurn) for t in turns)


@pytest.mark.asyncio
async def test_run_debate_turns_alternate_roles(fake_llm_factory):
    scripted = [
        DebateTurn(role="bull", round=1, argument="x"),
        DebateTurn(role="bear", round=1, argument="x"),
        DebateTurn(role="bull", round=2, argument="x"),
        DebateTurn(role="bear", round=2, argument="x"),
    ]
    fake_llm_factory(scripted, ["src.agents.debate"])
    from src.agents.debate import run_debate

    personas = [("bull", "p1"), ("bear", "p2")]
    turns, _ = await run_debate("AAPL", "ctx", personas, rounds=2, node_label="research_debate")
    assert [t.role for t in turns] == ["bull", "bear", "bull", "bear"]
    assert [t.round for t in turns] == [1, 1, 2, 2]


@pytest.mark.asyncio
async def test_run_debate_aggregates_metrics_under_node_label(fake_llm_factory):
    scripted = [
        DebateTurn(role="bull", round=1, argument="x"),
        DebateTurn(role="bear", round=1, argument="x"),
    ]
    fake_llm_factory(scripted, ["src.agents.debate"])
    from src.agents.debate import run_debate

    personas = [("bull", "p1"), ("bear", "p2")]
    _, metrics = await run_debate("AAPL", "ctx", personas, rounds=1, node_label="research_debate")
    # one metric record per LLM call, all under the same node label
    assert len(metrics) == 2
    assert all(m["node"] == "research_debate" for m in metrics)
    assert sum(m["prompt_tokens"] for m in metrics) == 20


@pytest.mark.asyncio
async def test_run_debate_min_one_round(fake_llm_factory):
    scripted = [
        DebateTurn(role="bull", round=1, argument="x"),
        DebateTurn(role="bear", round=1, argument="x"),
    ]
    fake_llm_factory(scripted, ["src.agents.debate"])
    from src.agents.debate import run_debate

    # rounds=0 is clamped to a single round (never an empty debate)
    turns, _ = await run_debate("AAPL", "ctx", [("bull", "p1"), ("bear", "p2")], rounds=0)
    assert len(turns) == 2

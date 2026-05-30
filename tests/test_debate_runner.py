# tests/test_debate_runner.py
"""Tests for the shared run_debate bounded-debate runner (WP-D).
Also covers conftest strictness (F6).
"""
from __future__ import annotations

import pytest

from src.llm.schemas import DebateTurn


def test_conftest_raises_for_unregistered_schema():
    """make_structured_llm raises KeyError for any schema not in _KNOWN_SCHEMAS. F6."""
    from conftest import make_structured_llm

    class _UnknownSchema:
        pass

    llm = make_structured_llm([])
    with pytest.raises(KeyError, match="no canned instance registered for"):
        llm.with_structured_output(_UnknownSchema)


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

    # rounds=0 is clamped to a single round (never an empty debate) — F3
    turns, _ = await run_debate("AAPL", "ctx", [("bull", "p1"), ("bear", "p2")], rounds=0)
    assert len(turns) == 2


@pytest.mark.asyncio
async def test_run_debate_rounds_capped_at_max_rounds(fake_llm_factory, caplog):
    """rounds > max_rounds is silently capped; turn count reflects max_rounds, not rounds. F3."""
    import logging

    # max_rounds=2, rounds=99 → only 2 rounds x 2 personas = 4 turns
    scripted = [
        DebateTurn(role="bull", round=1, argument="b1"),
        DebateTurn(role="bear", round=1, argument="r1"),
        DebateTurn(role="bull", round=2, argument="b2"),
        DebateTurn(role="bear", round=2, argument="r2"),
    ]
    fake_llm_factory(scripted, ["src.agents.debate"])
    from src.agents.debate import run_debate

    personas = [("bull", "p1"), ("bear", "p2")]
    with caplog.at_level(logging.WARNING, logger="src.agents.debate"):
        turns, _ = await run_debate(
            "AAPL", "ctx", personas, rounds=99, max_rounds=2, node_label="research_debate"
        )

    # Turn count must reflect max_rounds=2, not the requested 99
    assert len(turns) == 4  # 2 rounds × 2 personas
    # The cap warning must have been emitted
    assert any("capped" in r.message for r in caplog.records)


@pytest.mark.asyncio
async def test_run_debate_none_turn_skipped(fake_llm_factory):
    """If a turn returns None (weak model / parse failure) it is skipped. F1."""
    # Provide one real turn and one None; only the real turn should be in results.
    scripted = [
        None,  # simulates a weak model returning no parseable output
        DebateTurn(role="bear", round=1, argument="bear arg"),
    ]
    fake_llm_factory(scripted, ["src.agents.debate"])
    from src.agents.debate import run_debate

    personas = [("bull", "p1"), ("bear", "p2")]
    turns, metrics = await run_debate(
        "AAPL", "ctx", personas, rounds=1, node_label="research_debate"
    )
    # None turn was skipped; only the bear turn survives
    assert len(turns) == 1
    assert turns[0].role == "bear"
    # Both LLM calls still fired and were tracked (metrics count = 2)
    assert len(metrics) == 2

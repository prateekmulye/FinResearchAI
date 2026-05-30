# tests/test_research_live.py
"""Opt-in live integration test for WP-D (set RUN_LIVE=1 to run).

Verifies the configured deep model actually returns structured DebateTurn objects
via the method declared in STRUCT_METHOD (default: "function_calling"). If this
test fails with a tool-calling / function-calling unsupported error, change
STRUCT_METHOD to "json_schema" in src/llm/factory.py and re-run.
"""
from __future__ import annotations

import os

import pytest

pytestmark = pytest.mark.live


@pytest.mark.skipif(os.environ.get("RUN_LIVE") != "1", reason="set RUN_LIVE=1 to run")
@pytest.mark.asyncio
async def test_run_debate_live_returns_structured_turns():
    """Live probe: run_debate calls the real Ollama Cloud deep model and returns
    DebateTurn objects. Confirms function_calling / json_schema method choice."""
    from src.agents.debate import run_debate

    personas = [
        ("bull", "Argue to BUY, one sentence."),
        ("bear", "Argue to SELL, one sentence."),
    ]
    turns, metrics = await run_debate(
        topic="AAPL",
        context="Strong margins; rich valuation; uptrend.",
        personas=personas,
        rounds=1,
        node_label="research_debate",
    )
    assert len(turns) == 2
    assert all(t.argument for t in turns)
    assert sum(m["completion_tokens"] for m in metrics) > 0

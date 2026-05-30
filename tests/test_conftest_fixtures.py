# tests/test_conftest_fixtures.py
"""Self-tests for the WP-I shared fixtures added to tests/conftest.py:
``env_isolation`` (autouse), ``fake_llm`` (schema-routed factory), ``frozen_state``.
"""
import os

import pytest

from src.llm.factory import get_llm
from src.llm.schemas import AnalystReport, TradeProposal


def test_env_isolation_clears_keys_and_disables_live():
    # The autouse env-isolation fixture must clear provider keys and force RUN_LIVE off.
    assert os.environ.get("RUN_LIVE", "0") == "0"
    assert os.environ.get("OLLAMA_API_KEY", "") == ""
    assert os.environ.get("FIRECRAWL_API_KEY", "") == ""


def test_frozen_state_is_fully_populated(frozen_state):
    s = frozen_state()
    assert s["ticker"]
    assert s["resolved_ticker"]
    assert set(s["analyst_reports"]) == {"news", "fundamentals", "technicals"}
    assert s["trade_proposal"]["action"] in {"BUY", "SELL", "HOLD"}
    assert s["final_decision"]["score"] == 50
    assert isinstance(s["run_metrics"], list)


@pytest.mark.asyncio
async def test_fake_llm_returns_supplied_pydantic_instance(fake_llm):
    proposal = TradeProposal(action="BUY", conviction=0.8, score=72, rationale="mocked")
    fake_llm(proposal)  # patches get_llm globally for this test
    llm = get_llm("deep").with_structured_output(TradeProposal, method="function_calling")
    result = await llm.ainvoke([{"role": "user", "content": "x"}], config={"callbacks": []})
    assert result is proposal
    assert result.action == "BUY"


@pytest.mark.asyncio
async def test_fake_llm_routes_by_schema(fake_llm):
    # Register multiple schema->instance mappings; the fake returns the right one per schema.
    report = AnalystReport(summary="news summary", confidence=0.7)
    proposal = TradeProposal(action="HOLD", conviction=0.5, score=50, rationale="r")
    fake_llm({AnalystReport: report, TradeProposal: proposal})

    a = await get_llm("quick").with_structured_output(AnalystReport).ainvoke("p")
    p = await get_llm("deep").with_structured_output(TradeProposal).ainvoke("p")
    assert a is report
    assert p is proposal

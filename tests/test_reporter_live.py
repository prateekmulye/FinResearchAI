# tests/test_reporter_live.py
"""Opt-in live test for the reporter node — requires RUN_LIVE=1 and valid API keys.

Verifies that the quick model returns a valid ReportPayload via real Ollama Cloud.
If this fails with a tool-calling error, flip STRUCT_METHOD to 'json_schema' in
src/llm/factory.py (the single shared knob per COORDINATION §7.5) and re-run.
"""
import os

import pytest

pytestmark = pytest.mark.skipif(
    os.getenv("RUN_LIVE") != "1", reason="live test; set RUN_LIVE=1 to run"
)


@pytest.mark.live
@pytest.mark.asyncio
async def test_reporter_live_structured_output():
    """Confirms the quick model returns a valid ReportPayload via real Ollama Cloud."""
    from src.agents.reporter import reporter

    state = {
        "ticker": "AAPL",
        "resolved_ticker": "AAPL",
        "investor_mode": "Neutral",
        "analyst_reports": {
            "fundamentals": {
                "summary": "Healthy margins",
                "key_points": ["FCF up"],
                "data": {"pe": 28},
                "confidence": 0.6,
                "citations": [],
            }
        },
        "research_debate": {"facilitator_verdict": "Lean bull"},
        "trade_proposal": {"action": "BUY", "conviction": 0.7, "score": 70, "rationale": "x"},
        "risk_debate": {"arbiter_decision": "moderate"},
        "final_decision": {"action": "BUY", "conviction": 0.72, "score": 71, "rationale": "ok"},
        "run_metrics": [],
    }
    out = await reporter(state)
    assert "AAPL" in out["final_report"]
    assert set(out["financial_data"]) >= {"valuation", "growth", "risk"}
    # a real call should record nonzero tokens for the reporter node
    assert any(m["node"] == "reporter" for m in out["run_metrics"])

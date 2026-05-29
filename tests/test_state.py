# tests/test_state.py
from src.state import merge_named_reports, AgentState


def test_merge_named_reports_combines_parallel_writes():
    left = {"news": {"summary": "n"}}
    right = {"fundamentals": {"summary": "f"}}
    merged = merge_named_reports(left, right)
    assert set(merged) == {"news", "fundamentals"}


def test_merge_named_reports_right_wins_on_key_conflict():
    assert merge_named_reports({"news": {"v": 1}}, {"news": {"v": 2}})["news"]["v"] == 2


def test_merge_named_reports_handles_none():
    assert merge_named_reports(None, {"a": 1}) == {"a": 1}
    assert merge_named_reports({"a": 1}, None) == {"a": 1}


def test_agentstate_is_typeddict_with_expected_keys():
    # __annotations__ exposes the declared fields of a TypedDict
    keys = set(AgentState.__annotations__)
    for expected in [
        "ticker", "resolved_ticker", "analyst_reports", "research_debate",
        "trade_proposal", "risk_debate", "final_decision", "final_report",
        "run_metrics", "run_id",
    ]:
        assert expected in keys

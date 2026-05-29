# tests/test_graph_skeleton.py
from src.graph import build_graph


def test_graph_compiles():
    assert build_graph() is not None


def test_graph_runs_end_to_end():
    app = build_graph()
    result = app.invoke({"ticker": "AAPL", "investor_mode": "Neutral"})
    assert result["resolved_ticker"]  # router ran
    assert "final_report" in result  # reporter ran
    assert result["final_decision"]["action"] in {"BUY", "SELL", "HOLD"}


def test_graph_merges_three_parallel_analysts():
    app = build_graph()
    result = app.invoke({"ticker": "AAPL", "investor_mode": "Neutral"})
    assert set(result["analyst_reports"]) == {"news", "fundamentals", "technicals"}


def test_graph_accumulates_run_metrics():
    app = build_graph()
    result = app.invoke({"ticker": "AAPL", "investor_mode": "Neutral"})
    # every node appends one metric record
    assert len(result["run_metrics"]) == 12

import json

import pytest

from src.api.stream import _node_from_messages_meta, analyze_event_stream


async def _collect(gen):
    return [ev async for ev in gen]


@pytest.mark.asyncio
async def test_stream_starts_and_ends_with_done(offline_graph):
    events = await _collect(
        analyze_event_stream(
            ticker="AAPL", investor_mode="Neutral", debate_mode="on", run_id="run-x"
        )
    )
    names = [e["event"] for e in events]
    assert names[0] == "start"
    assert names[-1] == "done"


@pytest.mark.asyncio
async def test_stream_emits_node_complete_for_every_stub_node(offline_graph):
    events = await _collect(
        analyze_event_stream(
            ticker="AAPL", investor_mode="Neutral", debate_mode="on", run_id="run-y"
        )
    )
    completed = {
        json.loads(e["data"])["node"] for e in events if e["event"] == "node_complete"
    }
    # The 12-node stub graph: every node reports completion.
    assert {
        "router",
        "news_analyst",
        "fundamentals_analyst",
        "technicals_analyst",
        "bull",
        "bear",
        "facilitator",
        "trader",
        "risk_conservative",
        "risk_aggressive",
        "risk_arbiter",
        "reporter",
    } <= completed


@pytest.mark.asyncio
async def test_done_event_carries_report_decision_and_metrics(offline_graph):
    events = await _collect(
        analyze_event_stream(
            ticker="AAPL", investor_mode="Neutral", debate_mode="on", run_id="run-z"
        )
    )
    done = json.loads(events[-1]["data"])
    assert done["type"] == "done"
    assert done["run_id"] == "run-z"
    assert isinstance(done["final_report"], str) and done["final_report"]
    assert done["final_decision"]["action"] in {"BUY", "SELL", "HOLD"}
    # "on" topology = 12 nodes -> at least one metric per node. The real facilitator
    # contributes extra entries (debate turns + verdict), so assert >= 12.
    assert len(done["run_metrics"]) >= 12


@pytest.mark.asyncio
async def test_every_event_data_is_json_with_run_id(offline_graph):
    events = await _collect(
        analyze_event_stream(
            ticker="AAPL", investor_mode="Neutral", debate_mode="on", run_id="run-q"
        )
    )
    for e in events:
        payload = json.loads(e["data"])
        assert payload["run_id"] == "run-q"
        assert payload["type"] == e["event"]


@pytest.mark.asyncio
async def test_stream_emits_error_event_on_graph_failure(monkeypatch):
    import src.api.stream as stream_mod

    def boom(*a, **k):
        raise RuntimeError("kaboom")

    # _compiled_graph memoizes per debate_mode; clear it so the patched build_graph
    # is actually invoked instead of a graph cached by an earlier test.
    stream_mod._compiled_graph.cache_clear()
    monkeypatch.setattr(stream_mod, "build_graph", boom)
    events = await _collect(
        analyze_event_stream(
            ticker="AAPL", investor_mode="Neutral", debate_mode="on", run_id="run-e"
        )
    )
    assert events[-1]["event"] == "error"
    assert "kaboom" in json.loads(events[-1]["data"])["message"]


def test_node_from_messages_meta_reads_langgraph_node():
    assert _node_from_messages_meta({"langgraph_node": "bull"}) == "bull"
    assert _node_from_messages_meta({}) == "unknown"

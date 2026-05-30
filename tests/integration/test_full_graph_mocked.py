# tests/integration/test_full_graph_mocked.py
"""End-to-end composition test: the REAL compiled graph for both debate modes,
with every LLM call mocked and every tool SDK monkeypatched (via the shared
``offline_graph`` fixture in tests/conftest.py).

This is the 'does the whole system compose' test. It does NOT assert on the
*content quality* of nodes (that is each WP's unit-test job) — it asserts the
graph runs to completion, every contract field is present and shaped correctly,
and metrics accumulate: every graph node emits its per-node metric line.

Metric expectation (COORDINATION.md §7.4 + reality):
  "on"  topology  = 12 graph nodes, each appending >= 1 metric record. The
                    deep-debate (facilitator) and risk (arbiter) nodes ALSO run a
                    bounded sub-debate via run_debate which appends extra records
                    labelled "research_debate" / "risk_debate". So we assert the 12
                    node LABELS are all present (coverage), NOT a brittle exact count.
  "off" topology  = 10 graph nodes (bull/bear/facilitator replaced by a single
                    research_synthesis node). Same coverage assertion on 10 labels.
"""
from __future__ import annotations

import pytest

from src.graph import build_graph

# The graph-node metric labels each mode MUST emit (COORDINATION.md §7.4).
EXPECTED_NODE_LABELS = {
    "on": {
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
    },
    "off": {
        "router",
        "news_analyst",
        "fundamentals_analyst",
        "technicals_analyst",
        "research_synthesis",
        "trader",
        "risk_conservative",
        "risk_aggressive",
        "risk_arbiter",
        "reporter",
    },
}
EXPECTED_NODE_COUNT = {"on": 12, "off": 10}

_METRIC_KEYS = {"node", "prompt_tokens", "completion_tokens", "latency_s", "cost_usd"}


@pytest.mark.asyncio
@pytest.mark.parametrize("mode", ["on", "off"])
async def test_full_graph_composes_for_both_modes(mode, offline_graph):
    app = build_graph(mode)

    result = await app.ainvoke({"ticker": "AAPL", "investor_mode": "Neutral"})

    # Router ran and resolved the ticker.
    assert result.get("resolved_ticker"), "router did not run / resolve ticker"

    # All three analysts wrote reports, merged by name.
    assert set(result["analyst_reports"]) == {"news", "fundamentals", "technicals"}

    # Research debate produced a facilitator verdict in BOTH modes.
    assert result["research_debate"]["facilitator_verdict"], "no facilitator verdict"

    # Trader proposal survived into state (not silently dropped).
    tp = result["trade_proposal"]
    assert tp["action"] in {"BUY", "SELL", "HOLD"}

    # Risk personas both wrote their stance (merge reducer kept both sub-keys).
    rd = result["risk_debate"]
    assert rd.get("conservative") and rd.get("aggressive"), "risk stances dropped"

    # Trader + risk arbiter produced a coherent final decision.
    fd = result["final_decision"]
    assert fd["action"] in {"BUY", "SELL", "HOLD"}
    assert 0 <= fd["score"] <= 100
    assert 0.0 <= fd["conviction"] <= 1.0

    # Reporter produced a non-empty markdown report.
    assert isinstance(result["final_report"], str)
    assert result["final_report"].strip(), "empty final_report"
    assert result["final_report"].lstrip().startswith("#"), "report is not markdown"

    # Every graph node emitted at least one metric record (label coverage).
    emitted = {m["node"] for m in result["run_metrics"]}
    missing = EXPECTED_NODE_LABELS[mode] - emitted
    assert not missing, f"{mode!r} mode missing metric lines for nodes: {missing}"
    assert len(EXPECTED_NODE_LABELS[mode]) == EXPECTED_NODE_COUNT[mode]

    # Every metric record has the contract shape.
    for m in result["run_metrics"]:
        assert _METRIC_KEYS <= set(m), f"metric record missing keys: {m}"


@pytest.mark.asyncio
async def test_on_and_off_modes_differ_in_node_count(offline_graph):
    on = await build_graph("on").ainvoke({"ticker": "AAPL", "investor_mode": "Neutral"})
    off = await build_graph("off").ainvoke({"ticker": "AAPL", "investor_mode": "Neutral"})

    on_nodes = {m["node"] for m in on["run_metrics"]} & EXPECTED_NODE_LABELS["on"]
    off_nodes = {m["node"] for m in off["run_metrics"]} & EXPECTED_NODE_LABELS["off"]
    assert len(on_nodes) > len(off_nodes), (
        "off-mode (research_synthesis bypass) should run fewer graph nodes than on-mode "
        f"(on={sorted(on_nodes)}, off={sorted(off_nodes)})"
    )
    # The off-mode synthesis node replaces bull/bear/facilitator.
    assert "research_synthesis" in {m["node"] for m in off["run_metrics"]}
    assert {"bull", "bear", "facilitator"} <= {m["node"] for m in on["run_metrics"]}

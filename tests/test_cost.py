# tests/test_cost.py
from types import SimpleNamespace
from src.llm.cost import CostTracker, PRICING


def _fake_response(prompt_tokens, completion_tokens, model):
    return SimpleNamespace(
        llm_output={
            "token_usage": {"prompt_tokens": prompt_tokens, "completion_tokens": completion_tokens},
            "model_name": model,
        }
    )


def test_cost_tracker_aggregates_tokens_and_latency():
    t = CostTracker(node="trader")
    rid = "run-1"
    t.on_llm_start({}, ["prompt"], run_id=rid)
    t.on_llm_end(_fake_response(100, 40, "gpt-oss:120b"), run_id=rid)
    totals = t.totals()
    assert totals["prompt_tokens"] == 100
    assert totals["completion_tokens"] == 40
    assert totals["latency_s"] >= 0.0
    assert len(totals["per_node"]) == 1
    assert totals["per_node"][0]["node"] == "trader"


def test_cost_tracker_uses_pricing_when_present(monkeypatch):
    monkeypatch.setitem(PRICING, "test-model", (1.0, 2.0))  # USD per 1M (in, out)
    t = CostTracker(node="x")
    t.on_llm_start({}, ["p"], run_id="r")
    t.on_llm_end(_fake_response(1_000_000, 1_000_000, "test-model"), run_id="r")
    # 1M in * $1 + 1M out * $2 = $3
    assert round(t.totals()["cost_usd"], 2) == 3.0


def test_cost_tracker_handles_missing_usage():
    t = CostTracker(node="x")
    t.on_llm_start({}, ["p"], run_id="r")
    t.on_llm_end(SimpleNamespace(llm_output=None), run_id="r")
    assert t.totals()["prompt_tokens"] == 0


def test_cost_tracker_handles_none_token_usage():
    t = CostTracker(node="x")
    t.on_llm_start({}, ["p"], run_id="r")
    t.on_llm_end(SimpleNamespace(llm_output={"token_usage": None, "model_name": "m"}), run_id="r")
    assert t.totals()["prompt_tokens"] == 0

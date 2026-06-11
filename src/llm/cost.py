# src/llm/cost.py
from __future__ import annotations

import time
from dataclasses import asdict, dataclass
from typing import Any

from langchain_core.callbacks import BaseCallbackHandler

# USD per 1,000,000 tokens as (input_rate, output_rate).
# Ollama Cloud billing is plan-based; default to 0.0 and override per model as needed.
PRICING: dict[str, tuple[float, float]] = {
    "gpt-oss:20b": (0.0, 0.0),
    "gpt-oss:120b": (0.0, 0.0),
}


@dataclass
class NodeCost:
    node: str
    model: str = ""
    prompt_tokens: int = 0
    completion_tokens: int = 0
    latency_s: float = 0.0
    cost_usd: float = 0.0


class CostTracker(BaseCallbackHandler):
    """LangChain callback that records token usage, latency, and cost per LLM call."""

    def __init__(self, node: str = "unknown") -> None:
        self.node = node
        self.records: list[NodeCost] = []
        # Keyed by run_id, which LangChain passes as a UUID (fakes pass str,
        # and it may be None) — honest typing is Any, not str | None.
        self._starts: dict[Any, float] = {}

    def on_llm_start(self, serialized, prompts, *, run_id=None, **kwargs) -> None:
        self._starts[run_id] = time.perf_counter()

    def on_llm_error(self, error, *, run_id=None, **kwargs) -> None:
        # A failed call never reaches on_llm_end; drop its start marker so the
        # tracker doesn't leak an entry. No cost record is added for a failed call.
        self._starts.pop(run_id, None)

    def on_llm_end(self, response, *, run_id=None, **kwargs) -> None:
        start = self._starts.pop(run_id, time.perf_counter())
        elapsed = time.perf_counter() - start
        out = getattr(response, "llm_output", None) or {}
        usage = (out.get("token_usage") or {}) if isinstance(out, dict) else {}
        model = out.get("model_name", "") if isinstance(out, dict) else ""
        pt = int(usage.get("prompt_tokens", 0) or 0)
        ct = int(usage.get("completion_tokens", 0) or 0)
        in_rate, out_rate = PRICING.get(model, (0.0, 0.0))
        cost = pt / 1_000_000 * in_rate + ct / 1_000_000 * out_rate
        self.records.append(NodeCost(self.node, model, pt, ct, round(elapsed, 4), round(cost, 6)))

    def totals(self) -> dict:
        return {
            "prompt_tokens": sum(r.prompt_tokens for r in self.records),
            "completion_tokens": sum(r.completion_tokens for r in self.records),
            "latency_s": round(sum(r.latency_s for r in self.records), 4),
            "cost_usd": round(sum(r.cost_usd for r in self.records), 6),
            "per_node": [asdict(r) for r in self.records],
        }

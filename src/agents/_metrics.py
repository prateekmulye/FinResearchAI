"""Shared zero-cost metrics helper.

All nodes return a ``run_metrics`` list of dicts. ``zero_metrics(node)``
produces the canonical zero-cost entry so every node (and the graph stubs)
emits the same record shape without drift.
"""
from __future__ import annotations


def zero_metrics(node: str) -> list[dict]:
    """Return a single-entry list representing a no-cost LLM call for *node*."""
    return [
        {
            "node": node,
            "model": "",
            "prompt_tokens": 0,
            "completion_tokens": 0,
            "latency_s": 0.0,
            "cost_usd": 0.0,
        }
    ]

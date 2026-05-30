"""Shared zero-cost metrics helper.

All analyst nodes and the router return a ``run_metrics`` list of dicts.
``zero_metrics(node)`` produces the canonical zero-cost entry so router +
analysts stay in sync without 4-way drift.
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

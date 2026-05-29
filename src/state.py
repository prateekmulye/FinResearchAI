# src/state.py
from __future__ import annotations

import operator
from typing import Annotated, Any, TypedDict


def merge_named_reports(left: dict | None, right: dict | None) -> dict:
    """Reducer for parallel analyst writes: shallow-merge by analyst name (right wins)."""
    out: dict[str, Any] = dict(left or {})
    out.update(right or {})
    return out


class AgentState(TypedDict, total=False):
    # --- control (Router) ---
    ticker: str
    resolved_ticker: str
    screener: str
    exchange: str
    investor_mode: str
    model_plan: dict

    # --- research (analysts write concurrently; merged by name) ---
    analyst_reports: Annotated[dict, merge_named_reports]

    # --- debate + decision (concurrent writers; merged by key) ---
    research_debate: Annotated[dict, merge_named_reports]
    risk_debate: Annotated[dict, merge_named_reports]

    # --- single-writer fields ---
    trade_proposal: dict
    final_decision: dict
    final_report: str

    # --- observability (accumulated across nodes) ---
    run_metrics: Annotated[list, operator.add]
    run_id: str

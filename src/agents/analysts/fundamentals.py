"""Fundamentals analyst: yfinance -> structured AnalystReport (quick tier).

The raw numeric fundamentals are attached to report.data so the reporter (WP-F)
can render charts without re-fetching.

STRUCT_METHOD is imported from src.llm.factory per COORDINATION §7.5.
"""
from __future__ import annotations

import asyncio
import warnings

from langchain_core.messages import HumanMessage, SystemMessage

from src.agents._metrics import zero_metrics
from src.llm.cost import CostTracker
from src.llm.factory import STRUCT_METHOD, get_llm
from src.llm.schemas import AnalystReport
from src.tools import ToolError
from src.tools.yfinance import fetch_fundamentals

_SYSTEM = """You are a fundamentals analyst. Given a company's financial metrics
(P/E, growth, margins, dividend, beta), summarize financial health, list 3-5 key
points, and give a confidence in [0,1]. Reason only from the numbers provided."""

_NODE = "fundamentals_analyst"


def _degraded(reason: str) -> AnalystReport:
    return AnalystReport(summary=f"Fundamentals unavailable: {reason}", confidence=0.0)


# Local alias kept for backward-compat; delegates to shared helper.
def _zero_metrics() -> list[dict]:
    return zero_metrics(_NODE)


async def fundamentals_analyst(state: dict) -> dict:
    tracker = CostTracker(_NODE)
    ticker = state.get("resolved_ticker") or state.get("ticker") or ""

    try:
        f = await asyncio.to_thread(fetch_fundamentals, ticker)
    except ToolError as exc:
        # Degraded path: no LLM call was made, return zero metrics silently.
        return {
            "analyst_reports": {"fundamentals": _degraded(str(exc)).model_dump()},
            "run_metrics": _zero_metrics(),
        }

    data = f.to_dict()
    llm = get_llm("quick").with_structured_output(AnalystReport, method=STRUCT_METHOD)
    messages = [
        SystemMessage(content=_SYSTEM),
        HumanMessage(content=f"Ticker: {ticker}\nMetrics: {data}"),
    ]
    try:
        report: AnalystReport = await llm.ainvoke(messages, config={"callbacks": [tracker]})
    except Exception as exc:  # LLM failure degrades gracefully
        return {
            "analyst_reports": {"fundamentals": _degraded(f"LLM error: {exc}").model_dump()},
            "run_metrics": _zero_metrics(),
        }

    # Attach raw numbers for the reporter; preserve any LLM-provided data too.
    merged = {**data, **(report.data or {})}
    report = report.model_copy(update={"data": merged})

    # Happy path: an LLM call was made; warn if no cost was recorded.
    per_node = tracker.totals()["per_node"]
    if not per_node:
        warnings.warn(
            f"{_NODE}: no LLM cost recorded; on_llm_end may not have fired",
            stacklevel=2,
        )
        per_node = _zero_metrics()
    return {
        "analyst_reports": {"fundamentals": report.model_dump()},
        "run_metrics": per_node,
    }

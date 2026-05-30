"""Technicals analyst: tradingview-ta -> structured AnalystReport (quick tier).

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
from src.tools.tradingview import fetch_technicals

_SYSTEM = """You are a technical analyst. Given TradingView signals (overall
recommendation, buy/neutral/sell counts, RSI, MACD), summarize the technical
posture, list 3-5 key points, and give a confidence in [0,1]. Reason only from
the indicators provided."""

_NODE = "technicals_analyst"


def _degraded(reason: str) -> AnalystReport:
    return AnalystReport(summary=f"Technicals unavailable: {reason}", confidence=0.0)


# Local alias kept for backward-compat; delegates to shared helper.
def _zero_metrics() -> list[dict]:
    return zero_metrics(_NODE)


async def technicals_analyst(state: dict) -> dict:
    tracker = CostTracker(_NODE)
    ticker = state.get("resolved_ticker") or state.get("ticker") or ""
    screener = state.get("screener", "america")
    exchange = state.get("exchange", "NASDAQ")

    try:
        t = await asyncio.to_thread(fetch_technicals, ticker, screener, exchange)
    except ToolError as exc:
        # Degraded path: no LLM call was made, return zero metrics silently.
        return {
            "analyst_reports": {"technicals": _degraded(str(exc)).model_dump()},
            "run_metrics": _zero_metrics(),
        }

    data = t.to_dict()
    llm = get_llm("quick").with_structured_output(AnalystReport, method=STRUCT_METHOD)
    messages = [
        SystemMessage(content=_SYSTEM),
        HumanMessage(content=f"Ticker: {ticker}\nSignals: {data}"),
    ]
    try:
        report: AnalystReport = await llm.ainvoke(messages, config={"callbacks": [tracker]})
    except Exception as exc:  # LLM failure degrades gracefully
        return {
            "analyst_reports": {"technicals": _degraded(f"LLM error: {exc}").model_dump()},
            "run_metrics": _zero_metrics(),
        }

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
        "analyst_reports": {"technicals": report.model_dump()},
        "run_metrics": per_node,
    }

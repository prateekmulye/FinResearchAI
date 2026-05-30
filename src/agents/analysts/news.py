"""News analyst: Firecrawl search -> structured AnalystReport (quick tier).

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
from src.tools.firecrawl import search_news

_SYSTEM = """You are a financial news analyst. Given recent web headlines and
snippets about a stock, produce a concise sentiment summary, 3-5 key points, a
confidence in [0,1], and the source URLs as citations. Be factual; do not invent
news that is not in the provided material."""

_NODE = "news_analyst"


def _degraded(reason: str) -> AnalystReport:
    return AnalystReport(summary=f"News unavailable: {reason}", confidence=0.0)


# Local alias kept for backward-compat; delegates to shared helper.
def _zero_metrics() -> list[dict]:
    return zero_metrics(_NODE)


async def news_analyst(state: dict) -> dict:
    tracker = CostTracker(_NODE)
    ticker = state.get("resolved_ticker") or state.get("ticker") or ""

    try:
        hits = await asyncio.to_thread(search_news, f"{ticker} stock news latest", 5)
    except ToolError as exc:
        # Degraded path: no LLM call was made, return zero metrics silently.
        return {
            "analyst_reports": {"news": _degraded(str(exc)).model_dump()},
            "run_metrics": _zero_metrics(),
        }

    if not hits:
        # Degraded path: no LLM call was made, return zero metrics silently.
        return {
            "analyst_reports": {"news": _degraded("no results").model_dump()},
            "run_metrics": _zero_metrics(),
        }

    material = "\n".join(f"- {h.title} ({h.url}): {h.snippet}" for h in hits)
    llm = get_llm("quick").with_structured_output(AnalystReport, method=STRUCT_METHOD)
    messages = [
        SystemMessage(content=_SYSTEM),
        HumanMessage(content=f"Ticker: {ticker}\nHeadlines:\n{material}"),
    ]
    try:
        report: AnalystReport = await llm.ainvoke(messages, config={"callbacks": [tracker]})
    except Exception as exc:  # LLM failure degrades gracefully
        return {
            "analyst_reports": {"news": _degraded(f"LLM error: {exc}").model_dump()},
            "run_metrics": _zero_metrics(),
        }

    # Happy path: an LLM call was made; warn if no cost was recorded.
    per_node = tracker.totals()["per_node"]
    if not per_node:
        warnings.warn(
            f"{_NODE}: no LLM cost recorded; on_llm_end may not have fired",
            stacklevel=2,
        )
        per_node = _zero_metrics()
    return {
        "analyst_reports": {"news": report.model_dump()},
        "run_metrics": per_node,
    }

# src/agents/research/bull.py
"""Bull researcher node: produces a single standalone bullish thesis from the
analyst reports. Writes only research_debate.bull_thesis; the merge_named_reports
reducer combines it with the bear's parallel write safely."""
from __future__ import annotations

import json
import logging

from langchain_core.messages import HumanMessage, SystemMessage

from src.agents._metrics import zero_metrics
from src.llm.cost import CostTracker
from src.llm.factory import STRUCT_METHOD, get_llm
from src.llm.schemas import DebateTurn
from src.state import AgentState

_LOG = logging.getLogger(__name__)

BULL_SYSTEM = (
    "You are the BULL researcher on an equity research desk. Build the strongest "
    "evidence-based case to BUY the stock, citing the analyst reports. Be specific "
    "and concise. Acknowledge the single biggest risk only to rebut it."
)


def _context(state: AgentState) -> str:
    reports = state.get("analyst_reports", {})
    return json.dumps(reports, default=str)


async def bull(state: AgentState) -> dict:
    tracker = CostTracker("bull")
    llm = get_llm("deep").with_structured_output(DebateTurn, method=STRUCT_METHOD)
    ticker = state.get("resolved_ticker") or state.get("ticker", "")
    human = (
        f"Ticker: {ticker}\n\nAnalyst reports (JSON):\n{_context(state)}\n\n"
        "State your bullish thesis. Set role='bull' and round=1."
    )
    messages = [SystemMessage(content=BULL_SYSTEM), HumanMessage(content=human)]
    try:
        turn: DebateTurn = await llm.ainvoke(messages, config={"callbacks": [tracker]})
        thesis = turn.argument
    except Exception as exc:
        _LOG.warning("bull: LLM call failed (%s); degrading to empty thesis", exc)
        thesis = ""
    return {
        "research_debate": {"bull_thesis": thesis},
        "run_metrics": tracker.totals()["per_node"] or zero_metrics("bull"),
    }

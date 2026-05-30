# src/agents/research/bear.py
"""Bear researcher node: produces a single standalone bearish thesis from the
analyst reports. Writes only research_debate.bear_thesis; merged with the bull's
parallel write by merge_named_reports."""
from __future__ import annotations

import json

from langchain_core.messages import HumanMessage, SystemMessage

from src.llm.cost import CostTracker
from src.llm.factory import STRUCT_METHOD, get_llm
from src.llm.schemas import DebateTurn
from src.state import AgentState

BEAR_SYSTEM = (
    "You are the BEAR researcher on an equity research desk. Build the strongest "
    "evidence-based case to SELL or AVOID the stock, citing the analyst reports. "
    "Be specific and concise. Acknowledge the single biggest bullish point only to rebut it."
)


def _context(state: AgentState) -> str:
    return json.dumps(state.get("analyst_reports", {}), default=str)


async def bear(state: AgentState) -> dict:
    tracker = CostTracker("bear")
    llm = get_llm("deep").with_structured_output(DebateTurn, method=STRUCT_METHOD)
    ticker = state.get("resolved_ticker") or state.get("ticker", "")
    human = (
        f"Ticker: {ticker}\n\nAnalyst reports (JSON):\n{_context(state)}\n\n"
        "State your bearish thesis. Set role='bear' and round=1."
    )
    messages = [SystemMessage(content=BEAR_SYSTEM), HumanMessage(content=human)]
    turn: DebateTurn = await llm.ainvoke(messages, config={"callbacks": [tracker]})
    return {
        "research_debate": {"bear_thesis": turn.argument},
        "run_metrics": tracker.totals()["per_node"],
    }

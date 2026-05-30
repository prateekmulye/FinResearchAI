# src/agents/research/synthesis.py
"""Single-pass research baseline for debate_mode="off". Does ONE deep LLM pass over
the analyst reports and writes research_debate.facilitator_verdict directly,
bypassing bull/bear/facilitator. This is the A/B baseline WP-H compares against the
full debate path. Intentionally leaves bull_thesis/bear_thesis/rounds empty so the
A/B harness can detect 'no debate happened'."""
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

SYNTHESIS_SYSTEM = (
    "You are a senior equity analyst. In a SINGLE pass over the analyst reports, "
    "weigh the bullish and bearish evidence yourself and deliver one decisive verdict "
    "the trader can act on. Be concise and honest about uncertainty. Put the verdict "
    "in 'argument'; set role='bull' if net-bullish else role='bear', round=1."
)


async def research_synthesis(state: AgentState) -> dict:
    tracker = CostTracker("research_synthesis")
    llm = get_llm("deep").with_structured_output(DebateTurn, method=STRUCT_METHOD)
    ticker = state.get("resolved_ticker") or state.get("ticker", "")
    human = (
        f"Ticker: {ticker}\n\nAnalyst reports (JSON):\n"
        f"{json.dumps(state.get('analyst_reports', {}), default=str)}\n\n"
        "Deliver the single-pass verdict."
    )
    messages = [SystemMessage(content=SYNTHESIS_SYSTEM), HumanMessage(content=human)]
    try:
        verdict: DebateTurn = await llm.ainvoke(messages, config={"callbacks": [tracker]})
        verdict_text = verdict.argument
    except Exception as exc:
        _LOG.warning("research_synthesis: LLM call failed (%s); degrading to HOLD verdict", exc)
        verdict_text = "Single-pass synthesis unavailable; treat as HOLD."
    return {
        "research_debate": {
            "rounds": [],
            "bull_thesis": "",
            "bear_thesis": "",
            "facilitator_verdict": verdict_text,
        },
        "run_metrics": tracker.totals()["per_node"] or zero_metrics("research_synthesis"),
    }

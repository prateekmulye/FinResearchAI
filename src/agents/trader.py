# src/agents/trader.py
"""Trader node: reads the facilitator verdict + analyst reports, then produces a
TradeProposal (action/conviction/score/rationale) that the risk personas debate.

F4: Uses safe .get() access on research_debate and analyst_reports to avoid
KeyError on missing keys.
"""
from __future__ import annotations

import json
import logging

from langchain_core.messages import HumanMessage, SystemMessage

from src.agents._metrics import zero_metrics
from src.llm.cost import CostTracker
from src.llm.factory import STRUCT_METHOD, get_llm
from src.llm.schemas import TradeProposal
from src.state import AgentState

_LOG = logging.getLogger(__name__)

_SYSTEM = """You are a disciplined equity trader. Given the research team's verdict and
analyst reports, produce a concrete trade proposal: action (BUY/SELL/HOLD), a conviction
score 0-100, a conviction float 0.0-1.0, and a concise rationale (≤3 sentences).
Be actionable and decisive. Acknowledge your biggest risk in one sentence."""


def _build_context(state: AgentState) -> str:
    # F4: use .get() to avoid KeyError on missing keys
    rd = state.get("research_debate", {})
    facilitator_verdict = rd.get("facilitator_verdict", "")
    bull_thesis = rd.get("bull_thesis", "")
    bear_thesis = rd.get("bear_thesis", "")

    # F4: analyst_reports may be an empty dict; iteration over it is safe
    reports = state.get("analyst_reports") or {}
    reports_json = json.dumps(reports, default=str)

    return (
        f"Facilitator verdict: {facilitator_verdict}\n\n"
        f"Bull thesis: {bull_thesis}\n"
        f"Bear thesis: {bear_thesis}\n\n"
        f"Analyst reports (JSON):\n{reports_json}"
    )


async def trader(state: AgentState) -> dict:
    tracker = CostTracker("trader")
    ticker = state.get("resolved_ticker") or state.get("ticker", "")
    investor_mode = state.get("investor_mode", "Neutral")

    llm = get_llm("deep").with_structured_output(TradeProposal, method=STRUCT_METHOD)
    context = _build_context(state)
    human = (
        f"Ticker: {ticker}\n"
        f"Investor mode: {investor_mode}\n\n"
        f"{context}\n\n"
        "Produce your trade proposal."
    )
    messages = [SystemMessage(content=_SYSTEM), HumanMessage(content=human)]

    try:
        proposal: TradeProposal = await llm.ainvoke(messages, config={"callbacks": [tracker]})
    except Exception as exc:
        _LOG.warning("trader: LLM call failed (%s); degrading to HOLD", exc)
        per_node = tracker.totals()["per_node"] or zero_metrics("trader")
        return {
            "trade_proposal": {
                "action": "HOLD",
                "conviction": 0.0,
                "score": 50,
                "rationale": "Trader degraded; defaulting to HOLD.",
            },
            "run_metrics": per_node,
        }

    per_node = tracker.totals()["per_node"] or zero_metrics("trader")
    return {
        "trade_proposal": proposal.model_dump(),
        "run_metrics": per_node,
    }

# src/agents/risk/aggressive.py
"""Aggressive risk persona: upside-maximizing case for the trade proposal.
Writes its stance string into risk_debate['aggressive'] (merge-reduced key)."""
from __future__ import annotations

import json
import logging

from langchain_core.messages import HumanMessage, SystemMessage

from pydantic import BaseModel, Field

from src.agents._metrics import zero_metrics
from src.llm.cost import CostTracker
from src.llm.factory import STRUCT_METHOD, get_llm
from src.state import AgentState

_LOG = logging.getLogger(__name__)


class RiskStance(BaseModel):
    """Local structured-output target for a risk persona. Not part of the frozen
    contract; the node unwraps `.stance` into the RiskDebate string field."""

    stance: str = Field(description="The persona's concise risk stance on the trade proposal.")


AGGRESSIVE_SYSTEM = (
    "You are the AGGRESSIVE risk officer. Your mandate is return maximization within "
    "mandate. Make the case for taking (or increasing) the position: highlight asymmetric "
    "upside, momentum, catalysts, and the opportunity cost of inaction. Push back on "
    "over-caution where the reward justifies the risk. One or two tight paragraphs, grounded "
    "in the proposal."
)

_DEGRADE_STANCE = "Risk stance unavailable; defaulting to measured optimism."


def _human(state: AgentState) -> HumanMessage:
    proposal = state.get("trade_proposal", {}) or {}
    ticker = state.get("resolved_ticker") or state.get("ticker", "UNKNOWN")
    return HumanMessage(
        content=(
            f"Ticker: {ticker}\n"
            f"Proposed trade:\n{json.dumps(proposal, indent=2, default=str)}\n\n"
            "Give your aggressive risk stance."
        )
    )


async def risk_aggressive(state: AgentState) -> dict:
    tracker = CostTracker("risk_aggressive")
    llm = get_llm("deep").with_structured_output(RiskStance, method=STRUCT_METHOD)
    messages = [SystemMessage(content=AGGRESSIVE_SYSTEM), _human(state)]

    try:
        result: RiskStance = await llm.ainvoke(messages, config={"callbacks": [tracker]})
        stance = result.stance
    except Exception as exc:
        _LOG.warning("risk_aggressive: LLM call failed (%s); degrading to measured optimism", exc)
        stance = _DEGRADE_STANCE

    per_node = tracker.totals()["per_node"] or zero_metrics("risk_aggressive")
    return {
        "risk_debate": {"aggressive": stance},
        "run_metrics": per_node,
    }

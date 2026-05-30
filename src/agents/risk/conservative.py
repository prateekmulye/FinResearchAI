# src/agents/risk/conservative.py
"""Conservative risk persona: capital-preservation critique of the trade proposal.
Writes its stance string into risk_debate['conservative'] (merge-reduced key)."""
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


CONSERVATIVE_SYSTEM = (
    "You are the CONSERVATIVE risk officer. Your mandate is capital preservation. "
    "Critique the trade proposal: surface downside, drawdown, liquidity, concentration, and "
    "tail risks. Argue for smaller size, tighter stops, or HOLD when uncertainty is high. "
    "Be specific and grounded in the proposal; one or two tight paragraphs."
)

_DEGRADE_STANCE = "Risk stance unavailable; defaulting to caution."


def _human(state: AgentState) -> HumanMessage:
    proposal = state.get("trade_proposal", {}) or {}
    ticker = state.get("resolved_ticker") or state.get("ticker", "UNKNOWN")
    return HumanMessage(
        content=(
            f"Ticker: {ticker}\n"
            f"Proposed trade:\n{json.dumps(proposal, indent=2, default=str)}\n\n"
            "Give your conservative risk stance."
        )
    )


async def risk_conservative(state: AgentState) -> dict:
    tracker = CostTracker("risk_conservative")
    llm = get_llm("deep").with_structured_output(RiskStance, method=STRUCT_METHOD)
    messages = [SystemMessage(content=CONSERVATIVE_SYSTEM), _human(state)]

    try:
        result: RiskStance = await llm.ainvoke(messages, config={"callbacks": [tracker]})
        stance = result.stance
    except Exception as exc:
        _LOG.warning("risk_conservative: LLM call failed (%s); degrading to caution", exc)
        stance = _DEGRADE_STANCE

    per_node = tracker.totals()["per_node"] or zero_metrics("risk_conservative")
    return {
        "risk_debate": {"conservative": stance},
        "run_metrics": per_node,
    }

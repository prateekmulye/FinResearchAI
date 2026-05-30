# src/agents/research/facilitator.py
"""Research facilitator node: runs the bounded bull<->bear debate via run_debate,
then selects the prevailing view and writes the full ResearchDebate into state.

Reads bull_thesis/bear_thesis already merged into research_debate by the upstream
bull/bear nodes (merge_named_reports reducer). Writes rounds + facilitator_verdict
while preserving the theses. research_debate carries the merge reducer, so the
returned partial dict is merged into existing state."""
from __future__ import annotations

import json

from langchain_core.messages import HumanMessage, SystemMessage

from src.agents.debate import run_debate
from src.config.settings import get_settings
from src.llm.cost import CostTracker
from src.llm.factory import STRUCT_METHOD, get_llm
from src.llm.schemas import DebateTurn
from src.state import AgentState

FACILITATOR_SYSTEM = (
    "You are the research facilitator. You have moderated a bounded bull vs bear "
    "debate. Weigh both sides and the analyst evidence, then state the prevailing "
    "view as a concise verdict that the trader can act on. Be decisive but honest "
    "about residual uncertainty. Put your verdict in 'argument'; set role='bull' if "
    "the prevailing view is bullish else role='bear', and round=1."
)

BULL_DEBATE_SYSTEM = (
    "You are the BULL debater. Argue to BUY using the analyst reports and rebut the "
    "bear. Be specific and concise."
)
BEAR_DEBATE_SYSTEM = (
    "You are the BEAR debater. Argue to SELL/AVOID using the analyst reports and "
    "rebut the bull. Be specific and concise."
)


async def facilitator(state: AgentState) -> dict:
    settings = get_settings()
    rounds = settings.research_debate_rounds
    ticker = state.get("resolved_ticker") or state.get("ticker", "")
    rd = state.get("research_debate", {})
    bull_thesis = rd.get("bull_thesis", "")
    bear_thesis = rd.get("bear_thesis", "")

    context = (
        f"Analyst reports (JSON):\n{json.dumps(state.get('analyst_reports', {}), default=str)}\n\n"
        f"Bull opening thesis: {bull_thesis}\n"
        f"Bear opening thesis: {bear_thesis}"
    )
    personas = [("bull", BULL_DEBATE_SYSTEM), ("bear", BEAR_DEBATE_SYSTEM)]

    turns, debate_metrics = await run_debate(
        topic=ticker,
        context=context,
        personas=personas,
        rounds=rounds,
        tier="deep",
        node_label="research_debate",
    )

    transcript = "\n".join(f"[round {t.round}] {t.role}: {t.argument}" for t in turns)
    tracker = CostTracker("facilitator")
    verdict_llm = get_llm("deep").with_structured_output(DebateTurn, method=STRUCT_METHOD)
    human = (
        f"Ticker: {ticker}\n\n{context}\n\nFull debate transcript:\n{transcript}\n\n"
        "Now deliver the prevailing-view verdict."
    )
    messages = [SystemMessage(content=FACILITATOR_SYSTEM), HumanMessage(content=human)]
    verdict: DebateTurn = await verdict_llm.ainvoke(messages, config={"callbacks": [tracker]})

    # F4: write ONLY the keys facilitator owns; do NOT include bull_thesis/bear_thesis
    # so the merge reducer retains the real theses written by bull/bear nodes upstream.
    return {
        "research_debate": {
            "rounds": [t.model_dump() for t in turns],
            "facilitator_verdict": verdict.argument,
        },
        "run_metrics": debate_metrics + tracker.totals()["per_node"],
    }

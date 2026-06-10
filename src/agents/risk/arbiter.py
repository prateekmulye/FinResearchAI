# src/agents/risk/arbiter.py
"""Risk arbiter node: run a bounded conservative<->aggressive debate (reusing WP-D's
run_debate), then act as the fund manager — fold both stances into a FinalDecision that
adjusts the trader's proposal. Persists the verdict to the warehouse-backed cache (WP-2)."""
from __future__ import annotations

import json
import logging

from langchain_core.messages import HumanMessage, SystemMessage

from src.agents._metrics import zero_metrics
from src.agents.debate import run_debate
from src.config.settings import get_settings
from src.llm.cost import CostTracker
from src.llm.factory import STRUCT_METHOD, get_llm
from src.llm.schemas import FinalDecision
from src.state import AgentState

# --- store_verdict (WP-2: async, warehouse-backed); guard so the graph runs
# --- even if the memory module is absent. ---
try:
    from src.memory.cache import store_verdict
except ImportError:  # pragma: no cover - exercised only without the memory module
    store_verdict = None  # type: ignore[assignment]

_LOG = logging.getLogger(__name__)

CONSERVATIVE_PROMPT = (
    "You are the CONSERVATIVE risk officer in a risk committee debate. Defend capital "
    "preservation: downside, drawdown, sizing, and HOLD when uncertain. Rebut the aggressive "
    "officer directly and concisely."
)
AGGRESSIVE_PROMPT = (
    "You are the AGGRESSIVE risk officer in a risk committee debate. Defend taking the "
    "opportunity: asymmetric upside, momentum, catalysts, opportunity cost. Rebut the "
    "conservative officer directly and concisely."
)

ARBITER_SYSTEM = (
    "You are the FUND MANAGER chairing the risk committee. You have the trader's proposal, both "
    "risk officers' opening stances, and the full debate transcript. Render the FINAL decision: "
    "action (BUY/SELL/HOLD), conviction (0..1), score (0..100), and a rationale that explains how "
    "you weighed the conservative vs aggressive arguments and what you adjusted from the trader's "
    "proposal (e.g. downgraded BUY->HOLD, trimmed conviction). Ground every claim in the inputs."
)


def _transcript(turns) -> str:
    if not turns:
        return "(no debate turns)"
    return "\n".join(f"[r{t.round}] {t.role}: {t.argument}" for t in turns)


def _arbiter_human(state: AgentState, turns, conservative: str, aggressive: str) -> HumanMessage:
    ticker = state.get("resolved_ticker") or state.get("ticker", "UNKNOWN")
    proposal = state.get("trade_proposal", {}) or {}
    content = (
        f"Ticker: {ticker}\n"
        f"Trader proposal:\n{json.dumps(proposal, indent=2, default=str)}\n\n"
        f"Conservative opening stance: {conservative or '(none)'}\n"
        f"Aggressive opening stance: {aggressive or '(none)'}\n\n"
        f"Debate transcript:\n{_transcript(turns)}\n\n"
        "Render the FinalDecision now."
    )
    return HumanMessage(content=content)


def _derive_adjustments(proposal: dict, decision: FinalDecision) -> list[str]:
    """Human-readable diff of what the arbiter changed vs the trader's proposal."""
    adjustments: list[str] = []
    if proposal.get("action") and proposal["action"] != decision.action:
        adjustments.append(f"action {proposal['action']} -> {decision.action}")
    if "conviction" in proposal and proposal["conviction"] != decision.conviction:
        adjustments.append(f"conviction {proposal['conviction']} -> {decision.conviction}")
    if "score" in proposal and proposal["score"] != decision.score:
        adjustments.append(f"score {proposal['score']} -> {decision.score}")
    return adjustments


async def risk_arbiter(state: AgentState) -> dict:
    tracker = CostTracker("risk_arbiter")
    settings = get_settings()
    rounds = settings.risk_debate_rounds

    risk_debate = state.get("risk_debate", {}) or {}
    conservative = risk_debate.get("conservative", "")
    aggressive = risk_debate.get("aggressive", "")
    proposal = state.get("trade_proposal", {}) or {}
    ticker = state.get("resolved_ticker") or state.get("ticker", "UNKNOWN")

    # 1. Bounded conservative<->aggressive debate (reused from WP-D).
    context = (
        f"Trade proposal for {ticker}: {json.dumps(proposal, default=str)}\n"
        f"Conservative opening: {conservative}\nAggressive opening: {aggressive}"
    )
    turns, debate_metrics = await run_debate(
        topic=f"Risk of the proposed trade on {ticker}",
        context=context,
        personas=[("conservative", CONSERVATIVE_PROMPT), ("aggressive", AGGRESSIVE_PROMPT)],
        rounds=rounds,
        tier="deep",
        node_label="risk_debate",
    )

    # 2. Fund-manager FinalDecision.
    llm = get_llm("deep").with_structured_output(FinalDecision, method=STRUCT_METHOD)
    messages = [
        SystemMessage(content=ARBITER_SYSTEM),
        _arbiter_human(state, turns, conservative, aggressive),
    ]

    try:
        decision: FinalDecision = await llm.ainvoke(messages, config={"callbacks": [tracker]})
    except Exception as exc:
        _LOG.warning("risk_arbiter: LLM call failed (%s); degrading to trade_proposal", exc)
        per_node = tracker.totals()["per_node"] or zero_metrics("risk_arbiter")
        metrics = list(debate_metrics) + per_node
        # Degrade: copy trade_proposal values so downstream nodes have a valid FinalDecision.
        return {
            "final_decision": {
                "action": proposal.get("action", "HOLD"),
                "conviction": proposal.get("conviction", 0.0),
                "score": proposal.get("score", 50),
                "rationale": "Arbiter degraded; using trader proposal as final decision.",
            },
            "risk_debate": {
                "rounds": [t.model_dump() for t in turns],
                "arbiter_decision": "Arbiter degraded.",
                "adjustments": [],
            },
            "run_metrics": metrics,
        }

    # 3. Persist to the verdict cache if available (never break on failure).
    if store_verdict is not None:
        try:
            await store_verdict(ticker, decision)
        except Exception as exc:  # defensive; cache must never break the run
            _LOG.warning("risk_arbiter: store_verdict failed (%s); continuing", exc, exc_info=exc)

    adjustments = _derive_adjustments(proposal, decision)
    per_node = tracker.totals()["per_node"] or zero_metrics("risk_arbiter")
    metrics = list(debate_metrics) + per_node
    return {
        "final_decision": decision.model_dump(),
        "risk_debate": {
            "rounds": [t.model_dump() for t in turns],
            "arbiter_decision": decision.rationale,
            "adjustments": adjustments,
        },
        "run_metrics": metrics,
    }

# src/agents/debate.py
"""Shared bounded-debate runner. Owned by WP-D; reused by WP-E (risk debate).

A debate is `rounds` bounded turns over an ordered list of personas. Personas
alternate by turn index. Each turn produces exactly one DebateTurn via
get_llm(tier).with_structured_output(DebateTurn, method=STRUCT_METHOD).
Per-node metrics from every LLM call are aggregated under a single node_label
and returned for the caller to fold into AgentState["run_metrics"].
"""
from __future__ import annotations

import logging

from langchain_core.messages import HumanMessage, SystemMessage

from src.llm.cost import CostTracker
from src.llm.factory import STRUCT_METHOD, get_llm
from src.llm.schemas import DebateTurn

logger = logging.getLogger(__name__)


async def run_debate(
    topic: str,
    context: str,
    personas: list[tuple[str, str]],
    rounds: int,
    tier: str = "deep",
    node_label: str = "debate",
    *,
    max_rounds: int = 8,
) -> tuple[list[DebateTurn], dict]:
    """Run a bounded alternating debate.

    Args:
        topic: short subject line (e.g. the ticker or the trade proposal).
        context: shared context all personas see (analyst reports, prior turns).
        personas: ordered [(role, system_prompt), ...]; turns alternate through them.
        rounds: number of full cycles through every persona.
                Values < 1 are clamped to 1 (never an empty debate).
                Values > max_rounds are capped with a warning logged.
        tier: LLM tier ("deep" by default).
        node_label: metrics node name for all calls in this debate.
        max_rounds: keyword-only hard cap on rounds (default 8).

    Returns:
        (turns, metrics_per_node) where turns is a flat list of DebateTurn in
        speaking order and metrics_per_node is CostTracker.totals()["per_node"].
    """
    # F3: clamp rounds into [1, max_rounds] and warn if capped
    effective_rounds = max(1, min(rounds, max_rounds))
    if rounds > max_rounds:
        logger.warning("run_debate: rounds=%d capped to max_rounds=%d", rounds, max_rounds)

    # F5: node_label is correctly threaded into CostTracker
    tracker = CostTracker(node_label)
    llm = get_llm(tier).with_structured_output(DebateTurn, method=STRUCT_METHOD)

    turns: list[DebateTurn] = []
    transcript: list[str] = []

    for rnd in range(1, effective_rounds + 1):
        for role, system_prompt in personas:
            prior = "\n".join(transcript) if transcript else "(no prior arguments yet)"
            human = (
                f"Topic: {topic}\n\n"
                f"Shared context:\n{context}\n\n"
                f"Debate so far:\n{prior}\n\n"
                f"You are the '{role}' debater. This is round {rnd}. "
                f"Make your strongest argument for your stance. "
                f"Set role='{role}' and round={rnd} in your response."
            )
            messages = [SystemMessage(content=system_prompt), HumanMessage(content=human)]
            turn: DebateTurn | None = await llm.ainvoke(messages, config={"callbacks": [tracker]})
            # F1: guard against None returned by weak models that emit no parseable output
            if turn is None:
                continue
            # Enforce the persona's role/round assignment from the loop, not the model.
            turn.role = role  # type: ignore[assignment]
            turn.round = rnd
            turns.append(turn)
            transcript.append(f"[round {rnd}] {role}: {turn.argument}")

    return turns, tracker.totals()["per_node"]

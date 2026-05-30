"""Deep-model referee for the debate A/B. Given a ticker, shared research context,
and the two verdicts (debate-on vs debate-off), the judge scores which is the
better-reasoned decision and whether the two agree on direction.

Blind-ish: the judge is shown two verdicts labeled neutrally ("Verdict A" /
"Verdict B") and is NOT told which used the debate. We map A->on, B->off after
the call. This is a reasoning-quality PROXY, not realized P&L."""
from __future__ import annotations

import json
from typing import Literal

from pydantic import BaseModel, Field

from src.llm.cost import CostTracker
from src.llm.factory import STRUCT_METHOD, get_llm

_SYSTEM = (
    "You are an impartial referee evaluating two independent investment verdicts "
    "for the same stock, produced by two different analysis pipelines. You do NOT "
    "know which pipeline produced which verdict. Judge ONLY on reasoning quality: "
    "evidence use, internal consistency, acknowledgment of risk, and calibration "
    "of conviction to the rationale. Do not reward a verdict merely for being more "
    "bullish or more cautious. State which verdict is better-reasoned and whether "
    "the two verdicts agree on direction (same BUY/SELL/HOLD action)."
)

# Maps the neutral A/B labels the judge sees back to the on/off pipelines.
_LABEL_TO_PIPELINE = {"A": "on", "B": "off"}


class JudgeVerdict(BaseModel):
    """Referee output. `preferred` is normalized to the pipeline name (on/off)."""

    preferred: Literal["on", "off", "tie"] = Field(
        description="Which pipeline was better-reasoned: 'on' (debate) or 'off' (single-pass), or 'tie'."
    )
    agreement: bool = Field(
        description="True if both verdicts chose the same BUY/SELL/HOLD action."
    )
    reasoning: str = Field(description="One paragraph justifying the preference.")
    confidence: float = Field(ge=0.0, le=1.0, description="Referee confidence in the preference.")


class _RawJudgeVerdict(BaseModel):
    """What the LLM returns: it only knows neutral labels A/B."""

    preferred_label: Literal["A", "B", "tie"]
    agreement: bool
    reasoning: str
    confidence: float = Field(ge=0.0, le=1.0)


async def judge_decision(
    ticker: str,
    context: str,
    decision_on: dict,
    decision_off: dict,
) -> JudgeVerdict:
    """Score on-vs-off reasoning quality with the deep model. Returns a JudgeVerdict
    whose `preferred` is normalized to 'on'/'off'/'tie'."""
    # Present neutrally: A == debate-on, B == debate-off (judge is not told this).
    user = (
        f"Ticker: {ticker}\n\n"
        f"Shared research context:\n{context}\n\n"
        f"Verdict A:\n{json.dumps(decision_on, indent=2)}\n\n"
        f"Verdict B:\n{json.dumps(decision_off, indent=2)}\n\n"
        "Return the better-reasoned verdict label (A, B, or tie), whether they "
        "agree on action, your reasoning, and your confidence."
    )
    tracker = CostTracker("eval_judge")
    llm = get_llm("deep").with_structured_output(_RawJudgeVerdict, method=STRUCT_METHOD)
    raw: _RawJudgeVerdict = await llm.ainvoke(
        [{"role": "system", "content": _SYSTEM}, {"role": "user", "content": user}],
        config={"callbacks": [tracker]},
    )
    preferred = _LABEL_TO_PIPELINE.get(raw.preferred_label, "tie")
    return JudgeVerdict(
        preferred=preferred,
        agreement=raw.agreement,
        reasoning=raw.reasoning,
        confidence=raw.confidence,
    )

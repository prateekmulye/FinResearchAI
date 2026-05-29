# src/llm/schemas.py
from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

Action = Literal["BUY", "SELL", "HOLD"]


class AnalystReport(BaseModel):
    summary: str
    key_points: list[str] = Field(default_factory=list)
    data: dict = Field(default_factory=dict)
    confidence: float = Field(default=0.5, ge=0.0, le=1.0)
    citations: list[str] = Field(default_factory=list)


class DebateTurn(BaseModel):
    role: Literal["bull", "bear", "conservative", "aggressive"]
    round: int = Field(ge=1)
    argument: str


class ResearchDebate(BaseModel):
    rounds: list[DebateTurn] = Field(default_factory=list)
    bull_thesis: str = ""
    bear_thesis: str = ""
    facilitator_verdict: str = ""


class TradeProposal(BaseModel):
    action: Action
    conviction: float = Field(ge=0.0, le=1.0)
    score: int = Field(ge=0, le=100)
    rationale: str


class RiskDebate(BaseModel):
    rounds: list[DebateTurn] = Field(default_factory=list)
    conservative: str = ""
    aggressive: str = ""
    arbiter_decision: str = ""
    adjustments: list[str] = Field(default_factory=list)


class FinalDecision(BaseModel):
    action: Action
    conviction: float = Field(ge=0.0, le=1.0)
    score: int = Field(ge=0, le=100)
    rationale: str

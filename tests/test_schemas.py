# tests/test_schemas.py
import pytest
from pydantic import ValidationError
from src.llm.schemas import (
    AnalystReport,
    DebateTurn,
    ResearchDebate,
    TradeProposal,
    RiskDebate,
    FinalDecision,
)


def test_analyst_report_defaults():
    r = AnalystReport(summary="s")
    assert r.key_points == []
    assert r.confidence == 0.5


def test_trade_proposal_valid():
    p = TradeProposal(action="BUY", conviction=0.8, score=72, rationale="strong fundamentals")
    assert p.action == "BUY"
    assert p.model_dump()["score"] == 72


def test_trade_proposal_rejects_bad_score():
    with pytest.raises(ValidationError):
        TradeProposal(action="BUY", conviction=0.8, score=150, rationale="x")


def test_trade_proposal_rejects_bad_action():
    with pytest.raises(ValidationError):
        TradeProposal(action="MAYBE", conviction=0.5, score=50, rationale="x")


def test_research_debate_round_trip():
    d = ResearchDebate(
        rounds=[DebateTurn(role="bull", round=1, argument="up")],
        bull_thesis="b", bear_thesis="r", facilitator_verdict="lean bull",
    )
    again = ResearchDebate(**d.model_dump())
    assert again.rounds[0].role == "bull"


def test_final_decision_and_risk_debate():
    fd = FinalDecision(action="HOLD", conviction=0.4, score=50, rationale="mixed")
    rd = RiskDebate(conservative="careful", aggressive="bold", arbiter_decision="hold")
    assert fd.action == "HOLD"
    assert rd.adjustments == []

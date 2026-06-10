# tests/test_llm_fake.py
"""WP-5 APP_FAKE_LLM mode: the deterministic production fake (src/llm/fake.py —
NO imports from tests/) and its factory/tool/ingest seams.

The fake implements exactly the node-LLM surface:
``get_llm(tier).with_structured_output(Schema, method=...).ainvoke(messages,
config={"callbacks": [tracker]})`` and returns plausible, deterministic
instances of THAT schema, with content keyed by the ticker in the prompt.
"""
from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest
from langchain_core.messages import HumanMessage, SystemMessage
from pydantic import BaseModel

from src.agents.reporter import ReportPayload
from src.agents.router import TickerResolution
from src.config import settings as settings_mod
from src.llm.cost import CostTracker
from src.llm.fake import FakeChatModel
from src.llm.schemas import (
    AnalystReport,
    DebateTurn,
    FinalDecision,
    RiskStance,
    TradeProposal,
)

pytestmark = []


def _msgs(system: str, human: str):
    return [SystemMessage(content=system), HumanMessage(content=human)]


async def _ask(schema, system: str, human: str, tracker=None):
    llm = FakeChatModel("deep").with_structured_output(schema, method="function_calling")
    config = {"callbacks": [tracker]} if tracker else None
    return await llm.ainvoke(_msgs(system, human), config=config)


# ------------------------------------------------------------- schema dispatch


async def test_returns_instance_of_each_node_schema():
    cases = [
        (TickerResolution, "You resolve a user-provided stock symbol.",
         "Resolve this symbol or company: 'AAPL'"),
        (AnalystReport, "You are a financial news analyst.", "Ticker: AAPL\nHeadlines:..."),
        (DebateTurn, "You are the BULL debater.", "Ticker: AAPL\nSet role='bull' and round=1."),
        (TradeProposal, "You are the trader.", "Ticker: AAPL\nProduce your trade proposal."),
        (RiskStance, "You are the CONSERVATIVE risk officer.", "Ticker: AAPL"),
        (FinalDecision, "You are the risk arbiter.", "Ticker: AAPL"),
        (ReportPayload, "You are the Reporter agent.", "Ticker: AAPL\nWrite the report."),
    ]
    for schema, system, human in cases:
        result = await _ask(schema, system, human)
        assert isinstance(result, schema), schema.__name__


async def test_ticker_resolution_handles_international_suffixes():
    res = await _ask(
        TickerResolution, "You resolve symbols.",
        "Resolve this symbol or company: 'reliance.ns'",
    )
    assert res.resolved_ticker == "RELIANCE.NS"
    assert res.screener == "india"
    assert res.exchange == "NSE"
    us = await _ask(
        TickerResolution, "You resolve symbols.", "Resolve this symbol or company: 'aapl'"
    )
    assert us.resolved_ticker == "AAPL"
    assert (us.screener, us.exchange) == ("america", "NASDAQ")


async def test_debate_turn_respects_requested_role_and_round():
    turn = await _ask(
        DebateTurn, "You are the BEAR debater.",
        "Ticker: AAPL\nThis is round 2. Set role='bear' and round=2 in your response.",
    )
    assert turn.role == "bear"
    assert turn.round == 2
    assert turn.argument


async def test_final_decision_is_valid_and_plausible():
    fd = await _ask(FinalDecision, "You are the risk arbiter.", "Ticker: AAPL")
    assert fd.action in {"BUY", "SELL", "HOLD"}
    assert 0.0 <= fd.conviction <= 1.0
    assert 0 <= fd.score <= 100
    assert "AAPL" in fd.rationale


async def test_report_payload_has_sections_and_radar():
    payload = await _ask(ReportPayload, "You are the Reporter agent.", "Ticker: AAPL")
    assert payload.sections and all(s.heading and s.body for s in payload.sections)
    fd = payload.financial_data
    for axis in (fd.valuation, fd.growth, fd.profitability, fd.momentum, fd.sentiment, fd.risk):
        assert 0.0 <= axis <= 100.0
    assert payload.financial_data.metric_cards


# ----------------------------------------------------------------- determinism


async def test_same_inputs_same_outputs():
    a = await _ask(TradeProposal, "You are the trader.", "Ticker: AAPL\nPropose.")
    b = await _ask(TradeProposal, "You are the trader.", "Ticker: AAPL\nPropose.")
    assert a.model_dump() == b.model_dump()


async def test_different_tickers_look_different():
    a = await _ask(AnalystReport, "You are a fundamentals analyst.", "Ticker: AAPL")
    t = await _ask(AnalystReport, "You are a fundamentals analyst.", "Ticker: TSLA")
    assert a.model_dump() != t.model_dump()
    assert "AAPL" in a.summary and "TSLA" in t.summary


# ------------------------------------------------------------------- callbacks


async def test_fires_cost_tracker_callbacks():
    tracker = CostTracker("trader")
    await _ask(TradeProposal, "You are the trader.", "Ticker: AAPL", tracker=tracker)
    per_node = tracker.totals()["per_node"]
    assert len(per_node) == 1
    assert per_node[0]["node"] == "trader"
    assert per_node[0]["prompt_tokens"] > 0
    assert per_node[0]["completion_tokens"] > 0
    assert per_node[0]["model"].startswith("fake-")


# ------------------------------------------------------------ generic fallback


async def test_unknown_schema_falls_back_to_defaults():
    class Oddball(BaseModel):
        note: str = "default"
        n: int = 7

    result = await _ask(Oddball, "Anything.", "Ticker: AAPL")
    assert isinstance(result, Oddball)


async def test_bare_ainvoke_returns_message_with_content():
    msg = await FakeChatModel("quick").ainvoke(_msgs("sys", "Ticker: AAPL"))
    assert isinstance(msg.content, str) and msg.content


# -------------------------------------------------------------- factory seam


def test_get_llm_returns_fake_when_flag_set(monkeypatch):
    from src.llm import factory

    monkeypatch.setenv("APP_FAKE_LLM", "1")
    settings_mod.get_settings.cache_clear()
    factory.get_llm.cache_clear()
    assert isinstance(factory.get_llm("quick"), FakeChatModel)
    assert isinstance(factory.get_llm("deep"), FakeChatModel)


def test_get_llm_returns_real_chatopenai_without_flag():
    from langchain_openai import ChatOpenAI

    from src.llm import factory

    factory.get_llm.cache_clear()
    assert isinstance(factory.get_llm("quick"), ChatOpenAI)


# ----------------------------------------------------------------- tool seams


@pytest.fixture
def fake_mode(monkeypatch):
    monkeypatch.setenv("APP_FAKE_LLM", "1")
    settings_mod.get_settings.cache_clear()
    yield
    settings_mod.get_settings.cache_clear()


def test_fetch_fundamentals_returns_canned_data_offline(fake_mode, monkeypatch):
    import src.tools.yfinance as yf_mod

    def _boom(ticker):
        raise AssertionError("network path must not run in fake mode")

    monkeypatch.setattr(yf_mod, "_ticker_info", _boom)
    f = yf_mod.fetch_fundamentals("AAPL")
    assert f.ticker == "AAPL"
    assert f.name and f.sector
    assert f.trailing_pe and f.market_cap
    assert yf_mod.fetch_fundamentals("AAPL").to_dict() == f.to_dict()  # deterministic


def test_search_news_returns_canned_hits_offline(fake_mode, monkeypatch):
    import src.tools.firecrawl as fc_mod

    monkeypatch.setattr(
        fc_mod, "_client",
        lambda: (_ for _ in ()).throw(AssertionError("no firecrawl in fake mode")),
    )
    hits = fc_mod.search_news("AAPL stock news latest", 5)
    assert len(hits) == 5
    assert all(h.title and h.url.startswith("https://") and h.snippet for h in hits)
    assert "AAPL" in hits[0].title


def test_fetch_technicals_returns_canned_data_offline(fake_mode, monkeypatch):
    import src.tools.tradingview as tv_mod

    def _boom(**kwargs):
        raise AssertionError("no tradingview in fake mode")

    monkeypatch.setattr(tv_mod, "_analyze", _boom)
    t = tv_mod.fetch_technicals("AAPL", "america", "NASDAQ")
    assert t.ticker == "AAPL" and t.exchange == "NASDAQ"
    assert t.recommendation in {"STRONG_BUY", "BUY", "NEUTRAL", "SELL", "STRONG_SELL"}
    assert t.rsi is not None and 0 <= t.rsi <= 100


async def test_ingest_fetch_daily_bars_generates_deterministic_ohlcv(fake_mode):
    from src.warehouse.ingest import _fetch_daily_bars

    start = datetime.now(UTC) - timedelta(days=30)
    bars = await _fetch_daily_bars("AAPL", start)
    again = await _fetch_daily_bars("AAPL", start)
    other = await _fetch_daily_bars("TSLA", start)
    assert len(bars) >= 15  # ~22 business days in 30 calendar days
    for bar in bars:
        assert bar["low"] <= bar["open"] <= bar["high"]
        assert bar["low"] <= bar["close"] <= bar["high"]
        assert bar["volume"] > 0
    assert bars == again  # deterministic
    assert [b["close"] for b in bars] != [b["close"] for b in other]


def test_tools_read_flag_at_call_time_not_import_time(monkeypatch):
    # Flag off -> the real path runs (proven via a sentinel on the SDK seam).
    import src.tools.yfinance as yf_mod

    called = []
    monkeypatch.setattr(
        yf_mod, "_ticker_info",
        lambda t: called.append(t) or {"longName": "Apple", "marketCap": 1},
    )
    settings_mod.get_settings.cache_clear()
    yf_mod.fetch_fundamentals("AAPL")
    assert called == ["AAPL"]

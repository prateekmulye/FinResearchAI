# tests/test_llm_fake.py
"""WP-5 APP_FAKE_LLM mode: the deterministic production fake (src/llm/fake.py —
NO imports from tests/) and its factory/tool/ingest seams.

The fake implements exactly the node-LLM surface:
``get_llm(tier).with_structured_output(Schema, method=...).ainvoke(messages,
config={"callbacks": [tracker]})`` and returns plausible, deterministic
instances of THAT schema, with content keyed by the ticker in the prompt.

Dispatch tests use the REAL ``_SYSTEM`` prompt constants imported from the
agent modules (not paraphrases), so rewording a production prompt breaks these
tests instead of silently degrading demo output to the generic fallback.
"""
from __future__ import annotations

import time
from datetime import UTC, datetime, timedelta

import pytest
from langchain_core.messages import HumanMessage, SystemMessage
from pydantic import BaseModel

from src.agents.analysts.fundamentals import _SYSTEM as FUNDAMENTALS_SYSTEM
from src.agents.analysts.news import _SYSTEM as NEWS_SYSTEM
from src.agents.analysts.technicals import _SYSTEM as TECHNICALS_SYSTEM
from src.agents.reporter import REPORTER_SYSTEM_PROMPT, ReportPayload
from src.agents.research.bear import BEAR_SYSTEM
from src.agents.research.bull import BULL_SYSTEM
from src.agents.risk.aggressive import AGGRESSIVE_SYSTEM
from src.agents.risk.arbiter import ARBITER_SYSTEM
from src.agents.risk.conservative import CONSERVATIVE_SYSTEM
from src.agents.router import _SYSTEM as ROUTER_SYSTEM
from src.agents.router import TickerResolution
from src.agents.trader import _SYSTEM as TRADER_SYSTEM
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
        (TickerResolution, ROUTER_SYSTEM, f"Resolve this symbol or company: {'AAPL'!r}"),
        (AnalystReport, NEWS_SYSTEM, "Ticker: AAPL\nHeadlines:..."),
        (DebateTurn, BULL_SYSTEM,
         "Ticker: AAPL\nState your bullish thesis. Set role='bull' and round=1."),
        (TradeProposal, TRADER_SYSTEM, "Ticker: AAPL\nProduce your trade proposal."),
        (RiskStance, CONSERVATIVE_SYSTEM, "Ticker: AAPL\nGive your conservative risk stance."),
        (FinalDecision, ARBITER_SYSTEM, "Ticker: AAPL"),
        (ReportPayload, REPORTER_SYSTEM_PROMPT, "Ticker: AAPL\nWrite the report."),
    ]
    for schema, system, human in cases:
        result = await _ask(schema, system, human)
        assert isinstance(result, schema), schema.__name__


async def test_analyst_dispatch_keys_match_real_system_prompts():
    # The fake dispatches analyst flavors on substrings of the production
    # prompts; each REAL prompt must keep producing its distinct variant.
    news = await _ask(AnalystReport, NEWS_SYSTEM, "Ticker: AAPL\nHeadlines:\n- ...")
    assert news.citations  # news flavor carries canned source URLs
    assert "headlines" in news.summary
    fund = await _ask(AnalystReport, FUNDAMENTALS_SYSTEM, "Ticker: AAPL")
    assert "P/E" in fund.summary
    tech = await _ask(AnalystReport, TECHNICALS_SYSTEM, "Ticker: AAPL")
    assert "RSI" in tech.summary
    # the three flavors are actually distinct (no silent generic fallback)
    assert len({news.summary, fund.summary, tech.summary}) == 3


async def test_risk_stance_dispatch_keys_match_real_system_prompts():
    cons = await _ask(
        RiskStance, CONSERVATIVE_SYSTEM, "Ticker: AAPL\nGive your conservative risk stance."
    )
    agg = await _ask(
        RiskStance, AGGRESSIVE_SYSTEM, "Ticker: AAPL\nGive your aggressive risk stance."
    )
    assert "Capital preservation" in cons.stance
    assert cons.stance != agg.stance


async def test_ticker_resolution_handles_international_suffixes():
    res = await _ask(
        TickerResolution, ROUTER_SYSTEM,
        f"Resolve this symbol or company: {'reliance.ns'!r}",
    )
    assert res.resolved_ticker == "RELIANCE.NS"
    assert res.screener == "india"
    assert res.exchange == "NSE"
    us = await _ask(
        TickerResolution, ROUTER_SYSTEM, f"Resolve this symbol or company: {'aapl'!r}"
    )
    assert us.resolved_ticker == "AAPL"
    assert (us.screener, us.exchange) == ("america", "NASDAQ")


async def test_debate_turn_respects_requested_role_and_round():
    # human mirrors src/agents/debate.py's run_debate turn prompt
    turn = await _ask(
        DebateTurn, BEAR_SYSTEM,
        "Topic: AAPL\n\nYou are the 'bear' debater. This is round 2. "
        "Set role='bear' and round=2 in your response.",
    )
    assert turn.role == "bear"
    assert turn.round == 2
    assert turn.argument


async def test_final_decision_is_valid_and_plausible():
    fd = await _ask(FinalDecision, ARBITER_SYSTEM, "Ticker: AAPL")
    assert fd.action in {"BUY", "SELL", "HOLD"}
    assert 0.0 <= fd.conviction <= 1.0
    assert 0 <= fd.score <= 100
    assert "AAPL" in fd.rationale


async def test_demo_sell_ticker_maps_to_sell_and_aapl_stays_buy():
    """At least one well-known demo ticker deterministically shows the SELL path;
    the canonical demo ticker AAPL stays a confident BUY (86)."""
    sell = await _ask(FinalDecision, ARBITER_SYSTEM, "Ticker: GME")
    assert sell.action == "SELL"
    assert sell.score < 50          # outlook score reads bearish
    assert sell.conviction >= 0.5   # but the SELL call itself is confident

    buy = await _ask(FinalDecision, ARBITER_SYSTEM, "Ticker: AAPL")
    assert (buy.action, buy.score) == ("BUY", 86)


async def test_report_payload_has_sections_and_radar():
    payload = await _ask(ReportPayload, REPORTER_SYSTEM_PROMPT, "Ticker: AAPL")
    assert payload.sections and all(s.heading and s.body for s in payload.sections)
    fd = payload.financial_data
    for axis in (fd.valuation, fd.growth, fd.profitability, fd.momentum, fd.sentiment, fd.risk):
        assert 0.0 <= axis <= 100.0
    assert payload.financial_data.metric_cards


# ----------------------------------------------------------------- determinism


async def test_same_inputs_same_outputs():
    a = await _ask(TradeProposal, TRADER_SYSTEM, "Ticker: AAPL\nPropose.")
    b = await _ask(TradeProposal, TRADER_SYSTEM, "Ticker: AAPL\nPropose.")
    assert a.model_dump() == b.model_dump()


async def test_different_tickers_look_different():
    a = await _ask(AnalystReport, FUNDAMENTALS_SYSTEM, "Ticker: AAPL")
    t = await _ask(AnalystReport, FUNDAMENTALS_SYSTEM, "Ticker: TSLA")
    assert a.model_dump() != t.model_dump()
    assert "AAPL" in a.summary and "TSLA" in t.summary


# ------------------------------------------------------------------- callbacks


async def test_fires_cost_tracker_callbacks():
    tracker = CostTracker("trader")
    await _ask(TradeProposal, TRADER_SYSTEM, "Ticker: AAPL", tracker=tracker)
    per_node = tracker.totals()["per_node"]
    assert len(per_node) == 1
    assert per_node[0]["node"] == "trader"
    assert per_node[0]["prompt_tokens"] > 0
    assert per_node[0]["completion_tokens"] > 0
    assert per_node[0]["model"].startswith("fake-")


async def test_records_synthetic_latency_without_sleeping():
    # CostTracker latency is perf_counter() between on_llm_start/on_llm_end;
    # the fake backdates the start marker (hash-derived 80-400ms) instead of
    # sleeping, so recorded latency is plausible while wall time stays ~0.
    tracker = CostTracker("trader")
    t0 = time.perf_counter()
    await _ask(TradeProposal, TRADER_SYSTEM, "Ticker: AAPL", tracker=tracker)
    wall_s = time.perf_counter() - t0
    latency_s = tracker.totals()["per_node"][0]["latency_s"]
    assert 0.08 <= latency_s <= 0.45  # synthetic 80-400ms (+ tiny real epsilon)
    assert wall_s < latency_s  # injected, not slept

    again = CostTracker("trader")
    await _ask(TradeProposal, TRADER_SYSTEM, "Ticker: AAPL", tracker=again)
    repeat_s = again.totals()["per_node"][0]["latency_s"]
    assert abs(repeat_s - latency_s) < 0.02  # deterministic per prompt


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

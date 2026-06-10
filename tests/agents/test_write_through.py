# tests/agents/test_write_through.py
"""WP-3 node write-through hooks: with the warehouse enabled (sqlite fixture)
the router persists the Instrument, the fundamentals analyst persists a
FundamentalsSnapshot + backfills price bars, and the news analyst persists
NewsItems. With the warehouse disabled (the default everywhere else in the
suite) the hooks are byte-invisible — the existing node tests prove that.

State contract: the hooks add ZERO new state keys and change no report content;
each test asserts the node output shape is exactly the pre-WP-3 one.

Ordering contract (review fix): the write-through runs OFF the LLM critical
path — scheduled as a background task right after the tool fetch and awaited
only after the LLM call completes — but rows must still have landed by the
time the node returns (every persistence assertion below runs post-return).
"""
from __future__ import annotations

import asyncio
from datetime import UTC, datetime, timedelta

from sqlalchemy import func, select

from src.agents import router as router_mod
from src.agents.analysts import fundamentals as fund_mod
from src.agents.analysts import news as news_mod
from src.agents.router import TickerResolution, router
from src.llm.schemas import AnalystReport
from src.tools.firecrawl import NewsHit
from src.tools.yfinance import Fundamentals
from src.warehouse.db import session_scope
from src.warehouse.models import FundamentalsSnapshot, Instrument, NewsItem, PriceBar


class _FakeStructured:
    def __init__(self, result):
        self._result = result

    async def ainvoke(self, messages, config=None):
        return self._result


class _FakeLLM:
    def __init__(self, result):
        self._result = result

    def with_structured_output(self, schema, method=None):
        return _FakeStructured(self._result)


async def _no_cached_verdict(*a, **k):
    return None


async def _count(model) -> int:
    async with session_scope() as session:
        return (
            await session.execute(select(func.count()).select_from(model))
        ).scalar_one()


def _fund() -> Fundamentals:
    return Fundamentals(
        ticker="AAPL", name="Apple Inc.", sector="Technology", trailing_pe=28.0,
        forward_pe=25.0, earnings_growth=0.1, revenue_growth=0.05, dividend_yield=0.0056,
        payout_ratio=0.15, profit_margins=0.25, gross_margins=0.44,
        market_cap=2.7e12, beta=1.2,
    )


# ----------------------------------------------------------------------- router


async def test_router_persists_instrument(sqlite_warehouse, monkeypatch):
    monkeypatch.setattr(router_mod, "_get_cached_verdict", _no_cached_verdict)
    resolution = TickerResolution(resolved_ticker="RELIANCE.NS", screener="india", exchange="NSE")
    monkeypatch.setattr(router_mod, "get_llm", lambda tier: _FakeLLM(resolution))

    out = await router({"ticker": "RELIANCE", "investor_mode": "Neutral"})

    assert out["resolved_ticker"] == "RELIANCE.NS"  # state contract unchanged
    assert set(out) == {"resolved_ticker", "screener", "exchange", "model_plan", "run_metrics"}
    async with session_scope() as session:
        inst = (await session.execute(select(Instrument))).scalar_one()
    assert (inst.ticker, inst.exchange, inst.screener) == ("RELIANCE.NS", "NSE", "india")
    assert inst.watched is False  # routing must not mark instruments watched


async def test_router_degraded_resolution_persists_nothing(sqlite_warehouse, monkeypatch):
    monkeypatch.setattr(router_mod, "_get_cached_verdict", _no_cached_verdict)

    class _FailingStructured:
        async def ainvoke(self, messages, config=None):
            raise ConnectionError("LLM unreachable")

    class _FailingLLM:
        def with_structured_output(self, schema, method=None):
            return _FailingStructured()

    monkeypatch.setattr(router_mod, "get_llm", lambda tier: _FailingLLM())
    out = await router({"ticker": "ZZZGARBAGE", "investor_mode": "Neutral"})
    assert out["resolved_ticker"] == "ZZZGARBAGE"  # degrade path unchanged
    # An unverified default resolution must not pollute the instruments table.
    assert await _count(Instrument) == 0


# ----------------------------------------------------- fundamentals analyst


async def test_fundamentals_analyst_persists_snapshot_and_prices(sqlite_warehouse, monkeypatch):
    monkeypatch.setattr(fund_mod, "fetch_fundamentals", lambda t: _fund())
    report = AnalystReport(summary="Healthy margins", key_points=["P/E 28"], confidence=0.65)
    monkeypatch.setattr(fund_mod, "get_llm", lambda tier: _FakeLLM(report))

    bars = [
        {"ts": datetime.now(UTC) - timedelta(days=1), "open": 1.0, "high": 2.0,
         "low": 0.5, "close": 1.5, "volume": 100},
        {"ts": datetime.now(UTC), "open": 1.5, "high": 2.5, "low": 1.0,
         "close": 2.0, "volume": 200},
    ]

    async def _fake_fetch(ticker, start):
        return bars

    from src.warehouse import ingest as ingest_mod

    monkeypatch.setattr(ingest_mod, "_fetch_daily_bars", _fake_fetch)

    out = await fund_mod.fundamentals_analyst(
        {"resolved_ticker": "AAPL", "screener": "america", "exchange": "NASDAQ"}
    )

    # State contract unchanged: same keys, same report content as pre-WP-3.
    assert set(out) == {"analyst_reports", "run_metrics"}
    assert out["analyst_reports"]["fundamentals"]["summary"] == "Healthy margins"
    assert out["analyst_reports"]["fundamentals"]["data"]["trailing_pe"] == 28.0

    async with session_scope() as session:
        snap = (await session.execute(select(FundamentalsSnapshot))).scalar_one()
        assert snap.market_cap == 2.7e12
        assert snap.pe_ratio == 28.0
    assert await _count(PriceBar) == 2


async def test_fundamentals_analyst_skips_price_refresh_when_fresh(sqlite_warehouse, monkeypatch):
    monkeypatch.setattr(fund_mod, "fetch_fundamentals", lambda t: _fund())
    report = AnalystReport(summary="ok", confidence=0.5)
    monkeypatch.setattr(fund_mod, "get_llm", lambda tier: _FakeLLM(report))

    # Pre-seed a fresh bar so prices_stale() is False -> refresh must be skipped.
    from src.warehouse.ingest import refresh_prices

    async def _seed_fetch(ticker, start):
        return [{"ts": datetime.now(UTC), "open": 1.0, "high": 1.0, "low": 1.0, "close": 1.0}]

    await refresh_prices("AAPL", "NASDAQ", "america", fetch=_seed_fetch)

    async def _must_not_fetch(ticker, start):
        raise AssertionError("price fetch must be skipped when bars are fresh")

    from src.warehouse import ingest as ingest_mod

    monkeypatch.setattr(ingest_mod, "_fetch_daily_bars", _must_not_fetch)
    out = await fund_mod.fundamentals_analyst(
        {"resolved_ticker": "AAPL", "screener": "america", "exchange": "NASDAQ"}
    )
    assert out["analyst_reports"]["fundamentals"]["summary"] == "ok"
    assert await _count(PriceBar) == 1  # still just the seeded bar


async def test_fundamentals_write_through_off_llm_critical_path(sqlite_warehouse, monkeypatch):
    """The write-through must NOT be awaited before the LLM call. The ingest here
    blocks until the (fake) LLM has run: under the old pre-LLM-awaited ordering
    this deadlocks (caught by the timeout); off the critical path the LLM runs,
    unblocks the ingest, and the row still lands by node return."""
    monkeypatch.setattr(fund_mod, "fetch_fundamentals", lambda t: _fund())

    from src.warehouse import ingest as ingest_mod

    async def _no_bars(ticker, start):
        return []

    monkeypatch.setattr(ingest_mod, "_fetch_daily_bars", _no_bars)

    llm_ran = asyncio.Event()
    real_record = fund_mod.record_fundamentals

    async def _blocking_record(*args, **kwargs):
        await asyncio.wait_for(llm_ran.wait(), timeout=5)
        return await real_record(*args, **kwargs)

    monkeypatch.setattr(fund_mod, "record_fundamentals", _blocking_record)

    report = AnalystReport(summary="ordered", confidence=0.5)

    class _SignallingStructured:
        async def ainvoke(self, messages, config=None):
            llm_ran.set()
            return report

    class _SignallingLLM:
        def with_structured_output(self, schema, method=None):
            return _SignallingStructured()

    monkeypatch.setattr(fund_mod, "get_llm", lambda tier: _SignallingLLM())

    out = await asyncio.wait_for(
        fund_mod.fundamentals_analyst(
            {"resolved_ticker": "AAPL", "screener": "america", "exchange": "NASDAQ"}
        ),
        timeout=5,
    )
    assert set(out) == {"analyst_reports", "run_metrics"}
    assert out["analyst_reports"]["fundamentals"]["summary"] == "ordered"
    # Rows must still have landed by node return (task awaited before return).
    assert await _count(FundamentalsSnapshot) == 1


async def test_fundamentals_analyst_llm_error_still_persists_snapshot(
    sqlite_warehouse, monkeypatch
):
    """Degrade path: the LLM raising must not leak (or cancel) the write-through
    task — the snapshot still lands by node return."""
    monkeypatch.setattr(fund_mod, "fetch_fundamentals", lambda t: _fund())

    from src.warehouse import ingest as ingest_mod

    async def _no_bars(ticker, start):
        return []

    monkeypatch.setattr(ingest_mod, "_fetch_daily_bars", _no_bars)

    class _FailingStructured:
        async def ainvoke(self, messages, config=None):
            raise ConnectionError("LLM unreachable")

    class _FailingLLM:
        def with_structured_output(self, schema, method=None):
            return _FailingStructured()

    monkeypatch.setattr(fund_mod, "get_llm", lambda tier: _FailingLLM())

    out = await fund_mod.fundamentals_analyst(
        {"resolved_ticker": "AAPL", "screener": "america", "exchange": "NASDAQ"}
    )
    assert set(out) == {"analyst_reports", "run_metrics"}
    assert "LLM error" in out["analyst_reports"]["fundamentals"]["summary"]
    assert await _count(FundamentalsSnapshot) == 1


async def test_fundamentals_analyst_survives_raising_ingest(
    sqlite_warehouse, monkeypatch, caplog
):
    """Belt-and-braces: ingest never raises by contract, but even a broken
    invariant must not crash the node — the hardened await logs and degrades."""
    monkeypatch.setattr(fund_mod, "fetch_fundamentals", lambda t: _fund())

    async def _boom(*args, **kwargs):
        raise RuntimeError("ingest invariant broken")

    monkeypatch.setattr(fund_mod, "record_fundamentals", _boom)
    report = AnalystReport(summary="still fine", confidence=0.6)
    monkeypatch.setattr(fund_mod, "get_llm", lambda tier: _FakeLLM(report))

    with caplog.at_level("WARNING"):
        out = await fund_mod.fundamentals_analyst(
            {"resolved_ticker": "AAPL", "screener": "america", "exchange": "NASDAQ"}
        )
    assert set(out) == {"analyst_reports", "run_metrics"}
    assert out["analyst_reports"]["fundamentals"]["summary"] == "still fine"
    assert any("write-through" in r.message for r in caplog.records)


# ------------------------------------------------------------- news analyst


async def test_news_analyst_persists_news_items(sqlite_warehouse, monkeypatch):
    hits = [
        NewsHit(title="Apple beats earnings", url="https://x.com/a", snippet="strong q",
                markdown=None),
        NewsHit(title="Apple guidance", url="https://x.com/b", snippet="raised", markdown=None),
    ]
    monkeypatch.setattr(news_mod, "search_news", lambda q, limit=5: hits)
    report = AnalystReport(summary="Positive coverage", key_points=["beat"], confidence=0.7,
                           citations=["https://x.com/a"])
    monkeypatch.setattr(news_mod, "get_llm", lambda tier: _FakeLLM(report))

    out = await news_mod.news_analyst(
        {"resolved_ticker": "AAPL", "screener": "america", "exchange": "NASDAQ"}
    )

    assert set(out) == {"analyst_reports", "run_metrics"}
    assert out["analyst_reports"]["news"]["summary"] == "Positive coverage"

    async with session_scope() as session:
        rows = list((await session.execute(select(NewsItem))).scalars())
    assert {r.url for r in rows} == {"https://x.com/a", "https://x.com/b"}
    assert all(r.ts.tzinfo is not None for r in rows)
    assert await _count(Instrument) == 1


async def test_news_write_through_off_llm_critical_path(sqlite_warehouse, monkeypatch):
    """Same ordering contract as fundamentals: record_news blocks until the fake
    LLM has run — pre-LLM awaiting would deadlock; rows still land by return."""
    hits = [NewsHit(title="Apple beats", url="https://x.com/a", snippet="q", markdown=None)]
    monkeypatch.setattr(news_mod, "search_news", lambda q, limit=5: hits)

    llm_ran = asyncio.Event()
    real_record = news_mod.record_news

    async def _blocking_record(*args, **kwargs):
        await asyncio.wait_for(llm_ran.wait(), timeout=5)
        return await real_record(*args, **kwargs)

    monkeypatch.setattr(news_mod, "record_news", _blocking_record)

    report = AnalystReport(summary="ordered", confidence=0.5)

    class _SignallingStructured:
        async def ainvoke(self, messages, config=None):
            llm_ran.set()
            return report

    class _SignallingLLM:
        def with_structured_output(self, schema, method=None):
            return _SignallingStructured()

    monkeypatch.setattr(news_mod, "get_llm", lambda tier: _SignallingLLM())

    out = await asyncio.wait_for(
        news_mod.news_analyst(
            {"resolved_ticker": "AAPL", "screener": "america", "exchange": "NASDAQ"}
        ),
        timeout=5,
    )
    assert set(out) == {"analyst_reports", "run_metrics"}
    assert out["analyst_reports"]["news"]["summary"] == "ordered"
    assert await _count(NewsItem) == 1


async def test_news_analyst_survives_raising_ingest(sqlite_warehouse, monkeypatch, caplog):
    """Belt-and-braces for the news node: a raising record_news must not crash
    the node — the hardened await logs and the normal output is returned."""
    hits = [NewsHit(title="Apple beats", url="https://x.com/a", snippet="q", markdown=None)]
    monkeypatch.setattr(news_mod, "search_news", lambda q, limit=5: hits)

    async def _boom(*args, **kwargs):
        raise RuntimeError("ingest invariant broken")

    monkeypatch.setattr(news_mod, "record_news", _boom)
    report = AnalystReport(summary="still fine", confidence=0.6)
    monkeypatch.setattr(news_mod, "get_llm", lambda tier: _FakeLLM(report))

    with caplog.at_level("WARNING"):
        out = await news_mod.news_analyst(
            {"resolved_ticker": "AAPL", "screener": "america", "exchange": "NASDAQ"}
        )
    assert set(out) == {"analyst_reports", "run_metrics"}
    assert out["analyst_reports"]["news"]["summary"] == "still fine"
    assert any("write-through" in r.message for r in caplog.records)

# tests/warehouse/test_repos.py
"""Repository functions against in-memory SQLite: upsert semantics, idempotent
bulk inserts, run lifecycle, freshness window, and quota accounting."""
from __future__ import annotations

import hashlib
from datetime import UTC, date, datetime, timedelta

import pytest
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from src.warehouse.bootstrap import create_all
from src.warehouse.db import enable_sqlite_fks
from src.warehouse.models import Instrument, NewsItem, PriceBar
from src.warehouse.repos import (
    _dialect_insert,
    append_run_event,
    bulk_upsert_price_bars,
    create_run,
    finish_run,
    get_quota,
    get_run,
    get_run_events,
    increment_quota,
    insert_fundamentals,
    insert_verdict,
    latest_finished_run,
    latest_verdict,
    list_eval_results,
    list_runs,
    list_watched,
    save_eval_result,
    set_watched,
    upsert_instrument,
    upsert_news,
)

TS = datetime(2026, 6, 10, 12, 0, 0, tzinfo=UTC)
DAY = date(2026, 6, 10)


@pytest.fixture
async def engine():
    eng = create_async_engine("sqlite+aiosqlite:///:memory:")
    enable_sqlite_fks(eng)
    await create_all(eng)
    yield eng
    await eng.dispose()


@pytest.fixture
async def session(engine):
    maker = async_sessionmaker(engine, expire_on_commit=False)
    async with maker() as s:
        yield s


async def _count(session, model) -> int:
    return (await session.execute(select(func.count()).select_from(model))).scalar_one()


# ---------------------------------------------------------------- instruments


async def test_upsert_instrument_inserts_then_updates_same_id(session):
    first = await upsert_instrument(session, ticker="AAPL", exchange="NASDAQ", screener="america")
    assert first.id is not None
    assert first.name is None

    second = await upsert_instrument(
        session, ticker="AAPL", exchange="NASDAQ", screener="america",
        name="Apple Inc.", sector="Technology",
    )
    assert second.id == first.id
    assert second.name == "Apple Inc."
    assert second.sector == "Technology"
    assert await _count(session, Instrument) == 1


async def test_upsert_instrument_unknown_field_raises_typeerror(session):
    # Insert path: no row exists yet.
    with pytest.raises(TypeError, match="sectr"):
        await upsert_instrument(
            session, ticker="AAPL", exchange="NASDAQ", screener="america", sectr="Tech"
        )
    # Update path: the row exists, the kwarg is still bogus.
    await upsert_instrument(session, ticker="AAPL", exchange="NASDAQ", screener="america")
    with pytest.raises(TypeError, match="watchd"):
        await upsert_instrument(
            session, ticker="AAPL", exchange="NASDAQ", screener="america", watchd=True
        )
    assert await _count(session, Instrument) == 1


def test_dialect_insert_unbound_session_raises():
    with pytest.raises(RuntimeError, match="session is not bound to an engine"):
        _dialect_insert(AsyncSession())


async def test_set_watched_and_list_watched(session):
    aapl = await upsert_instrument(session, ticker="AAPL", exchange="NASDAQ", screener="america")
    await upsert_instrument(session, ticker="MSFT", exchange="NASDAQ", screener="america")

    assert await list_watched(session) == []
    await set_watched(session, aapl.id, True)
    watched = await list_watched(session)
    assert [i.ticker for i in watched] == ["AAPL"]
    await set_watched(session, aapl.id, False)
    assert await list_watched(session) == []


# ----------------------------------------------------------------- price bars


async def test_bulk_upsert_price_bars_idempotent(session):
    inst = await upsert_instrument(session, ticker="AAPL", exchange="NASDAQ", screener="america")
    bars = [
        {"ts": TS, "open": 1.0, "high": 2.0, "low": 0.5, "close": 1.5, "volume": 100},
        {"ts": TS + timedelta(days=1), "open": 1.5, "high": 2.5,
         "low": 1.0, "close": 2.0, "volume": 200},
    ]
    assert await bulk_upsert_price_bars(session, inst.id, bars) == 2
    assert await _count(session, PriceBar) == 2

    # Re-inserting the same bars keeps the count stable (conflict, no new rows).
    assert await bulk_upsert_price_bars(session, inst.id, bars) == 2  # attempted count
    assert await _count(session, PriceBar) == 2

    # Re-inserting a changed bar UPDATES in place (ON CONFLICT DO UPDATE): a
    # partial intraday bar gets corrected on the next refresh, count stable.
    corrected = {**bars[1], "close": 9.9, "high": 9.95, "volume": 999}
    assert await bulk_upsert_price_bars(session, inst.id, [corrected]) == 1
    assert await _count(session, PriceBar) == 2
    row = (
        await session.execute(
            select(PriceBar).where(PriceBar.ts == TS + timedelta(days=1))
        )
    ).scalar_one()
    assert row.close == 9.9
    assert row.high == 9.95
    assert row.volume == 999

    assert await bulk_upsert_price_bars(session, inst.id, []) == 0


# --------------------------------------------------------------- fundamentals


async def test_insert_fundamentals(session):
    inst = await upsert_instrument(session, ticker="AAPL", exchange="NASDAQ", screener="america")
    snap = await insert_fundamentals(
        session, inst.id, TS, market_cap=2.9e12, pe_ratio=28.5, payload={"src": "yf"}
    )
    assert snap.id is not None
    assert snap.market_cap == 2.9e12
    assert snap.payload == {"src": "yf"}


# ----------------------------------------------------------------------- news


async def test_upsert_news_dedupes_by_url(session):
    inst = await upsert_instrument(session, ticker="AAPL", exchange="NASDAQ", screener="america")
    items = [
        {"ts": TS, "title": "first", "url": "https://news.example/1", "source": "ex"},
        {"ts": TS, "title": "second", "url": "https://news.example/2"},
    ]
    assert await upsert_news(session, inst.id, items) == 2
    assert await _count(session, NewsItem) == 2

    # Same URLs again (different titles) must not create new rows.
    again = [
        {"ts": TS, "title": "first-redux", "url": "https://news.example/1"},
        {"ts": TS, "title": "third", "url": "https://news.example/3"},
    ]
    assert await upsert_news(session, inst.id, again) == 2
    assert await _count(session, NewsItem) == 3

    row = (
        await session.execute(
            select(NewsItem).where(NewsItem.url == "https://news.example/1")
        )
    ).scalar_one()
    assert row.title == "first"  # original kept (DO NOTHING)
    assert row.url_hash == hashlib.sha256(b"https://news.example/1").hexdigest()


# ------------------------------------------------------------------------ runs


async def test_run_lifecycle_create_events_finish_get_list(session):
    run = await create_run(session, "r1", "AAPL", "on")
    assert run.status == "running" and run.finished_at is None

    await append_run_event(session, "r1", 0, {"type": "start"})
    await append_run_event(session, "r1", 1, {"type": "node_complete", "node": "router"})

    finished = await finish_run(
        session, "r1", status="finished",
        final_decision={"action": "BUY", "score": 70},
        report="# AAPL", metrics=[{"node": "router", "cost": 0.0}],
    )
    assert finished is not None
    assert finished.status == "finished"
    assert finished.finished_at is not None
    assert finished.final_decision == {"action": "BUY", "score": 70}

    fetched = await get_run(session, "r1")
    assert fetched is not None and fetched.report == "# AAPL"
    assert await get_run(session, "missing") is None

    events = await get_run_events(session, "r1")
    assert [e.seq for e in events] == [0, 1]
    assert events[0].event == {"type": "start"}

    # list_runs: newest first, ticker filter, limit/offset.
    run2 = await create_run(session, "r2", "MSFT", "off")
    run.started_at = TS - timedelta(hours=2)
    run2.started_at = TS
    await session.flush()

    assert [r.run_id for r in await list_runs(session)] == ["r2", "r1"]
    assert [r.run_id for r in await list_runs(session, ticker="AAPL")] == ["r1"]
    assert [r.run_id for r in await list_runs(session, limit=1)] == ["r2"]
    assert [r.run_id for r in await list_runs(session, limit=1, offset=1)] == ["r1"]


async def test_finish_run_unknown_run_returns_none(session):
    assert await finish_run(session, "nope", status="finished") is None


async def test_latest_finished_run_respects_within_hours(session):
    now = datetime.now(UTC)

    old = await create_run(session, "old", "TSLA", "on")
    await finish_run(session, "old", status="finished")
    old.started_at = now - timedelta(hours=48)
    await session.flush()

    fresh = await create_run(session, "fresh", "AAPL", "on")
    await finish_run(session, "fresh", status="finished")
    fresh.started_at = now - timedelta(minutes=5)
    await session.flush()

    await create_run(session, "still-running", "AAPL", "on")  # never finished

    # A newer run that finished with status="error" must NOT win.
    errored = await create_run(session, "errored", "AAPL", "on")
    await finish_run(session, "errored", status="error")
    errored.started_at = now - timedelta(minutes=1)
    await session.flush()
    assert errored.finished_at is not None  # finished, but not status="finished"

    # No window: newest *successfully* finished run per ticker.
    got = await latest_finished_run(session, "AAPL")
    assert got is not None and got.run_id == "fresh"
    got = await latest_finished_run(session, "TSLA")
    assert got is not None and got.run_id == "old"

    # Window: the 48h-old TSLA run is outside 24h but inside 72h.
    assert await latest_finished_run(session, "TSLA", within_hours=24) is None
    got = await latest_finished_run(session, "TSLA", within_hours=72)
    assert got is not None and got.run_id == "old"

    # Unfinished runs never count.
    assert await latest_finished_run(session, "NVDA") is None


async def test_latest_finished_run_tie_breaks_on_run_id(session):
    t = datetime.now(UTC) - timedelta(minutes=10)
    a = await create_run(session, "a", "IBM", "on")
    await finish_run(session, "a", status="finished")
    b = await create_run(session, "b", "IBM", "on")
    await finish_run(session, "b", status="finished")
    a.started_at = t
    b.started_at = t  # identical started_at -> run_id.desc() decides
    await session.flush()

    got = await latest_finished_run(session, "IBM")
    assert got is not None and got.run_id == "b"


# ----------------------------------------------------------------------- quota


async def test_increment_quota_counts_and_is_per_key_day(session):
    assert await increment_quota(session, "global", DAY) == 1
    assert await increment_quota(session, "global", DAY) == 2
    assert await increment_quota(session, "global", DAY) == 3
    assert await get_quota(session, "global", DAY) == 3

    # Independent per key and per day.
    assert await increment_quota(session, "ip:1.2.3.4", DAY) == 1
    assert await increment_quota(session, "global", DAY + timedelta(days=1)) == 1
    assert await get_quota(session, "global", DAY) == 3
    assert await get_quota(session, "unknown", DAY) == 0


# ------------------------------------------------------------------------ eval


async def test_save_and_list_eval_results(session):
    await save_eval_result(session, "first", {"win_rate": 0.5}, [{"ticker": "AAPL"}])
    await save_eval_result(session, "second", {"win_rate": 0.7}, [{"ticker": "MSFT"}])

    results = await list_eval_results(session)
    assert [r.label for r in results] == ["second", "first"]  # newest first
    assert results[0].summary == {"win_rate": 0.7}
    assert results[0].pairs == [{"ticker": "MSFT"}]

    assert [r.label for r in await list_eval_results(session, limit=1)] == ["second"]


# --------------------------------------------------------------------- verdicts


async def test_insert_verdict_persists_row(session):
    row = await insert_verdict(session, "AAPL", {"action": "BUY", "score": 70}, TS)
    assert row.id is not None
    assert row.ticker == "AAPL"
    assert row.ts == TS
    assert row.decision == {"action": "BUY", "score": 70}


async def test_latest_verdict_newest_by_ts(session):
    await insert_verdict(session, "AAPL", {"action": "SELL", "score": 10}, TS)
    await insert_verdict(session, "AAPL", {"action": "BUY", "score": 90}, TS + timedelta(hours=1))

    row = await latest_verdict(session, "AAPL")
    assert row is not None
    assert row.decision == {"action": "BUY", "score": 90}
    assert row.ts == TS + timedelta(hours=1)


async def test_latest_verdict_id_desc_tie_break_on_equal_ts(session):
    first = await insert_verdict(session, "AAPL", {"v": 1}, TS)
    second = await insert_verdict(session, "AAPL", {"v": 2}, TS)  # same ts, higher id

    row = await latest_verdict(session, "AAPL")
    assert row is not None
    assert row.id == second.id and row.id != first.id
    assert row.decision == {"v": 2}


async def test_latest_verdict_is_per_ticker(session):
    await insert_verdict(session, "AAPL", {"action": "BUY"}, TS + timedelta(hours=2))
    await insert_verdict(session, "MSFT", {"action": "SELL"}, TS)

    row = await latest_verdict(session, "MSFT")
    assert row is not None and row.decision == {"action": "SELL"}
    assert await latest_verdict(session, "ZZZZ") is None

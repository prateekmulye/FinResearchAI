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
    bulk_append_run_events,
    bulk_upsert_price_bars,
    count_runs,
    create_run,
    finish_run,
    get_quota,
    get_run,
    get_run_events,
    increment_quota,
    insert_fundamentals,
    insert_verdict,
    latest_fundamentals,
    latest_verdict,
    list_eval_results,
    list_news_items,
    list_price_bars,
    list_runs,
    list_watched,
    resolve_instrument,
    save_eval_result,
    search_instruments,
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


async def test_watched_flag_upsert_and_list_watched(session):
    # The watched flag is written through upsert_instrument (seed_watchlist's
    # path); list_watched reads it back for the collector sweep.
    await upsert_instrument(session, ticker="AAPL", exchange="NASDAQ", screener="america")
    await upsert_instrument(session, ticker="MSFT", exchange="NASDAQ", screener="america")

    assert await list_watched(session) == []
    await upsert_instrument(
        session, ticker="AAPL", exchange="NASDAQ", screener="america", watched=True
    )
    watched = await list_watched(session)
    assert [i.ticker for i in watched] == ["AAPL"]
    await upsert_instrument(
        session, ticker="AAPL", exchange="NASDAQ", screener="america", watched=False
    )
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

    await bulk_append_run_events(
        session, "r1",
        [
            {"seq": 0, "event": {"type": "start"}},
            {"seq": 1, "event": {"type": "node_complete", "node": "router"}},
        ],
    )

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


async def test_bulk_append_run_events_inserts_in_order(session):
    await create_run(session, "r1", "AAPL", "on")
    rows = [
        {"seq": 0, "event": {"name": "start", "data": {}, "ts_ms": 1}},
        {"seq": 1, "event": {"name": "node_start", "data": {"node": "router"}, "ts_ms": 2}},
        {"seq": 2, "event": {"name": "done", "data": {}, "ts_ms": 3}},
    ]
    assert await bulk_append_run_events(session, "r1", rows) == 3

    events = await get_run_events(session, "r1")
    assert [e.seq for e in events] == [0, 1, 2]
    assert [e.event["name"] for e in events] == ["start", "node_start", "done"]


async def test_bulk_append_run_events_conflict_do_nothing(session):
    await create_run(session, "r1", "AAPL", "on")
    first = [{"seq": 0, "event": {"name": "start"}}, {"seq": 1, "event": {"name": "done"}}]
    await bulk_append_run_events(session, "r1", first)

    # Overlapping replay: existing seqs are kept (DO NOTHING), the new one lands.
    replay = [
        {"seq": 1, "event": {"name": "OVERWRITE-ATTEMPT"}},
        {"seq": 2, "event": {"name": "error"}},
    ]
    assert await bulk_append_run_events(session, "r1", replay) == 2  # attempted count

    events = await get_run_events(session, "r1")
    assert [e.seq for e in events] == [0, 1, 2]
    assert events[1].event == {"name": "done"}  # original kept


async def test_bulk_append_run_events_empty_returns_zero(session):
    await create_run(session, "r1", "AAPL", "on")
    assert await bulk_append_run_events(session, "r1", []) == 0
    assert await get_run_events(session, "r1") == []


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


# ----------------------------------------------------- WP-5 API read queries


async def _seed_instrument(session, ticker, exchange, name=None, watched=False):
    inst = await upsert_instrument(
        session, ticker=ticker, exchange=exchange, screener="america",
        **({"name": name} if name else {}), **({"watched": True} if watched else {}),
    )
    return inst


async def test_search_instruments_matches_ticker_or_name_case_insensitive(session):
    await _seed_instrument(session, "AAPL", "NASDAQ", name="Apple Inc.")
    await _seed_instrument(session, "MSFT", "NASDAQ", name="Microsoft Corporation")
    await _seed_instrument(session, "JPM", "NYSE", name="JPMorgan Chase & Co.")

    assert [i.ticker for i in await search_instruments(session, "aap")] == ["AAPL"]
    # name substring, case-insensitive
    assert [i.ticker for i in await search_instruments(session, "micro")] == ["MSFT"]
    # matches both ticker (AAPL) and name (Apple) once; ordered ticker asc
    assert [i.ticker for i in await search_instruments(session, "Ap")] == ["AAPL"]
    # empty q matches everything, ticker asc
    assert [i.ticker for i in await search_instruments(session, "")] == ["AAPL", "JPM", "MSFT"]
    assert [i.ticker for i in await search_instruments(session, "")][:2] == ["AAPL", "JPM"]
    assert len(await search_instruments(session, "", limit=2)) == 2
    assert await search_instruments(session, "zzz-no-match") == []


async def test_resolve_instrument_by_ticker_and_exchange(session):
    nse = await _seed_instrument(session, "RELIANCE.NS", "NSE")
    assert (await resolve_instrument(session, "RELIANCE.NS")).id == nse.id
    assert (await resolve_instrument(session, "RELIANCE.NS", exchange="NSE")).id == nse.id
    assert await resolve_instrument(session, "RELIANCE.NS", exchange="BSE") is None
    assert await resolve_instrument(session, "NOPE") is None


async def test_resolve_instrument_ambiguous_prefers_newest_price_bar(session):
    stale = await _seed_instrument(session, "DUAL", "NYSE")
    fresh = await _seed_instrument(session, "DUAL", "NASDAQ")
    bare = await _seed_instrument(session, "DUAL", "AMEX")  # no bars at all
    await bulk_upsert_price_bars(
        session, stale.id,
        [{"ts": TS - timedelta(days=30), "open": 1, "high": 1, "low": 1, "close": 1}],
    )
    await bulk_upsert_price_bars(
        session, fresh.id,
        [{"ts": TS, "open": 2, "high": 2, "low": 2, "close": 2}],
    )
    resolved = await resolve_instrument(session, "DUAL")
    assert resolved is not None and resolved.id == fresh.id
    # explicit exchange still wins over bar recency
    assert (await resolve_instrument(session, "DUAL", exchange="AMEX")).id == bare.id


async def test_list_price_bars_ascending_within_window(session):
    inst = await _seed_instrument(session, "AAPL", "NASDAQ")
    bars = [
        {"ts": TS - timedelta(days=d), "open": 1.0, "high": 2.0, "low": 0.5,
         "close": 1.5, "volume": 100 + d}
        for d in (400, 10, 5, 1)
    ]
    await bulk_upsert_price_bars(session, inst.id, bars)
    rows = await list_price_bars(session, inst.id, days=365)
    assert [r.ts for r in rows] == sorted(r.ts for r in rows)
    assert len(rows) == 3  # the 400-day-old bar is outside the window
    assert await list_price_bars(session, inst.id, days=365, interval="1h") == []


async def test_latest_fundamentals_newest_by_ts(session):
    inst = await _seed_instrument(session, "AAPL", "NASDAQ")
    assert await latest_fundamentals(session, inst.id) is None
    await insert_fundamentals(session, inst.id, TS - timedelta(days=2), pe_ratio=10.0)
    await insert_fundamentals(session, inst.id, TS, pe_ratio=28.0)
    snap = await latest_fundamentals(session, inst.id)
    assert snap is not None and snap.pe_ratio == 28.0


async def test_list_news_items_newest_first_with_limit(session):
    inst = await _seed_instrument(session, "AAPL", "NASDAQ")
    items = [
        {"ts": TS - timedelta(hours=h), "title": f"n{h}", "url": f"https://x.com/{h}"}
        for h in (3, 1, 2)
    ]
    await upsert_news(session, inst.id, items)
    rows = await list_news_items(session, inst.id)
    assert [r.title for r in rows] == ["n1", "n2", "n3"]
    assert [r.title for r in await list_news_items(session, inst.id, limit=2)] == ["n1", "n2"]


async def test_list_runs_status_filter_and_count_runs(session):
    await create_run(session, "r1", "AAPL", "on")
    await create_run(session, "r2", "AAPL", "on")
    await create_run(session, "r3", "MSFT", "off")
    await finish_run(session, "r1", status="finished")
    await finish_run(session, "r3", status="error")

    assert {r.run_id for r in await list_runs(session, status="finished")} == {"r1"}
    assert {r.run_id for r in await list_runs(session, ticker="AAPL", status="running")} == {"r2"}
    assert await count_runs(session) == 3
    assert await count_runs(session, ticker="AAPL") == 2
    assert await count_runs(session, ticker="AAPL", status="finished") == 1
    assert await count_runs(session, status="aborted") == 0

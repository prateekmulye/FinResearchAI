# tests/warehouse/test_models.py
"""Warehouse ORM models: create_all on in-memory SQLite, per-table roundtrips,
unique-constraint enforcement (IntegrityError on duplicates), FK enforcement
(PRAGMA foreign_keys=ON), and tz-aware datetime roundtrips."""
from __future__ import annotations

from datetime import UTC, date, datetime, timedelta, timezone

import pytest
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from src.warehouse.bootstrap import create_all
from src.warehouse.db import enable_sqlite_fks
from src.warehouse.models import (
    EMBEDDING_DIM,
    DemoQuota,
    EvalResult,
    FundamentalsSnapshot,
    Instrument,
    NewsItem,
    PriceBar,
    Run,
    RunEvent,
    Verdict,
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


async def _make_instrument(session, **overrides) -> Instrument:
    fields = {"ticker": "AAPL", "exchange": "NASDAQ", "screener": "america"}
    fields.update(overrides)
    inst = Instrument(**fields)
    session.add(inst)
    await session.flush()
    return inst


def test_embedding_dim_constant():
    assert EMBEDDING_DIM == 384


async def test_insert_and_read_back_one_row_per_table(session):
    inst = await _make_instrument(
        session, name="Apple Inc.", country="US", currency="USD", sector="Technology"
    )
    assert inst.id is not None
    assert inst.watched is False
    assert inst.created_at is not None and inst.updated_at is not None

    session.add_all(
        [
            PriceBar(
                instrument_id=inst.id, ts=TS, open=190.0, high=195.5,
                low=189.2, close=194.1, volume=10_000_000_000,
            ),
            FundamentalsSnapshot(
                instrument_id=inst.id, ts=TS, market_cap=2.9e12, pe_ratio=28.5,
                eps=6.4, revenue_growth=0.05, profit_margin=0.25, payload={"raw": True},
            ),
            NewsItem(
                instrument_id=inst.id, ts=TS, title="Apple ships",
                url="https://news.example/apple", source="example",
                snippet="snippet", url_hash="a" * 64, embedding=[0.1] * EMBEDDING_DIM,
            ),
            Run(run_id="run-1", ticker="AAPL", debate_mode="on"),
            EvalResult(label="demo", summary={"n": 1}, pairs=[{"on": 1, "off": 0}]),
            DemoQuota(key="global", day=DAY, count=3),
        ]
    )
    await session.flush()
    session.add(RunEvent(run_id="run-1", seq=0, event={"type": "start"}))
    await session.commit()

    bar = (await session.execute(select(PriceBar))).scalar_one()
    assert bar.interval == "1d"  # default applied
    assert bar.volume == 10_000_000_000  # BigInteger survives

    snap = (await session.execute(select(FundamentalsSnapshot))).scalar_one()
    assert snap.payload == {"raw": True}

    news = (await session.execute(select(NewsItem))).scalar_one()
    assert news.embedding == pytest.approx([0.1] * EMBEDDING_DIM)

    run = await session.get(Run, "run-1")
    assert run is not None
    assert run.status == "running"
    assert run.started_at is not None and run.finished_at is None

    evt = (await session.execute(select(RunEvent))).scalar_one()
    assert evt.event == {"type": "start"}

    ev = (await session.execute(select(EvalResult))).scalar_one()
    assert ev.summary == {"n": 1} and ev.pairs == [{"on": 1, "off": 0}]
    assert ev.created_at is not None

    quota = (await session.execute(select(DemoQuota))).scalar_one()
    assert (quota.key, quota.day, quota.count) == ("global", DAY, 3)


async def test_instruments_unique_ticker_exchange(session):
    await _make_instrument(session)
    with pytest.raises(IntegrityError):
        await _make_instrument(session)
    await session.rollback()
    # Same ticker on a different exchange is allowed.
    await _make_instrument(session)
    await _make_instrument(session, exchange="NSE", screener="india")
    n = (await session.execute(select(func.count()).select_from(Instrument))).scalar_one()
    assert n == 2


async def test_price_bars_unique_instrument_interval_ts(session):
    inst = await _make_instrument(session)
    kw = {"instrument_id": inst.id, "ts": TS, "interval": "1d",
          "open": 1.0, "high": 2.0, "low": 0.5, "close": 1.5}
    session.add(PriceBar(**kw))
    await session.flush()
    session.add(PriceBar(**kw))
    with pytest.raises(IntegrityError):
        await session.flush()


async def test_news_items_unique_url_hash(session):
    inst = await _make_instrument(session)
    kw = {"instrument_id": inst.id, "ts": TS, "title": "t",
          "url": "https://x.example", "url_hash": "b" * 64}
    session.add(NewsItem(**kw))
    await session.flush()
    session.add(NewsItem(**kw))
    with pytest.raises(IntegrityError):
        await session.flush()


async def test_run_events_unique_run_id_seq(session):
    session.add(Run(run_id="run-u", ticker="AAPL", debate_mode="on"))
    await session.flush()
    session.add(RunEvent(run_id="run-u", seq=1, event={"a": 1}))
    await session.flush()
    session.add(RunEvent(run_id="run-u", seq=1, event={"a": 2}))
    with pytest.raises(IntegrityError):
        await session.flush()


async def test_demo_quota_unique_key_day(session):
    session.add(DemoQuota(key="ip:1.2.3.4", day=DAY, count=1))
    await session.flush()
    session.add(DemoQuota(key="ip:1.2.3.4", day=DAY, count=2))
    with pytest.raises(IntegrityError):
        await session.flush()


# ---------------------------------------------------------- FK enforcement


async def test_orphan_run_event_rejected_on_sqlite(session):
    """PRAGMA foreign_keys=ON makes SQLite reject orphans like Postgres does."""
    session.add(RunEvent(run_id="ghost", seq=0, event={"type": "orphan"}))
    with pytest.raises(IntegrityError):
        await session.flush()


async def test_delete_instrument_cascades_price_bars(session):
    inst = await _make_instrument(session)
    session.add(
        PriceBar(instrument_id=inst.id, ts=TS, open=1.0, high=2.0, low=0.5, close=1.5)
    )
    await session.flush()
    await session.delete(inst)
    await session.flush()
    n = (await session.execute(select(func.count()).select_from(PriceBar))).scalar_one()
    assert n == 0


# ------------------------------------------------------- datetimes & indexes


async def test_datetime_columns_return_utc_aware_on_sqlite(engine):
    """An aware non-UTC bind comes back as the same instant with tzinfo=UTC."""
    ist = timezone(timedelta(hours=5, minutes=30))
    maker = async_sessionmaker(engine, expire_on_commit=False)
    async with maker() as s1:
        inst = Instrument(ticker="AAPL", exchange="NASDAQ", screener="america")
        s1.add(inst)
        await s1.flush()
        s1.add(
            PriceBar(
                instrument_id=inst.id, ts=TS.astimezone(ist),
                open=1.0, high=2.0, low=0.5, close=1.5,
            )
        )
        await s1.commit()
    async with maker() as s2:  # fresh session: forces result-row processing
        bar = (await s2.execute(select(PriceBar))).scalar_one()
        assert bar.ts.tzinfo == UTC
        assert bar.ts == TS
        inst2 = (await s2.execute(select(Instrument))).scalar_one()
        assert inst2.created_at.tzinfo == UTC
        assert inst2.updated_at.tzinfo == UTC


def test_news_items_has_instrument_ts_index():
    names = {ix.name for ix in NewsItem.__table__.indexes}
    assert "ix_news_items_instrument_id_ts" in names


def test_verdicts_has_ticker_ts_index():
    names = {ix.name for ix in Verdict.__table__.indexes}
    assert "ix_verdicts_ticker_ts" in names

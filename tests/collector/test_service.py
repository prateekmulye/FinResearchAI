# tests/collector/test_service.py
"""collect_once (WP-3): sweeps watched instruments with injected fetchers,
isolates per-instrument failures, and no-ops when the warehouse is disabled."""
from __future__ import annotations

from datetime import UTC, datetime, timedelta

from sqlalchemy import func, select

from src.collector.service import collect_once
from src.warehouse.db import session_scope
from src.warehouse.models import FundamentalsSnapshot, PriceBar
from src.warehouse.repos import upsert_instrument

NOW = datetime(2026, 6, 10, 12, 0, 0, tzinfo=UTC)


async def _watch(ticker: str, exchange: str = "NASDAQ", screener: str = "america") -> None:
    async with session_scope() as session:
        await upsert_instrument(
            session, ticker=ticker, exchange=exchange, screener=screener, watched=True
        )


def _bars(n: int) -> list[dict]:
    return [
        {"ts": NOW - timedelta(days=n - i), "open": 1.0, "high": 2.0,
         "low": 0.5, "close": 1.5, "volume": 100}
        for i in range(n)
    ]


async def _count(model) -> int:
    async with session_scope() as session:
        return (
            await session.execute(select(func.count()).select_from(model))
        ).scalar_one()


async def test_collect_once_noop_when_disabled():
    # env_isolation (autouse) scrubbed DATABASE_URL -> warehouse disabled.
    summary = await collect_once()
    assert summary == {"instruments": 0, "prices_rows": 0, "fundamentals": 0, "errors": []}


async def test_collect_once_sweeps_watched_instruments(sqlite_warehouse, caplog):
    await _watch("AAPL")
    await _watch("MSFT")

    async def price_fetch(ticker, start):
        return _bars(3)

    async def fundamentals_fetch(ticker):
        return {"market_cap": 1e12, "trailing_pe": 20.0}

    with caplog.at_level("INFO"):
        summary = await collect_once(fetch=price_fetch, fundamentals_fetch=fundamentals_fetch)

    assert summary["instruments"] == 2
    assert summary["prices_rows"] == 6
    assert summary["fundamentals"] == 2
    assert summary["errors"] == []
    assert await _count(PriceBar) == 6
    assert await _count(FundamentalsSnapshot) == 2
    # The summary line reports ok/errors explicitly ("instruments" counts only
    # fully-successful tickers, so the log must not imply a total).
    assert any("ok=2 errors=0" in r.getMessage() for r in caplog.records), (
        "INFO summary line with ok=N errors=M expected"
    )


async def test_collect_once_isolates_per_instrument_failure(sqlite_warehouse):
    """The erroring ticker is recorded in errors; the healthy ticker is still
    fully processed — one bad instrument never stops the sweep."""
    await _watch("BAD")
    await _watch("GOOD")

    async def price_fetch(ticker, start):
        return _bars(2)

    async def fundamentals_fetch(ticker):
        if ticker == "BAD":
            raise RuntimeError("yfinance exploded for BAD")
        return {"market_cap": 5e11}

    summary = await collect_once(fetch=price_fetch, fundamentals_fetch=fundamentals_fetch)

    assert summary["errors"] == ["BAD (NASDAQ)"]  # "TICKER (EXCHANGE)" strings
    assert summary["instruments"] == 1   # only the healthy ticker completed
    assert summary["fundamentals"] == 1
    assert await _count(FundamentalsSnapshot) == 1


async def test_collect_once_skips_fresh_fundamentals(sqlite_warehouse):
    from src.warehouse.ingest import record_fundamentals

    await _watch("AAPL")
    await record_fundamentals("AAPL", "NASDAQ", "america", {"market_cap": 1.0})

    async def price_fetch(ticker, start):
        return []

    async def fundamentals_fetch(ticker):
        raise AssertionError("fundamentals fetch must be skipped when fresh")

    summary = await collect_once(fetch=price_fetch, fundamentals_fetch=fundamentals_fetch)
    assert summary["instruments"] == 1
    assert summary["fundamentals"] == 0
    assert summary["errors"] == []

# src/warehouse/ingest.py
"""High-level write-through ingest API for the warehouse (WP-3).

Contract (every public function):
- async; no-op when the warehouse is disabled (``DATABASE_URL`` unset) —
  returning ``None``/``False``/``0`` without touching the DB or any fetcher;
- opens its own ``session_scope()`` (callers never pass sessions in);
- NEVER raises: any exception is logged at WARNING (with traceback) and
  degraded to the no-op return value. Node hooks and the collector therefore
  call these bare — a DB/fetch problem cannot affect a run or the sweep.

Freshness helpers (``fundamentals_stale`` / ``prices_stale``) answer "should we
fetch?": True only when the warehouse is enabled AND the newest row is missing
or older than ``max_age_hours``. Disabled or erroring DB -> False, so callers
skip the redundant fetch rather than hammer a dead backend.
"""
from __future__ import annotations

import asyncio
import logging
from collections.abc import Awaitable, Callable
from datetime import UTC, datetime, timedelta
from typing import Any

from sqlalchemy import select

from src.warehouse.db import session_scope, warehouse_enabled
from src.warehouse.models import FundamentalsSnapshot, Instrument, PriceBar
from src.warehouse.repos import (
    bulk_append_run_events,
    bulk_upsert_price_bars,
    create_run,
    finish_run,
    insert_fundamentals,
    upsert_instrument,
    upsert_news,
)

_LOG = logging.getLogger(__name__)

# Keep bulk inserts comfortably below asyncpg's ~32k bind-param ceiling
# (8 params/row -> ~4k bars max per call; see bulk_upsert_price_bars).
_PRICE_CHUNK = 2000

# Run events are 3 params/row, but token streams can number thousands; chunk
# conservatively at the same 2000-row boundary as price bars.
_RUN_EVENT_CHUNK = 2000

FetchBars = Callable[[str, datetime | None], Awaitable[list[dict[str, Any]]]]


def _utcnow() -> datetime:
    return datetime.now(UTC)


def _to_utc(ts: datetime) -> datetime:
    """Normalize a datetime to aware-UTC (naive values are assumed UTC)."""
    if ts.tzinfo is None:
        return ts.replace(tzinfo=UTC)
    return ts.astimezone(UTC)


def _drop_nones(**fields: Any) -> dict[str, Any]:
    """Optional upsert kwargs: omit Nones so re-upserts don't clobber existing values."""
    return {k: v for k, v in fields.items() if v is not None}


# ------------------------------------------------------------------ instruments


async def ensure_instrument(
    ticker: str,
    exchange: str,
    screener: str,
    *,
    name: str | None = None,
    country: str | None = None,
    currency: str | None = None,
    sector: str | None = None,
) -> int | None:
    """Upsert the instrument and return its id; None when disabled or on error."""
    if not warehouse_enabled():
        return None
    try:
        async with session_scope() as session:
            row = await upsert_instrument(
                session,
                ticker=ticker,
                exchange=exchange,
                screener=screener,
                **_drop_nones(name=name, country=country, currency=currency, sector=sector),
            )
            return row.id
    except Exception as exc:
        _LOG.warning(
            "warehouse ingest: ensure_instrument failed for %s/%s: %s",
            ticker, exchange, exc, exc_info=exc,
        )
        return None


# ---------------------------------------------------------------- fundamentals

# Known FundamentalsSnapshot columns <- snapshot-dict keys (first present wins).
# The yfinance tool emits trailing_pe/profit_margins; canonical names also accepted.
_FUNDAMENTALS_COLUMN_KEYS: dict[str, tuple[str, ...]] = {
    "market_cap": ("market_cap",),
    "pe_ratio": ("pe_ratio", "trailing_pe"),
    "eps": ("eps",),
    "revenue_growth": ("revenue_growth",),
    "profit_margin": ("profit_margin", "profit_margins"),
}


async def record_fundamentals(
    ticker: str, exchange: str, screener: str, snapshot: dict[str, Any]
) -> bool:
    """Persist one fundamentals snapshot (known keys -> columns, full dict -> payload)."""
    if not warehouse_enabled():
        return False
    try:
        fields = {
            column: next((snapshot[k] for k in keys if snapshot.get(k) is not None), None)
            for column, keys in _FUNDAMENTALS_COLUMN_KEYS.items()
        }
        async with session_scope() as session:
            row = await upsert_instrument(
                session,
                ticker=ticker,
                exchange=exchange,
                screener=screener,
                **_drop_nones(name=snapshot.get("name"), sector=snapshot.get("sector")),
            )
            await insert_fundamentals(
                session, row.id, _utcnow(), payload=dict(snapshot), **fields
            )
        return True
    except Exception as exc:
        _LOG.warning(
            "warehouse ingest: record_fundamentals failed for %s/%s: %s",
            ticker, exchange, exc, exc_info=exc,
        )
        return False


# ------------------------------------------------------------------------- news


async def record_news(
    ticker: str, exchange: str, screener: str, items: list[dict[str, Any]]
) -> int:
    """Persist news items (deduped by url_hash). Returns the attempted count.

    ``ts`` is the item's ``published`` datetime when present AND tz-aware;
    otherwise now-UTC (naive published values are untrusted and ignored).
    Items without a url are skipped (url is the dedupe identity).
    """
    if not warehouse_enabled():
        return 0
    try:
        rows: list[dict[str, Any]] = []
        for item in items:
            url = item.get("url")
            if not url:
                continue
            published = item.get("published") or item.get("ts")
            ts = (
                published.astimezone(UTC)
                if isinstance(published, datetime) and published.tzinfo is not None
                else _utcnow()
            )
            rows.append(
                {
                    "ts": ts,
                    "title": item.get("title") or "",
                    "url": url,
                    "source": item.get("source"),
                    "snippet": item.get("snippet"),
                }
            )
        if not rows:
            return 0
        async with session_scope() as session:
            inst = await upsert_instrument(
                session, ticker=ticker, exchange=exchange, screener=screener
            )
            return await upsert_news(session, inst.id, rows)
    except Exception as exc:
        _LOG.warning(
            "warehouse ingest: record_news failed for %s/%s: %s",
            ticker, exchange, exc, exc_info=exc,
        )
        return 0


# ------------------------------------------------------------------ price bars


async def _fetch_daily_bars(ticker: str, start: datetime | None) -> list[dict[str, Any]]:
    """Default price fetcher: daily OHLCV from yfinance, off the event loop.

    APP_FAKE_LLM seam (WP-5): flag read at CALL time; deterministic generated
    bars, no network (same per-tool-seam choice as src/tools/*)."""
    from src.config.settings import get_settings  # local: ingest stays settings-free otherwise

    if get_settings().fake_llm:
        from src.tools.fake_data import fake_daily_bars

        return fake_daily_bars(ticker, start)

    def _history() -> list[dict[str, Any]]:
        import yfinance as yf

        frame = yf.Ticker(ticker).history(start=start, interval="1d", auto_adjust=False)
        rows: list[dict[str, Any]] = []
        for ts, row in frame.iterrows():
            volume = row.get("Volume")
            rows.append(
                {
                    "ts": ts.to_pydatetime(),
                    "open": float(row["Open"]),
                    "high": float(row["High"]),
                    "low": float(row["Low"]),
                    "close": float(row["Close"]),
                    # NaN-safe without importing pandas: NaN != NaN.
                    "volume": int(volume) if volume is not None and volume == volume else None,
                }
            )
        return rows

    return await asyncio.to_thread(_history)


async def refresh_prices(
    ticker: str,
    exchange: str,
    screener: str,
    *,
    period_days: int = 365,
    fetch: FetchBars | None = None,
) -> int:
    """Fetch daily OHLCV bars and bulk-upsert them; returns rows attempted.

    Incremental: when the instrument already has 1d bars, the fetch starts AT
    the newest stored ts (start = newest, NOT newest + 1 day) so the newest
    day — possibly captured mid-session as a partial intraday bar — is
    re-fetched and corrected by the ON CONFLICT DO UPDATE upsert; otherwise
    the backfill window is ``period_days`` ago. The fetch runs OUTSIDE any DB
    session (no transaction held across network I/O). Bar timestamps are
    normalized to aware-UTC and inserts are chunked at 2000 rows.
    """
    if not warehouse_enabled():
        return 0
    fetch = fetch or _fetch_daily_bars
    try:
        async with session_scope() as session:
            inst = await upsert_instrument(
                session, ticker=ticker, exchange=exchange, screener=screener
            )
            instrument_id = inst.id
            newest = (
                await session.execute(
                    select(PriceBar.ts)
                    .where(PriceBar.instrument_id == instrument_id, PriceBar.interval == "1d")
                    .order_by(PriceBar.ts.desc())
                    .limit(1)
                )
            ).scalar_one_or_none()

        # Start AT the newest stored day (not +1) so a partial intraday bar is
        # re-fetched and corrected by the upsert instead of frozen forever.
        start = newest if newest else _utcnow() - timedelta(days=period_days)
        bars = await fetch(ticker, start)
        if not bars:
            return 0

        rows = [{**bar, "ts": _to_utc(bar["ts"])} for bar in bars]
        attempted = 0
        async with session_scope() as session:
            for i in range(0, len(rows), _PRICE_CHUNK):
                attempted += await bulk_upsert_price_bars(
                    session, instrument_id, rows[i : i + _PRICE_CHUNK]
                )
        return attempted
    except Exception as exc:
        _LOG.warning(
            "warehouse ingest: refresh_prices failed for %s/%s: %s",
            ticker, exchange, exc, exc_info=exc,
        )
        return 0


# ------------------------------------------------------------ run persistence
#
# WP-4: every API analysis run lands as a `runs` row (created at stream start,
# finished at done/error/abort) plus the full ordered SSE event stream in
# `run_events` — the Research Library + timeline replay UI (WP-5/8) read these.
# Same module contract as everything above: disabled -> no-op, errors -> log
# WARNING and degrade, NEVER raise into the stream.


async def record_run_start(run_id: str, ticker: str, debate_mode: str) -> bool:
    """Create the `runs` row (status "running"). True on success."""
    if not warehouse_enabled():
        return False
    try:
        async with session_scope() as session:
            await create_run(session, run_id, ticker, debate_mode)
        return True
    except Exception as exc:
        _LOG.warning(
            "warehouse ingest: record_run_start failed for %s (%s): %s",
            run_id, ticker, exc, exc_info=exc,
        )
        return False


async def record_run_events(run_id: str, events: list[dict[str, Any]]) -> int:
    """Bulk-append the run's FULL ordered SSE event stream. Returns attempted count.

    Seq contract: ``seq`` is assigned by 0-based list position — callers buffer
    the entire stream and write it ONCE at run end (never per-event during
    streaming). Partial/incremental appends are not supported; replaying the
    same (or a prefix-extended) list is idempotent because the underlying insert
    is ON CONFLICT (run_id, seq) DO NOTHING. Each input dict is stored verbatim
    as the ``event`` JSON (the stream layer shapes ``{"name", "data", "ts_ms"}``).
    Inserts are chunked at 2000 rows.
    """
    if not warehouse_enabled() or not events:
        return 0
    try:
        rows = [{"seq": seq, "event": event} for seq, event in enumerate(events)]
        attempted = 0
        async with session_scope() as session:
            for i in range(0, len(rows), _RUN_EVENT_CHUNK):
                attempted += await bulk_append_run_events(
                    session, run_id, rows[i : i + _RUN_EVENT_CHUNK]
                )
        return attempted
    except Exception as exc:
        _LOG.warning(
            "warehouse ingest: record_run_events failed for %s (%d events): %s",
            run_id, len(events), exc, exc_info=exc,
        )
        return 0


async def record_run_finish(
    run_id: str,
    *,
    status: str,
    final_decision: dict[str, Any] | None = None,
    report: str | None = None,
    metrics: list[Any] | dict[str, Any] | None = None,
) -> bool:
    """Finalize the `runs` row. True iff the row existed and was updated.

    Status vocabulary: "finished" (done, with payload), "error" (error event,
    no payload), "aborted" (client disconnected before done/error). Only
    "finished" runs are honored by ``repos.latest_finished_run`` — verdict-cache
    semantics are preserved.
    """
    if not warehouse_enabled():
        return False
    try:
        async with session_scope() as session:
            run = await finish_run(
                session,
                run_id,
                status=status,
                final_decision=final_decision,
                report=report,
                metrics=metrics,
            )
        if run is None:
            _LOG.warning(
                "warehouse ingest: record_run_finish found no runs row for %s "
                "(record_run_start likely failed earlier)", run_id,
            )
            return False
        return True
    except Exception as exc:
        _LOG.warning(
            "warehouse ingest: record_run_finish failed for %s (status=%s): %s",
            run_id, status, exc, exc_info=exc,
        )
        return False


# ----------------------------------------------------------- freshness helpers


async def _newest_ts(model: Any, ticker: str, exchange: str) -> datetime | None:
    """Newest ``model.ts`` for the (ticker, exchange) instrument, or None."""
    async with session_scope() as session:
        instrument_id = (
            await session.execute(
                select(Instrument.id).where(
                    Instrument.ticker == ticker, Instrument.exchange == exchange
                )
            )
        ).scalar_one_or_none()
        if instrument_id is None:
            return None
        stmt = (
            select(model.ts)
            .where(model.instrument_id == instrument_id)
            .order_by(model.ts.desc())
            .limit(1)
        )
        if model is PriceBar:
            # Staleness must agree with what refresh_prices stores (1d bars
            # only): scope the newest-ts lookup to interval == "1d" so a stray
            # intraday row can never mask daily-bar staleness.
            stmt = stmt.where(PriceBar.interval == "1d")
        return (await session.execute(stmt)).scalar_one_or_none()


async def _stale(model: Any, ticker: str, exchange: str, max_age_hours: int, label: str) -> bool:
    if not warehouse_enabled():
        return False
    try:
        newest = await _newest_ts(model, ticker, exchange)
    except Exception as exc:
        _LOG.warning(
            "warehouse ingest: %s staleness check failed for %s/%s: %s",
            label, ticker, exchange, exc, exc_info=exc,
        )
        return False
    if newest is None:
        return True
    return _utcnow() - newest > timedelta(hours=max_age_hours)


async def fundamentals_stale(ticker: str, exchange: str, *, max_age_hours: int = 24) -> bool:
    """True iff the newest fundamentals snapshot is missing or older than the window."""
    return await _stale(FundamentalsSnapshot, ticker, exchange, max_age_hours, "fundamentals")


async def prices_stale(ticker: str, exchange: str, *, max_age_hours: int = 24) -> bool:
    """True iff the newest stored price bar is missing or older than the window.

    Note: compares against the newest BAR ts (market dates), so weekends/holidays
    may report stale; the follow-up incremental fetch is then a cheap no-op.
    """
    return await _stale(PriceBar, ticker, exchange, max_age_hours, "prices")

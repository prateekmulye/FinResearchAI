# src/warehouse/repos.py
"""Async repository functions for the warehouse.

Every function takes an ``AsyncSession`` as its first argument — no hidden session
creation; callers own transaction boundaries (e.g. via ``session_scope``).
Bulk upserts use the dialect-aware ``INSERT ... ON CONFLICT`` (postgresql vs
sqlite) chosen from ``session.bind.dialect.name``.
"""
from __future__ import annotations

import hashlib
from datetime import UTC, date, datetime, timedelta
from typing import Any, Callable

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from src.warehouse.models import (
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


def _utcnow() -> datetime:
    return datetime.now(UTC)


def _dialect_insert(session: AsyncSession) -> Callable[..., Any]:
    """Return the ON-CONFLICT-capable ``insert`` constructor for the bound dialect."""
    # An unbound AsyncSession has no ``bind`` proxy attribute at all.
    bind = getattr(session, "bind", None)
    if bind is None:
        raise RuntimeError("session is not bound to an engine")
    if bind.dialect.name == "postgresql":
        from sqlalchemy.dialects.postgresql import insert as pg_insert

        return pg_insert
    from sqlalchemy.dialects.sqlite import insert as sqlite_insert

    return sqlite_insert


# ------------------------------------------------------------------ instruments

# Optional upsert kwargs must be real mapped columns; the key/identity fields are
# keyword-only parameters of upsert_instrument itself.
_INSTRUMENT_OPTIONAL_FIELDS = frozenset(Instrument.__table__.columns.keys()) - {
    "id",
    "ticker",
    "exchange",
    "screener",
}


async def upsert_instrument(
    session: AsyncSession, *, ticker: str, exchange: str, screener: str, **optional: Any
) -> Instrument:
    """Insert or update-by-(ticker, exchange) atomically; returns the ORM row.

    Race-safe: a single dialect-aware ``INSERT ... ON CONFLICT (ticker, exchange)
    DO UPDATE`` (no SELECT-then-INSERT window), followed by a re-select to return
    the refreshed ORM row.
    """
    unknown = set(optional) - _INSTRUMENT_OPTIONAL_FIELDS
    if unknown:
        raise TypeError(
            f"upsert_instrument() got unknown field(s): {', '.join(sorted(unknown))}"
        )
    insert = _dialect_insert(session)
    stmt = (
        insert(Instrument)
        .values(ticker=ticker, exchange=exchange, screener=screener, **optional)
        .on_conflict_do_update(
            index_elements=["ticker", "exchange"],
            # onupdate defaults don't fire for ON CONFLICT DO UPDATE: set
            # updated_at explicitly (last, so it always reflects this upsert).
            set_={"screener": screener, **optional, "updated_at": _utcnow()},
        )
    )
    await session.execute(stmt)
    row = (
        await session.execute(
            select(Instrument)
            .where(Instrument.ticker == ticker, Instrument.exchange == exchange)
            .execution_options(populate_existing=True)
        )
    ).scalar_one()
    return row


async def set_watched(session: AsyncSession, instrument_id: int, watched: bool) -> None:
    await session.execute(
        update(Instrument).where(Instrument.id == instrument_id).values(watched=watched)
    )


async def list_watched(session: AsyncSession) -> list[Instrument]:
    result = await session.execute(
        select(Instrument).where(Instrument.watched.is_(True)).order_by(Instrument.ticker)
    )
    return list(result.scalars().all())


# ------------------------------------------------------------------- price bars


async def bulk_upsert_price_bars(
    session: AsyncSession, instrument_id: int, bars: list[dict[str, Any]]
) -> int:
    """Idempotent bulk insert; ON CONFLICT (instrument_id, interval, ts) DO NOTHING.

    Returns the attempted (input) count, not the inserted count.
    """
    # asyncpg's ~32k bind-param ceiling caps one call at ~4k bars (8 params/row);
    # chunk upstream for backfills.
    if not bars:
        return 0
    rows = [
        {
            "instrument_id": instrument_id,
            "ts": bar["ts"],
            "interval": bar.get("interval", "1d"),
            "open": bar["open"],
            "high": bar["high"],
            "low": bar["low"],
            "close": bar["close"],
            "volume": bar.get("volume"),
        }
        for bar in bars
    ]
    insert = _dialect_insert(session)
    stmt = (
        insert(PriceBar)
        .values(rows)
        .on_conflict_do_nothing(index_elements=["instrument_id", "interval", "ts"])
    )
    await session.execute(stmt)
    return len(rows)


# ----------------------------------------------------------------- fundamentals


async def insert_fundamentals(
    session: AsyncSession, instrument_id: int, ts: datetime, **fields: Any
) -> FundamentalsSnapshot:
    snap = FundamentalsSnapshot(instrument_id=instrument_id, ts=ts, **fields)
    session.add(snap)
    await session.flush()
    return snap


# ------------------------------------------------------------------------- news


async def upsert_news(
    session: AsyncSession, instrument_id: int, items: list[dict[str, Any]]
) -> int:
    """Insert news items, deduped by sha256(url) — ON CONFLICT (url_hash) DO NOTHING.

    Returns the attempted (input) count, not the inserted count.
    """
    # asyncpg's ~32k bind-param ceiling bounds one bulk call; chunk upstream for backfills.
    if not items:
        return 0
    rows = []
    for item in items:
        url = item["url"]
        rows.append(
            {
                "instrument_id": instrument_id,
                "ts": item["ts"],
                "title": item["title"],
                "url": url,
                "source": item.get("source"),
                "snippet": item.get("snippet"),
                "url_hash": hashlib.sha256(url.encode("utf-8")).hexdigest(),
                "embedding": item.get("embedding"),
            }
        )
    insert = _dialect_insert(session)
    stmt = insert(NewsItem).values(rows).on_conflict_do_nothing(index_elements=["url_hash"])
    await session.execute(stmt)
    return len(rows)


# ------------------------------------------------------------------------- runs


async def create_run(
    session: AsyncSession, run_id: str, ticker: str, debate_mode: str
) -> Run:
    run = Run(run_id=run_id, ticker=ticker, debate_mode=debate_mode)
    session.add(run)
    await session.flush()
    return run


async def finish_run(
    session: AsyncSession,
    run_id: str,
    *,
    status: str,
    final_decision: dict[str, Any] | None = None,
    report: str | None = None,
    metrics: Any | None = None,
) -> Run | None:
    run = await session.get(Run, run_id)
    if run is None:
        return None
    run.status = status
    run.finished_at = _utcnow()
    if final_decision is not None:
        run.final_decision = final_decision
    if report is not None:
        run.report = report
    if metrics is not None:
        run.metrics = metrics
    await session.flush()
    return run


async def append_run_event(
    session: AsyncSession, run_id: str, seq: int, event: dict[str, Any]
) -> RunEvent:
    row = RunEvent(run_id=run_id, seq=seq, event=event)
    session.add(row)
    await session.flush()
    return row


async def get_run(session: AsyncSession, run_id: str) -> Run | None:
    return await session.get(Run, run_id)


async def get_run_events(session: AsyncSession, run_id: str) -> list[RunEvent]:
    result = await session.execute(
        select(RunEvent).where(RunEvent.run_id == run_id).order_by(RunEvent.seq)
    )
    return list(result.scalars().all())


async def list_runs(
    session: AsyncSession, *, ticker: str | None = None, limit: int = 50, offset: int = 0
) -> list[Run]:
    """Runs newest-first (by started_at), optionally filtered by ticker."""
    stmt = select(Run).order_by(Run.started_at.desc(), Run.run_id.desc())
    if ticker is not None:
        stmt = stmt.where(Run.ticker == ticker)
    result = await session.execute(stmt.limit(limit).offset(offset))
    return list(result.scalars().all())


async def latest_finished_run(
    session: AsyncSession, ticker: str, *, within_hours: int | None = None
) -> Run | None:
    """Newest successfully finished run for ``ticker`` (backs the WP-2 verdict cache).

    Only ``status == "finished"`` runs qualify (errored runs have ``finished_at``
    set too but must never win). ``within_hours`` restricts to runs started
    inside the freshness window.
    """
    stmt = (
        select(Run)
        .where(
            Run.ticker == ticker,
            Run.status == "finished",
            Run.finished_at.is_not(None),
        )
        .order_by(Run.started_at.desc(), Run.run_id.desc())
        .limit(1)
    )
    if within_hours is not None:
        cutoff = _utcnow() - timedelta(hours=within_hours)
        stmt = stmt.where(Run.started_at >= cutoff)
    result = await session.execute(stmt)
    return result.scalars().first()


# --------------------------------------------------------------------- verdicts


async def insert_verdict(
    session: AsyncSession, ticker: str, decision: dict[str, Any], ts: datetime
) -> Verdict:
    """Persist a FinalDecision dump for ``ticker`` stamped with tz-aware ``ts``."""
    row = Verdict(ticker=ticker, ts=ts, decision=decision)
    session.add(row)
    await session.flush()
    return row


async def latest_verdict(session: AsyncSession, ticker: str) -> Verdict | None:
    """Newest verdict for ``ticker``: ORDER BY ts DESC, id DESC (deterministic
    recency — never similarity search)."""
    result = await session.execute(
        select(Verdict)
        .where(Verdict.ticker == ticker)
        .order_by(Verdict.ts.desc(), Verdict.id.desc())
        .limit(1)
    )
    return result.scalars().first()


# ------------------------------------------------------------------------ quota


async def increment_quota(session: AsyncSession, key: str, day: date) -> int:
    """Atomic upsert+increment for (key, day); returns the new count."""
    insert = _dialect_insert(session)
    stmt = (
        insert(DemoQuota)
        .values(key=key, day=day, count=1)
        .on_conflict_do_update(
            index_elements=["key", "day"], set_={"count": DemoQuota.count + 1}
        )
        .returning(DemoQuota.count)
    )
    result = await session.execute(stmt)
    return int(result.scalar_one())


async def get_quota(session: AsyncSession, key: str, day: date) -> int:
    result = await session.execute(
        select(DemoQuota.count).where(DemoQuota.key == key, DemoQuota.day == day)
    )
    count = result.scalar_one_or_none()
    return int(count) if count is not None else 0


# ------------------------------------------------------------------------- eval


async def save_eval_result(
    session: AsyncSession, label: str, summary: dict[str, Any], pairs: Any
) -> EvalResult:
    row = EvalResult(label=label, summary=summary, pairs=pairs)
    session.add(row)
    await session.flush()
    return row


async def list_eval_results(session: AsyncSession, limit: int = 20) -> list[EvalResult]:
    """Eval results newest-first."""
    result = await session.execute(
        select(EvalResult)
        .order_by(EvalResult.created_at.desc(), EvalResult.id.desc())
        .limit(limit)
    )
    return list(result.scalars().all())

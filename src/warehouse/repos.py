# src/warehouse/repos.py
"""Async repository functions for the warehouse.

Every function takes an ``AsyncSession`` as its first argument — no hidden session
creation; callers own transaction boundaries (e.g. via ``session_scope``).
Bulk upserts use the dialect-aware ``INSERT ... ON CONFLICT`` (postgresql vs
sqlite) chosen from ``session.bind.dialect.name``.
"""
from __future__ import annotations

import hashlib
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta
from typing import Any, Callable

from sqlalchemy import func, or_, select
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


async def list_watched(session: AsyncSession) -> list[Instrument]:
    result = await session.execute(
        select(Instrument).where(Instrument.watched.is_(True)).order_by(Instrument.ticker)
    )
    return list(result.scalars().all())


async def search_instruments(
    session: AsyncSession, q: str, limit: int = 20
) -> list[Instrument]:
    """Case-insensitive substring search on ticker OR name, ordered ticker asc.

    Empty ``q`` matches everything (the Market Explorer's unfiltered list)."""
    stmt = select(Instrument).order_by(Instrument.ticker.asc(), Instrument.id.asc())
    if q:
        pattern = f"%{q}%"
        stmt = stmt.where(
            or_(Instrument.ticker.ilike(pattern), Instrument.name.ilike(pattern))
        )
    result = await session.execute(stmt.limit(limit))
    return list(result.scalars().all())


async def resolve_instrument(
    session: AsyncSession, ticker: str, exchange: str | None = None
) -> Instrument | None:
    """Resolve a ticker (optionally exchange-qualified) to ONE instrument row.

    With ``exchange`` the (ticker, exchange) pair is unique. Without it, a
    ticker listed on several exchanges is disambiguated by data freshness: the
    row with the newest price bar wins (rows with no bars sort last; id asc
    tie-break keeps the result deterministic)."""
    if exchange is not None:
        result = await session.execute(
            select(Instrument).where(
                Instrument.ticker == ticker, Instrument.exchange == exchange
            )
        )
        return result.scalars().first()
    newest_bar = func.max(PriceBar.ts)
    stmt = (
        select(Instrument)
        .outerjoin(PriceBar, PriceBar.instrument_id == Instrument.id)
        .where(Instrument.ticker == ticker)
        .group_by(Instrument.id)
        .order_by(newest_bar.desc().nulls_last(), Instrument.id.asc())
        .limit(1)
    )
    result = await session.execute(stmt)
    return result.scalars().first()


# ------------------------------------------------------------------- price bars


async def bulk_upsert_price_bars(
    session: AsyncSession, instrument_id: int, bars: list[dict[str, Any]]
) -> int:
    """Idempotent bulk upsert; ON CONFLICT (instrument_id, interval, ts) DO UPDATE.

    Re-fetched bars win: OHLCV columns take the incoming (excluded) values, so a
    partial intraday bar captured mid-session is corrected by the next refresh
    instead of frozen forever. Both the sqlite and postgresql dialect inserts
    support ``on_conflict_do_update``/``excluded``.

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
    stmt = insert(PriceBar).values(rows)
    stmt = stmt.on_conflict_do_update(
        index_elements=["instrument_id", "interval", "ts"],
        set_={
            "open": stmt.excluded.open,
            "high": stmt.excluded.high,
            "low": stmt.excluded.low,
            "close": stmt.excluded.close,
            "volume": stmt.excluded.volume,
        },
    )
    await session.execute(stmt)
    return len(rows)


async def list_price_bars(
    session: AsyncSession,
    instrument_id: int,
    *,
    days: int = 365,
    interval: str = "1d",
) -> list[PriceBar]:
    """Bars for the instrument within the trailing ``days`` window, ts ASCENDING."""
    cutoff = _utcnow() - timedelta(days=days)
    result = await session.execute(
        select(PriceBar)
        .where(
            PriceBar.instrument_id == instrument_id,
            PriceBar.interval == interval,
            PriceBar.ts >= cutoff,
        )
        .order_by(PriceBar.ts.asc())
    )
    return list(result.scalars().all())


# ----------------------------------------------------------------- fundamentals


async def insert_fundamentals(
    session: AsyncSession, instrument_id: int, ts: datetime, **fields: Any
) -> FundamentalsSnapshot:
    snap = FundamentalsSnapshot(instrument_id=instrument_id, ts=ts, **fields)
    session.add(snap)
    await session.flush()
    return snap


async def latest_fundamentals(
    session: AsyncSession, instrument_id: int
) -> FundamentalsSnapshot | None:
    """Newest fundamentals snapshot (ts DESC, id DESC tie-break), or None."""
    result = await session.execute(
        select(FundamentalsSnapshot)
        .where(FundamentalsSnapshot.instrument_id == instrument_id)
        .order_by(FundamentalsSnapshot.ts.desc(), FundamentalsSnapshot.id.desc())
        .limit(1)
    )
    return result.scalars().first()


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


async def list_news_items(
    session: AsyncSession, instrument_id: int, limit: int = 20
) -> list[NewsItem]:
    """News for the instrument, newest first (ts DESC, id DESC tie-break)."""
    result = await session.execute(
        select(NewsItem)
        .where(NewsItem.instrument_id == instrument_id)
        .order_by(NewsItem.ts.desc(), NewsItem.id.desc())
        .limit(limit)
    )
    return list(result.scalars().all())


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
    embedding: list[float] | None = None,
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
    if embedding is not None:
        # WP-9: summary vector for /api/search (computed by the caller OUTSIDE
        # any DB session — model inference must not hold a transaction open).
        run.embedding = embedding
    await session.flush()
    return run


async def bulk_append_run_events(
    session: AsyncSession, run_id: str, rows: list[dict[str, Any]]
) -> int:
    """Idempotent bulk append; ON CONFLICT (run_id, seq) DO NOTHING.

    Each row is ``{"seq": int, "event": dict}`` — the caller owns seq assignment
    (see ``ingest.record_run_events``). First write wins: replaying rows with
    already-stored seqs inserts nothing, mirroring ``upsert_news`` semantics.

    Returns the attempted (input) count, not the inserted count.
    """
    # asyncpg's ~32k bind-param ceiling bounds one bulk call; chunk upstream.
    if not rows:
        return 0
    values = [
        {"run_id": run_id, "seq": row["seq"], "event": row["event"]} for row in rows
    ]
    insert = _dialect_insert(session)
    stmt = (
        insert(RunEvent)
        .values(values)
        .on_conflict_do_nothing(index_elements=["run_id", "seq"])
    )
    await session.execute(stmt)
    return len(values)


async def get_run(session: AsyncSession, run_id: str) -> Run | None:
    return await session.get(Run, run_id)


async def get_run_events(session: AsyncSession, run_id: str) -> list[RunEvent]:
    result = await session.execute(
        select(RunEvent).where(RunEvent.run_id == run_id).order_by(RunEvent.seq)
    )
    return list(result.scalars().all())


async def list_runs(
    session: AsyncSession,
    *,
    ticker: str | None = None,
    status: str | None = None,
    limit: int = 50,
    offset: int = 0,
) -> list[Run]:
    """Runs newest-first (by started_at), optionally filtered by ticker/status."""
    stmt = select(Run).order_by(Run.started_at.desc(), Run.run_id.desc())
    if ticker is not None:
        stmt = stmt.where(Run.ticker == ticker)
    if status is not None:
        stmt = stmt.where(Run.status == status)
    result = await session.execute(stmt.limit(limit).offset(offset))
    return list(result.scalars().all())


async def count_runs(
    session: AsyncSession, *, ticker: str | None = None, status: str | None = None
) -> int:
    """Total runs matching the same filters as ``list_runs`` (the library's total)."""
    stmt = select(func.count()).select_from(Run)
    if ticker is not None:
        stmt = stmt.where(Run.ticker == ticker)
    if status is not None:
        stmt = stmt.where(Run.status == status)
    return int((await session.execute(stmt)).scalar_one())


# ----------------------------------------------------------------- search (WP-9)


class UnsupportedDialectError(RuntimeError):
    """``semantic_search`` requires PostgreSQL + pgvector; raised on any other
    dialect so the caller can fall back to ``keyword_search``."""


@dataclass(frozen=True)
class SearchHit:
    """One /api/search result row, shared by the semantic and keyword paths."""

    kind: str  # "news" | "run"
    ref: str  # news url | run_id
    ticker: str
    title: str
    snippet: str | None
    score: float | None  # cosine distance (semantic; lower = closer) | None (keyword)
    ts: datetime


_RUN_SNIPPET_CHARS = 200


def _news_hit(item: NewsItem, ticker: str, score: float | None) -> SearchHit:
    return SearchHit(
        kind="news", ref=item.url, ticker=ticker, title=item.title,
        snippet=item.snippet, score=score, ts=item.ts,
    )


def _run_hit(run: Run, score: float | None) -> SearchHit:
    decision = run.final_decision if isinstance(run.final_decision, dict) else {}
    action = decision.get("action")
    title = f"{run.ticker} run — {action}" if action else f"{run.ticker} run"
    snippet = (run.report or "")[:_RUN_SNIPPET_CHARS] or None
    return SearchHit(
        kind="run", ref=run.run_id, ticker=run.ticker, title=title,
        snippet=snippet, score=score, ts=run.started_at,
    )


async def semantic_search(
    session: AsyncSession, query_vec: list[float], *, limit: int = 20
) -> list[SearchHit]:
    """Nearest news + runs by cosine distance to ``query_vec`` (PostgreSQL only).

    UNION-style: two per-table queries (each ``ORDER BY embedding <=> :q LIMIT
    n``, so both can use their HNSW cosine index; rows with NULL embeddings are
    skipped), merged nearest-first in Python and capped at ``limit``. On any
    non-PostgreSQL dialect raises ``UnsupportedDialectError`` — callers fall
    back to ``keyword_search``.
    """
    bind = getattr(session, "bind", None)
    if bind is None or bind.dialect.name != "postgresql":
        raise UnsupportedDialectError(
            "semantic_search requires PostgreSQL + pgvector; use keyword_search"
        )
    news_dist = NewsItem.embedding.cosine_distance(query_vec).label("distance")
    news_stmt = (
        select(NewsItem, Instrument.ticker, news_dist)
        .join(Instrument, Instrument.id == NewsItem.instrument_id)
        .where(NewsItem.embedding.is_not(None))
        .order_by(news_dist)
        .limit(limit)
    )
    run_dist = Run.embedding.cosine_distance(query_vec).label("distance")
    run_stmt = (
        select(Run, run_dist)
        .where(Run.embedding.is_not(None))
        .order_by(run_dist)
        .limit(limit)
    )
    # Both queries SELECT the distance and skip NULL embeddings, so every hit
    # here carries a float score (SearchHit.score is Optional only for the
    # keyword path) — sort (distance, hit) pairs, nearest first.
    scored = [
        (float(distance), _news_hit(item, ticker, float(distance)))
        for item, ticker, distance in (await session.execute(news_stmt)).all()
    ]
    scored += [
        (float(distance), _run_hit(run, float(distance)))
        for run, distance in (await session.execute(run_stmt)).all()
    ]
    scored.sort(key=lambda pair: pair[0])
    return [hit for _, hit in scored[:limit]]


async def keyword_search(
    session: AsyncSession, q: str, *, limit: int = 20
) -> list[SearchHit]:
    """Dialect-agnostic ILIKE fallback: news title/snippet + run ticker/report.

    Newest-first (news ts / run started_at) across both kinds, capped at
    ``limit``. Hits carry ``score=None`` — there is no distance to report.
    """
    pattern = f"%{q}%"
    news_stmt = (
        select(NewsItem, Instrument.ticker)
        .join(Instrument, Instrument.id == NewsItem.instrument_id)
        .where(or_(NewsItem.title.ilike(pattern), NewsItem.snippet.ilike(pattern)))
        .order_by(NewsItem.ts.desc(), NewsItem.id.desc())
        .limit(limit)
    )
    run_stmt = (
        select(Run)
        .where(or_(Run.ticker.ilike(pattern), Run.report.ilike(pattern)))
        .order_by(Run.started_at.desc(), Run.run_id.desc())
        .limit(limit)
    )
    hits = [
        _news_hit(item, ticker, None)
        for item, ticker in (await session.execute(news_stmt)).all()
    ]
    hits += [
        _run_hit(run, None) for run in (await session.execute(run_stmt)).scalars()
    ]
    hits.sort(key=lambda h: h.ts, reverse=True)
    return hits[:limit]


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

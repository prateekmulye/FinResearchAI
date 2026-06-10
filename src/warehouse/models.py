# src/warehouse/models.py
"""Warehouse ORM models (SQLAlchemy 2 declarative, Mapped/mapped_column style).

Design notes:
- All datetime columns use ``UTCDateTime``: naive binds raise ``ValueError``,
  aware binds are normalized to UTC, and SQLite result rows (stored without an
  offset) come back with ``tzinfo=UTC`` reattached — so SQLite and Postgres
  bind/compare/return datetimes identically.
- JSON columns use ``sqlalchemy.JSON`` which works on both dialects (plain JSON on
  PG — no JSONB-only APIs). In-place mutation of a loaded JSON value is NOT
  change-tracked; always reassign the whole value (``row.payload = {**row.payload,
  "k": v}``), never mutate it.
- ``EmbeddingVector(EMBEDDING_DIM)`` is pgvector on PG, JSON-in-TEXT on SQLite.
"""
from __future__ import annotations

from datetime import UTC, date, datetime
from typing import Any

from sqlalchemy import (
    JSON,
    BigInteger,
    Date,
    ForeignKey,
    Index,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

from src.warehouse.types import EmbeddingVector, UTCDateTime

EMBEDDING_DIM = 384  # BAAI/bge-small-en-v1.5 output dimension (matches src/memory)


def _utcnow() -> datetime:
    return datetime.now(UTC)


class Base(DeclarativeBase):
    type_annotation_map = {
        datetime: UTCDateTime(),
        # NOTE: plain JSON columns don't track in-place mutation — reassign whole
        # values (see module docstring).
        dict[str, Any]: JSON,
    }


class Instrument(Base):
    __tablename__ = "instruments"
    __table_args__ = (
        UniqueConstraint("ticker", "exchange", name="uq_instruments_ticker_exchange"),
    )

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    ticker: Mapped[str] = mapped_column(String)
    exchange: Mapped[str] = mapped_column(String)
    screener: Mapped[str] = mapped_column(String)
    name: Mapped[str | None] = mapped_column(String)
    country: Mapped[str | None] = mapped_column(String)
    currency: Mapped[str | None] = mapped_column(String)
    sector: Mapped[str | None] = mapped_column(String)
    watched: Mapped[bool] = mapped_column(default=False)
    created_at: Mapped[datetime] = mapped_column(default=_utcnow)
    updated_at: Mapped[datetime] = mapped_column(default=_utcnow, onupdate=_utcnow)


class PriceBar(Base):
    __tablename__ = "price_bars"
    __table_args__ = (
        UniqueConstraint(
            "instrument_id", "interval", "ts", name="uq_price_bars_instrument_interval_ts"
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    instrument_id: Mapped[int] = mapped_column(
        ForeignKey("instruments.id", ondelete="CASCADE")
    )
    ts: Mapped[datetime]
    interval: Mapped[str] = mapped_column(String, default="1d")
    open: Mapped[float]
    high: Mapped[float]
    low: Mapped[float]
    close: Mapped[float]
    volume: Mapped[int | None] = mapped_column(BigInteger)


class FundamentalsSnapshot(Base):
    __tablename__ = "fundamentals_snapshots"
    __table_args__ = (
        Index("ix_fundamentals_snapshots_instrument_id_ts", "instrument_id", "ts"),
    )

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    instrument_id: Mapped[int] = mapped_column(
        ForeignKey("instruments.id", ondelete="CASCADE")
    )
    ts: Mapped[datetime]
    market_cap: Mapped[float | None]
    pe_ratio: Mapped[float | None]
    eps: Mapped[float | None]
    revenue_growth: Mapped[float | None]
    profit_margin: Mapped[float | None]
    # JSON columns (here and below): in-place mutation isn't tracked — always
    # reassign whole values.
    payload: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)


class NewsItem(Base):
    __tablename__ = "news_items"
    __table_args__ = (Index("ix_news_items_instrument_id_ts", "instrument_id", "ts"),)

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    instrument_id: Mapped[int] = mapped_column(
        ForeignKey("instruments.id", ondelete="CASCADE")
    )
    ts: Mapped[datetime]
    title: Mapped[str] = mapped_column(String)
    url: Mapped[str] = mapped_column(String)
    source: Mapped[str | None] = mapped_column(String)
    snippet: Mapped[str | None] = mapped_column(Text)
    url_hash: Mapped[str] = mapped_column(String(64), unique=True)
    embedding: Mapped[list[float] | None] = mapped_column(
        EmbeddingVector(EMBEDDING_DIM), nullable=True
    )


class Run(Base):
    __tablename__ = "runs"
    __table_args__ = (Index("ix_runs_ticker_started_at", "ticker", "started_at"),)

    run_id: Mapped[str] = mapped_column(String, primary_key=True)
    ticker: Mapped[str] = mapped_column(String)
    debate_mode: Mapped[str] = mapped_column(String)
    status: Mapped[str] = mapped_column(String, default="running")
    started_at: Mapped[datetime] = mapped_column(default=_utcnow)
    finished_at: Mapped[datetime | None]
    final_decision: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    report: Mapped[str | None] = mapped_column(Text)
    metrics: Mapped[Any | None] = mapped_column(JSON, nullable=True)
    embedding: Mapped[list[float] | None] = mapped_column(
        EmbeddingVector(EMBEDDING_DIM), nullable=True
    )


class RunEvent(Base):
    __tablename__ = "run_events"
    __table_args__ = (UniqueConstraint("run_id", "seq", name="uq_run_events_run_id_seq"),)

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    run_id: Mapped[str] = mapped_column(ForeignKey("runs.run_id", ondelete="CASCADE"))
    seq: Mapped[int]
    event: Mapped[dict[str, Any]] = mapped_column(JSON)


class EvalResult(Base):
    __tablename__ = "eval_results"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    label: Mapped[str] = mapped_column(String)
    created_at: Mapped[datetime] = mapped_column(default=_utcnow)
    summary: Mapped[dict[str, Any]] = mapped_column(JSON)
    pairs: Mapped[Any] = mapped_column(JSON)


class Verdict(Base):
    """Cross-run verdict cache row (WP-2): the FinalDecision dump for a ticker.

    Recency is deterministic — ORDER BY ts DESC (id DESC tie-break) — never
    similarity search.
    """

    __tablename__ = "verdicts"
    __table_args__ = (Index("ix_verdicts_ticker_ts", "ticker", "ts"),)

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    ticker: Mapped[str] = mapped_column(String)
    ts: Mapped[datetime]
    decision: Mapped[dict[str, Any]] = mapped_column(JSON)


class DemoQuota(Base):
    __tablename__ = "demo_quota"
    __table_args__ = (UniqueConstraint("key", "day", name="uq_demo_quota_key_day"),)

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    key: Mapped[str] = mapped_column(String)
    day: Mapped[date] = mapped_column(Date)
    count: Mapped[int] = mapped_column(default=0)

"""warehouse initial schema

Creates the pgvector extension (PostgreSQL only), every warehouse table, and the
HNSW cosine indexes on news_items.embedding + runs.embedding (PostgreSQL only).
In practice this migration only runs on PostgreSQL — SQLite tests build the
schema via src.warehouse.bootstrap.create_all — but every PG-ism is guarded so
the migration stays loadable on any dialect.

Revision ID: 0001
Revises:
Create Date: 2026-06-10
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision = "0001"
down_revision = None
branch_labels = None
depends_on = None

EMBEDDING_DIM = 384


def _is_postgresql() -> bool:
    return op.get_bind().dialect.name == "postgresql"


def _embedding_type() -> sa.types.TypeEngine:
    if _is_postgresql():
        from pgvector.sqlalchemy import Vector

        return Vector(EMBEDDING_DIM)
    return sa.Text()


def upgrade() -> None:
    if _is_postgresql():
        op.execute("CREATE EXTENSION IF NOT EXISTS vector")

    op.create_table(
        "instruments",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("ticker", sa.String(), nullable=False),
        sa.Column("exchange", sa.String(), nullable=False),
        sa.Column("screener", sa.String(), nullable=False),
        sa.Column("name", sa.String(), nullable=True),
        sa.Column("country", sa.String(), nullable=True),
        sa.Column("currency", sa.String(), nullable=True),
        sa.Column("sector", sa.String(), nullable=True),
        sa.Column("watched", sa.Boolean(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("ticker", "exchange", name="uq_instruments_ticker_exchange"),
    )

    op.create_table(
        "price_bars",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column(
            "instrument_id",
            sa.Integer(),
            sa.ForeignKey("instruments.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("ts", sa.DateTime(timezone=True), nullable=False),
        sa.Column("interval", sa.String(), nullable=False),
        sa.Column("open", sa.Float(), nullable=False),
        sa.Column("high", sa.Float(), nullable=False),
        sa.Column("low", sa.Float(), nullable=False),
        sa.Column("close", sa.Float(), nullable=False),
        sa.Column("volume", sa.BigInteger(), nullable=True),
        sa.UniqueConstraint(
            "instrument_id", "interval", "ts", name="uq_price_bars_instrument_interval_ts"
        ),
    )

    op.create_table(
        "fundamentals_snapshots",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column(
            "instrument_id",
            sa.Integer(),
            sa.ForeignKey("instruments.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("ts", sa.DateTime(timezone=True), nullable=False),
        sa.Column("market_cap", sa.Float(), nullable=True),
        sa.Column("pe_ratio", sa.Float(), nullable=True),
        sa.Column("eps", sa.Float(), nullable=True),
        sa.Column("revenue_growth", sa.Float(), nullable=True),
        sa.Column("profit_margin", sa.Float(), nullable=True),
        sa.Column("payload", sa.JSON(), nullable=False),
    )
    op.create_index(
        "ix_fundamentals_snapshots_instrument_id_ts",
        "fundamentals_snapshots",
        ["instrument_id", "ts"],
    )

    op.create_table(
        "news_items",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column(
            "instrument_id",
            sa.Integer(),
            sa.ForeignKey("instruments.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("ts", sa.DateTime(timezone=True), nullable=False),
        sa.Column("title", sa.String(), nullable=False),
        sa.Column("url", sa.String(), nullable=False),
        sa.Column("source", sa.String(), nullable=True),
        sa.Column("snippet", sa.Text(), nullable=True),
        sa.Column("url_hash", sa.String(64), nullable=False, unique=True),
        sa.Column("embedding", _embedding_type(), nullable=True),
    )

    op.create_table(
        "runs",
        sa.Column("run_id", sa.String(), primary_key=True),
        sa.Column("ticker", sa.String(), nullable=False),
        sa.Column("debate_mode", sa.String(), nullable=False),
        sa.Column("status", sa.String(), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("final_decision", sa.JSON(), nullable=True),
        sa.Column("report", sa.Text(), nullable=True),
        sa.Column("metrics", sa.JSON(), nullable=True),
        sa.Column("embedding", _embedding_type(), nullable=True),
    )
    op.create_index("ix_runs_ticker_started_at", "runs", ["ticker", "started_at"])

    op.create_table(
        "run_events",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column(
            "run_id",
            sa.String(),
            sa.ForeignKey("runs.run_id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("seq", sa.Integer(), nullable=False),
        sa.Column("event", sa.JSON(), nullable=False),
        sa.UniqueConstraint("run_id", "seq", name="uq_run_events_run_id_seq"),
    )

    op.create_table(
        "eval_results",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("label", sa.String(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("summary", sa.JSON(), nullable=False),
        sa.Column("pairs", sa.JSON(), nullable=False),
    )

    op.create_table(
        "demo_quota",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("key", sa.String(), nullable=False),
        sa.Column("day", sa.Date(), nullable=False),
        sa.Column("count", sa.Integer(), nullable=False),
        sa.UniqueConstraint("key", "day", name="uq_demo_quota_key_day"),
    )

    if _is_postgresql():
        op.execute(
            "CREATE INDEX ix_news_items_embedding_hnsw ON news_items "
            "USING hnsw (embedding vector_cosine_ops)"
        )
        op.execute(
            "CREATE INDEX ix_runs_embedding_hnsw ON runs "
            "USING hnsw (embedding vector_cosine_ops)"
        )


def downgrade() -> None:
    # HNSW indexes drop with their tables; the vector extension is left installed.
    op.drop_table("demo_quota")
    op.drop_table("eval_results")
    op.drop_table("run_events")
    op.drop_index("ix_runs_ticker_started_at", table_name="runs")
    op.drop_table("runs")
    op.drop_table("news_items")
    op.drop_index(
        "ix_fundamentals_snapshots_instrument_id_ts", table_name="fundamentals_snapshots"
    )
    op.drop_table("fundamentals_snapshots")
    op.drop_table("price_bars")
    op.drop_table("instruments")

"""verdicts table — warehouse-backed cross-run verdict cache (WP-2)

Replaces the embedded-Chroma verdict cache: the FinalDecision dump is stored as
JSON keyed by ticker, and recency is a deterministic ORDER BY ts DESC query
(id DESC tie-break) — never similarity search.

Revision ID: 0002
Revises: 0001
Create Date: 2026-06-10
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision = "0002"
down_revision = "0001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "verdicts",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("ticker", sa.String(), nullable=False),
        sa.Column("ts", sa.DateTime(timezone=True), nullable=False),
        sa.Column("decision", sa.JSON(), nullable=False),
    )
    op.create_index("ix_verdicts_ticker_ts", "verdicts", ["ticker", "ts"])


def downgrade() -> None:
    op.drop_index("ix_verdicts_ticker_ts", table_name="verdicts")
    op.drop_table("verdicts")

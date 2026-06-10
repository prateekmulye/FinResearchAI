# src/warehouse/types.py
"""Dialect-aware column types for the warehouse.

``EmbeddingVector(dim)`` stores a fixed-dimension embedding:
- on PostgreSQL it compiles to ``pgvector.sqlalchemy.Vector(dim)`` (real ANN-capable
  vector column);
- on every other dialect (SQLite in tests) it stores a JSON-serialized list in TEXT
  and returns ``list[float]`` on load, so the offline suite exercises the same model
  code without Postgres.
- binds are dimension-checked on every dialect: a vector whose length differs from
  ``dim`` raises ``ValueError``.

``UTCDateTime`` keeps datetimes tz-aware UTC on both dialects:
- naive datetimes are rejected on bind (``ValueError``);
- aware datetimes are normalized to UTC on bind;
- result rows that come back naive (SQLite stores no offset) get ``tzinfo=UTC``
  reattached, so ORM attributes are aware UTC everywhere.
"""
from __future__ import annotations

import json
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import DateTime, Float, Text
from sqlalchemy.engine import Dialect
from sqlalchemy.types import TypeDecorator


class EmbeddingVector(TypeDecorator):
    """Fixed-dimension float vector: pgvector on PostgreSQL, JSON-in-TEXT elsewhere."""

    impl = Text
    cache_ok = True

    class Comparator(TypeDecorator.Comparator):
        """pgvector-style distance comparator (WP-9 semantic search).

        ``cosine_distance`` emits the pgvector ``<=>`` operator — the same SQL
        pgvector.sqlalchemy's own comparator produces — so ``ORDER BY embedding
        <=> :q`` can use the HNSW cosine indexes. Only meaningful on PostgreSQL;
        non-PG callers must go through ``repos.semantic_search``'s dialect guard.
        """

        def cosine_distance(self, other: Any) -> Any:
            return self.op("<=>", return_type=Float)(other)

    comparator_factory = Comparator

    def coerce_compared_value(self, op: Any, value: Any) -> Any:
        # Keep THIS type for comparison operands. The TypeDecorator default
        # delegates to the impl (Text), which would bind a query vector as a
        # string; returning self keeps the dim check + pgvector bind processing.
        return self

    def __init__(self, dim: int) -> None:
        super().__init__()
        self.dim = dim

    def load_dialect_impl(self, dialect: Dialect) -> Any:
        if dialect.name == "postgresql":
            from pgvector.sqlalchemy import Vector

            return dialect.type_descriptor(Vector(self.dim))
        return dialect.type_descriptor(Text())

    def process_bind_param(self, value: Any, dialect: Dialect) -> Any:
        if value is None:
            return None
        if len(value) != self.dim:
            raise ValueError(
                f"EmbeddingVector expects {self.dim} dimensions, got {len(value)}"
            )
        if dialect.name == "postgresql":
            return value  # pgvector's own bind processing handles list/ndarray
        return json.dumps([float(x) for x in value])

    def process_result_value(self, value: Any, dialect: Dialect) -> list[float] | None:
        if value is None:
            return None
        if dialect.name == "postgresql":
            return [float(x) for x in value]  # pgvector returns an ndarray
        return [float(x) for x in json.loads(value)]


class UTCDateTime(TypeDecorator):
    """Tz-aware UTC datetime that behaves identically on PostgreSQL and SQLite.

    Bind: rejects naive datetimes (``ValueError``) and converts aware values to
    UTC. Result: reattaches ``tzinfo=UTC`` when the dialect returns naive rows
    (SQLite stores ISO strings without an offset); already-aware rows (PG
    ``timestamptz``) are normalized to UTC.
    """

    impl = DateTime(timezone=True)
    cache_ok = True

    def process_bind_param(self, value: Any, dialect: Dialect) -> datetime | None:
        if value is None:
            return None
        if value.tzinfo is None:
            raise ValueError(
                "naive datetime not allowed; bind tz-aware values (e.g. datetime.now(UTC))"
            )
        return value.astimezone(UTC)

    def process_result_value(self, value: Any, dialect: Dialect) -> datetime | None:
        if value is None:
            return None
        if value.tzinfo is None:
            return value.replace(tzinfo=UTC)
        return value.astimezone(UTC)

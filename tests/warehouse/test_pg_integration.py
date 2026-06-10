# tests/warehouse/test_pg_integration.py
"""Live Postgres 16 + pgvector integration (marker: db; deselected by default).

Run with the dev compose database::

    docker compose up -d db
    DATABASE_URL=postgresql+asyncpg://finresearch:finresearch@localhost:5433/finresearch \
        python -m pytest -m db tests/warehouse/test_pg_integration.py

Applies ``alembic upgrade head`` programmatically, then verifies the pgvector
extension and a vector insert + cosine-distance query roundtrip. Nothing is
downgraded afterwards (the dev DB keeps its schema).
"""
from __future__ import annotations

import os
import uuid
from datetime import UTC, datetime

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from src.warehouse.models import EMBEDDING_DIM
from src.warehouse.repos import upsert_instrument, upsert_news

pytestmark = pytest.mark.db


@pytest.fixture(scope="module")
def database_url() -> str:
    url = os.environ.get("DATABASE_URL", "")
    if not url:
        pytest.skip("DATABASE_URL not set; start the docker-compose db and export it")
    return url


@pytest.fixture(scope="module")
def migrated(database_url: str) -> str:
    """alembic upgrade head against DATABASE_URL (env.py prefers the env var)."""
    from alembic import command
    from alembic.config import Config

    command.upgrade(Config("alembic.ini"), "head")
    return database_url


async def test_pgvector_extension_installed(migrated: str):
    engine = create_async_engine(migrated)
    try:
        async with engine.connect() as conn:
            ext = (
                await conn.execute(
                    text("SELECT extname FROM pg_extension WHERE extname = 'vector'")
                )
            ).scalar_one_or_none()
        assert ext == "vector"
    finally:
        await engine.dispose()


async def test_hnsw_indexes_exist(migrated: str):
    engine = create_async_engine(migrated)
    try:
        async with engine.connect() as conn:
            names = (
                await conn.execute(
                    text("SELECT indexname FROM pg_indexes WHERE indexname LIKE '%hnsw%'")
                )
            ).scalars().all()
        assert "ix_news_items_embedding_hnsw" in names
        assert "ix_runs_embedding_hnsw" in names
    finally:
        await engine.dispose()


async def test_vector_insert_and_cosine_query_roundtrip(migrated: str):
    engine = create_async_engine(migrated)
    maker = async_sessionmaker(engine, expire_on_commit=False)
    probe = [0.0] * (EMBEDDING_DIM - 1) + [1.0]
    url = f"https://pg-integration.example/{uuid.uuid4()}"
    try:
        async with maker() as session:
            inst = await upsert_instrument(
                session, ticker="PGTEST", exchange="PGTEST", screener="america"
            )
            await upsert_news(
                session,
                inst.id,
                [{"ts": datetime.now(UTC), "title": "pg roundtrip", "url": url,
                  "embedding": probe}],
            )
            await session.commit()

        vector_literal = "[" + ",".join(str(x) for x in probe) + "]"
        async with engine.connect() as conn:
            row = (
                await conn.execute(
                    text(
                        "SELECT url, embedding <=> CAST(:q AS vector) AS dist "
                        "FROM news_items WHERE url = :url "
                        "ORDER BY embedding <=> CAST(:q AS vector) LIMIT 1"
                    ),
                    {"q": vector_literal, "url": url},
                )
            ).one()
        assert row.url == url
        assert row.dist == pytest.approx(0.0, abs=1e-6)  # cosine distance to itself
    finally:
        await engine.dispose()

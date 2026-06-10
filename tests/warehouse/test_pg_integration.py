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
from sqlalchemy import delete, select, text
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from src.warehouse.models import EMBEDDING_DIM, Instrument, NewsItem, Run
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


# ----------------------------------------------------- WP-9: write path + search
#
# Drives the REAL ingest functions (record_news / record_run_start / _finish)
# against live Postgres with a scripted embedder, then verifies the pgvector
# cosine path end to end: embeddings persisted on both tables, semantic_search
# nearest-first, HNSW-ordered <=> distances exposed as SearchHit.score.


class _ScriptedEmbedder:
    """text -> fixed vector; unknown text raises loudly (mapping must be exact)."""

    def __init__(self, mapping: dict[str, list[float]]) -> None:
        self.mapping = mapping

    def embed(self, texts: list[str]) -> list[list[float]]:
        return [self.mapping[t] for t in texts]

    def embed_one(self, text: str) -> list[float]:
        return self.mapping[text]


def _basis(i: int) -> list[float]:
    v = [0.0] * EMBEDDING_DIM
    v[i] = 1.0
    return v


@pytest.fixture
async def pg_warehouse(migrated: str, monkeypatch):
    """Point the app warehouse at the live PG DB (env_isolation scrubbed the env)."""
    from src.config import settings as settings_mod
    from src.warehouse.db import reset_engine

    monkeypatch.setenv("DATABASE_URL", migrated)
    settings_mod.get_settings.cache_clear()
    await reset_engine()
    yield migrated
    await reset_engine()
    settings_mod.get_settings.cache_clear()


async def test_record_news_and_run_embed_then_cosine_search_nearest_first(pg_warehouse):
    from src.warehouse.db import session_scope
    from src.warehouse.embeddings import set_embedder_for_testing
    from src.warehouse.ingest import (
        _run_summary_text,
        record_news,
        record_run_finish,
        record_run_start,
    )
    from src.warehouse.repos import semantic_search

    uid = uuid.uuid4().hex[:8]
    url_a = f"https://pg-sem.example/{uid}/a"
    url_b = f"https://pg-sem.example/{uid}/b"
    run_id = f"run-pgsem-{uid}"
    title_a = f"alpha headline {uid}"
    title_b = f"beta headline {uid}"
    snippet_b = "beta snippet"
    report = f"semantic run report {uid}"
    decision = {"action": "BUY", "rationale": "pg semantic"}

    # Keep the dev DB bounded + this test re-runnable: drop earlier WP-9 rows
    # (cascades news via the PGSEM instrument) before writing fresh ones.
    async with session_scope() as session:
        await session.execute(delete(Run).where(Run.run_id.like("run-pgsem-%")))
        await session.execute(
            delete(Instrument).where(Instrument.ticker == "PGSEM")
        )

    set_embedder_for_testing(
        _ScriptedEmbedder(
            {
                title_a: _basis(0),  # record_news embeds title (+ snippet joined)
                f"{title_b}\n{snippet_b}": _basis(1),
                _run_summary_text(report, decision): _basis(2),
            }
        )
    )
    assert await record_news(
        "PGSEM", "PGTEST", "america",
        [
            {"title": title_a, "url": url_a},
            {"title": title_b, "url": url_b, "snippet": snippet_b},
        ],
    ) == 2
    assert await record_run_start(run_id, "PGSEM", "on") is True
    assert await record_run_finish(
        run_id, status="finished", final_decision=decision, report=report
    ) is True

    # Embeddings persisted (pgvector -> list[float] roundtrip on both tables).
    async with session_scope() as session:
        news = {
            r.url: r
            for r in (
                await session.execute(
                    select(NewsItem).where(NewsItem.url.in_([url_a, url_b]))
                )
            ).scalars()
        }
        assert news[url_a].embedding == _basis(0)
        assert news[url_b].embedding == _basis(1)
        run = (
            await session.execute(select(Run).where(Run.run_id == run_id))
        ).scalar_one()
        assert run.embedding == _basis(2)

    # Query nearest axis 0: expect news A < news B < run, distances ascending.
    query = [0.0] * EMBEDDING_DIM
    query[0], query[1], query[2] = 1.0, 0.2, 0.1
    async with session_scope() as session:
        hits = await semantic_search(session, query, limit=500)
    ours = [h for h in hits if h.ref in (url_a, url_b, run_id)]
    assert [h.ref for h in ours] == [url_a, url_b, run_id]
    assert ours[0].score < ours[1].score < ours[2].score  # cosine: lower = closer
    assert ours[0].kind == "news"
    assert ours[0].ticker == "PGSEM"
    assert ours[2].kind == "run"
    assert ours[2].title == "PGSEM run — BUY"

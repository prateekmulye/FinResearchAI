# tests/warehouse/test_search_repos.py
"""WP-9 search repos: keyword_search (dialect-agnostic ILIKE fallback) against
SQLite, the UnsupportedDialectError sentinel for semantic_search on non-PG, and
the EmbeddingVector cosine comparator's PG SQL shape (compile-only — the live
cosine path runs in tests/warehouse/test_pg_integration.py, marker: db).
"""
from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy.dialects import postgresql
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from src.warehouse.bootstrap import create_all
from src.warehouse.db import enable_sqlite_fks
from src.warehouse.models import EMBEDDING_DIM, NewsItem, Run
from src.warehouse.repos import (
    SearchHit,
    UnsupportedDialectError,
    create_run,
    finish_run,
    keyword_search,
    semantic_search,
    upsert_instrument,
    upsert_news,
)
from src.warehouse.types import EmbeddingVector

TS = datetime(2026, 6, 10, 12, 0, 0, tzinfo=UTC)


@pytest.fixture
async def engine():
    eng = create_async_engine("sqlite+aiosqlite:///:memory:")
    enable_sqlite_fks(eng)
    await create_all(eng)
    yield eng
    await eng.dispose()


@pytest.fixture
async def session(engine):
    maker = async_sessionmaker(engine, expire_on_commit=False)
    async with maker() as s:
        yield s


async def _seed(session) -> None:
    aapl = await upsert_instrument(
        session, ticker="AAPL", exchange="NASDAQ", screener="america"
    )
    tsla = await upsert_instrument(
        session, ticker="TSLA", exchange="NASDAQ", screener="america"
    )
    await upsert_news(
        session, aapl.id,
        [
            {"ts": TS - timedelta(hours=3), "title": "Apple margin expansion",
             "url": "https://n.example/a1", "snippet": "services growth"},
            {"ts": TS - timedelta(hours=1), "title": "iPhone demand steady",
             "url": "https://n.example/a2", "snippet": "margin pressure easing"},
        ],
    )
    await upsert_news(
        session, tsla.id,
        [{"ts": TS - timedelta(hours=2), "title": "Tesla deliveries beat",
          "url": "https://n.example/t1", "snippet": None}],
    )
    await create_run(session, "run-aapl", "AAPL", "on")
    await finish_run(
        session, "run-aapl", status="finished",
        final_decision={"action": "BUY", "rationale": "margin upside"},
        report="Deep dive on AAPL margin drivers and services mix.",
    )
    await create_run(session, "run-msft", "MSFT", "off")


# -------------------------------------------------------------- keyword_search


async def test_keyword_search_matches_title_and_snippet(session):
    await _seed(session)
    hits = await keyword_search(session, "margin")
    assert all(isinstance(h, SearchHit) for h in hits)
    refs = [h.ref for h in hits]
    # Two news titles/snippets + the AAPL run report all contain "margin".
    assert "https://n.example/a1" in refs
    assert "https://n.example/a2" in refs
    assert "run-aapl" in refs
    assert all(h.score is None for h in hits)  # keyword hits carry no distance


async def test_keyword_search_news_hit_shape(session):
    await _seed(session)
    (hit,) = await keyword_search(session, "deliveries")
    assert hit.kind == "news"
    assert hit.ref == "https://n.example/t1"
    assert hit.ticker == "TSLA"
    assert hit.title == "Tesla deliveries beat"
    assert hit.snippet is None
    assert hit.ts == TS - timedelta(hours=2)


async def test_keyword_search_matches_run_ticker_and_report(session):
    await _seed(session)
    by_ticker = await keyword_search(session, "msft")  # case-insensitive
    assert [h.ref for h in by_ticker] == ["run-msft"]
    assert by_ticker[0].kind == "run"
    assert by_ticker[0].ticker == "MSFT"

    by_report = await keyword_search(session, "services mix")
    assert "run-aapl" in [h.ref for h in by_report]
    run_hit = next(h for h in by_report if h.ref == "run-aapl")
    assert run_hit.title == "AAPL run — BUY"  # decision action folded into the label
    assert "Deep dive" in (run_hit.snippet or "")


async def test_keyword_search_newest_first_and_limit(session):
    await _seed(session)
    hits = await keyword_search(session, "margin")
    assert [h.ts for h in hits] == sorted((h.ts for h in hits), reverse=True)
    limited = await keyword_search(session, "margin", limit=2)
    assert len(limited) == 2
    assert limited == hits[:2]


async def test_keyword_search_no_match_is_empty(session):
    await _seed(session)
    assert await keyword_search(session, "zzz-no-such-term") == []


# -------------------------------------------------------------- semantic_search


async def test_semantic_search_raises_sentinel_on_sqlite(session):
    await _seed(session)
    with pytest.raises(UnsupportedDialectError):
        await semantic_search(session, [0.1] * EMBEDDING_DIM)


def test_cosine_distance_comparator_compiles_to_pg_operator():
    """EmbeddingVector's comparator must emit the pgvector ``<=>`` operator and
    bind the query vector with the column's own type (not the Text impl)."""
    expr = NewsItem.embedding.cosine_distance([0.0] * EMBEDDING_DIM)
    compiled = expr.compile(dialect=postgresql.dialect())
    assert "<=>" in str(compiled)
    assert "news_items.embedding" in str(compiled)
    # The query-vector bind must carry EmbeddingVector (-> pgvector Vector on
    # PG), not the Text impl — coerce_compared_value keeps the column's type.
    assert compiled.binds
    assert all(isinstance(b.type, EmbeddingVector) for b in compiled.binds.values())
    # literal_binds renders the bind THROUGH that type's literal processor:
    # pgvector serializes '[0.0,0.0,...]' (comma-joined, no spaces). A Text bind
    # would refuse to render a list (or json.dumps it with ', ' separators).
    literal_sql = str(
        expr.compile(
            dialect=postgresql.dialect(), compile_kwargs={"literal_binds": True}
        )
    )
    assert "news_items.embedding <=> '[0.0,0.0" in literal_sql
    run_sql = str(
        Run.embedding.cosine_distance([0.0] * EMBEDDING_DIM).compile(
            dialect=postgresql.dialect()
        )
    )
    assert "<=>" in run_sql

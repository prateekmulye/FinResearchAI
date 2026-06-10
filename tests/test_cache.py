# tests/test_cache.py
"""Warehouse-backed verdict cache (WP-2): roundtrip, inclusive freshness boundary,
newest-wins recency, disabled no-op behavior, and degrade-on-DB-error.

Backend pattern: a file-backed SQLite URL (a `:memory:` aiosqlite URL gives each
pooled connection a FRESH empty DB, so the file URL is the safe choice), env var
via monkeypatch, ``reset_engine()`` around each test (engine has event-loop
affinity), and ``bootstrap.create_all`` once per test DB.
"""
from __future__ import annotations

import pytest

from src.config import settings as settings_mod
from src.llm.schemas import FinalDecision
from src.memory.cache import get_cached_verdict, store_verdict
from src.warehouse import db as db_mod
from src.warehouse.bootstrap import create_all
from src.warehouse.db import get_engine, reset_engine, session_scope
from src.warehouse.repos import insert_verdict


def _decision(action="BUY", score=70):
    return FinalDecision(action=action, conviction=0.8, score=score, rationale="r")


@pytest.fixture
async def warehouse(monkeypatch, tmp_path):
    """Enable the warehouse on a per-test SQLite file with the schema created."""
    monkeypatch.setenv("DATABASE_URL", f"sqlite+aiosqlite:///{tmp_path}/cache.db")
    settings_mod.get_settings.cache_clear()
    await reset_engine()
    await create_all(get_engine())
    yield
    await reset_engine()
    settings_mod.get_settings.cache_clear()


async def test_store_then_get_roundtrips_final_decision(warehouse):
    decision = _decision()
    await store_verdict("AAPL", decision, now=1000)

    got = await get_cached_verdict("AAPL", max_age_min=60, now=1000 + 30 * 60)  # 30 min old
    assert got is not None
    assert isinstance(got, FinalDecision)
    assert got == decision


async def test_freshness_boundary_is_inclusive(warehouse):
    await store_verdict("AAPL", _decision(score=42), now=1000)

    at_limit = await get_cached_verdict("AAPL", max_age_min=60, now=1000 + 60 * 60)
    assert at_limit is not None, "verdict exactly at max_age_min boundary must be fresh"
    assert at_limit.score == 42

    one_past = await get_cached_verdict("AAPL", max_age_min=60, now=1000 + 60 * 60 + 1)
    assert one_past is None


async def test_newest_verdict_wins(warehouse):
    await store_verdict("AAPL", _decision(action="SELL", score=10), now=1000)
    await store_verdict("AAPL", _decision(action="BUY", score=90), now=2000)  # newer

    got = await get_cached_verdict("AAPL", max_age_min=1000, now=2000)
    assert got is not None
    assert got.action == "BUY"
    assert got.score == 90


async def test_miss_for_unknown_ticker(warehouse):
    await store_verdict("AAPL", _decision(), now=1000)
    assert await get_cached_verdict("ZZZZ", max_age_min=60, now=1000) is None


async def test_disabled_warehouse_get_returns_none_and_store_noops():
    # env_isolation (autouse) scrubbed DATABASE_URL -> warehouse disabled.
    await store_verdict("AAPL", _decision(), now=1000)  # must not raise
    assert await get_cached_verdict("AAPL", max_age_min=60, now=1000) is None


async def test_db_error_degrades_get_to_none(warehouse, monkeypatch):
    await store_verdict("AAPL", _decision(), now=1000)

    def _boom():
        raise RuntimeError("db down")

    # session_scope() calls db.get_sessionmaker() internally; breaking it
    # simulates a dead database for the lookup path.
    monkeypatch.setattr(db_mod, "get_sessionmaker", _boom)
    got = await get_cached_verdict("AAPL", max_age_min=60, now=1000)
    assert got is None  # degrade, never raise into the graph


async def test_corrupt_decision_payload_degrades_to_none(warehouse):
    from datetime import UTC, datetime

    async with session_scope() as session:
        await insert_verdict(
            session, "AAPL", {"garbage": True}, datetime.fromtimestamp(1000, tz=UTC)
        )
    got = await get_cached_verdict("AAPL", max_age_min=60, now=1000)
    assert got is None  # invalid FinalDecision dump must not raise

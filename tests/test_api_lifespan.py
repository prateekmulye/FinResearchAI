# tests/test_api_lifespan.py
"""App lifespan (WP-3): startup seeds the watchlist when the warehouse is
enabled and starts the collector only when BOTH flags are on; shutdown stops
the scheduler and disposes the engine. Existing route behavior is untouched
(the rest of tests/test_api_*.py proves that under the same lifespan).

TestClient is used as a context manager — that is what drives lifespan
startup/shutdown (the pattern the other test_api modules already use).
"""
from __future__ import annotations

import asyncio

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import create_async_engine
from starlette.testclient import TestClient

import pytest

from src.api.main import create_app
from src.collector import scheduler as scheduler_mod
from src.collector.watchlist import SEED_WATCHLIST
from src.config import settings as settings_mod
from src.warehouse.bootstrap import create_all
from src.warehouse.db import enable_sqlite_fks, reset_engine
from src.warehouse.models import Instrument


@pytest.fixture
def warehouse_env(monkeypatch, tmp_path):
    """Warehouse enabled on a SQLite file with the schema pre-created.

    Unlike the async ``sqlite_warehouse`` fixture, NO engine is left memoized:
    the lifespan runs on TestClient's portal loop and must create (and at
    shutdown dispose) its own engine there — a memo from the pytest loop would
    violate the engine's loop affinity.
    """
    url = f"sqlite+aiosqlite:///{tmp_path}/lifespan.db"

    async def _prepare():
        await reset_engine()  # drop any memo from a previous test/loop
        engine = create_async_engine(url)
        enable_sqlite_fks(engine)
        await create_all(engine)
        await engine.dispose()

    asyncio.run(_prepare())
    monkeypatch.setenv("DATABASE_URL", url)
    settings_mod.get_settings.cache_clear()
    yield url
    asyncio.run(reset_engine())
    settings_mod.get_settings.cache_clear()


def _instrument_count(url: str) -> int:
    """Count instruments with a throwaway engine (no loop-affinity hazards)."""

    async def _go() -> int:
        engine = create_async_engine(url)
        try:
            async with engine.connect() as conn:
                result = await conn.execute(select(func.count()).select_from(Instrument))
                return result.scalar_one()
        finally:
            await engine.dispose()

    return asyncio.run(_go())


def test_lifespan_noop_when_warehouse_disabled(monkeypatch):
    # env_isolation (autouse) scrubbed DATABASE_URL -> warehouse disabled.
    from src.api import lifespan as lifespan_mod

    calls: list[str] = []

    async def _spy_seed():
        calls.append("seed")
        return 0

    monkeypatch.setattr(lifespan_mod, "seed_watchlist", _spy_seed)
    monkeypatch.setattr(lifespan_mod, "start_collector", lambda: calls.append("start"))

    with TestClient(create_app()) as client:
        assert client.get("/healthz").status_code == 200
    assert calls == [], "disabled warehouse: lifespan must not seed or start anything"


def test_lifespan_seeds_watchlist_but_no_scheduler_by_default(warehouse_env):
    # COLLECTOR_ENABLED defaults to False -> seed only, scheduler never starts.
    with TestClient(create_app()) as client:
        assert client.get("/healthz").status_code == 200
        assert scheduler_mod._scheduler is None
    assert _instrument_count(warehouse_env) == len(SEED_WATCHLIST)


def test_lifespan_starts_and_stops_collector_with_both_flags(warehouse_env, monkeypatch):
    monkeypatch.setenv("COLLECTOR_ENABLED", "true")
    settings_mod.get_settings.cache_clear()

    with TestClient(create_app()) as client:
        assert client.get("/healthz").status_code == 200
        assert scheduler_mod._scheduler is not None
        assert scheduler_mod._scheduler.running
    # Shutdown stopped the collector and cleared the module handle.
    assert scheduler_mod._scheduler is None
    assert _instrument_count(warehouse_env) == len(SEED_WATCHLIST)


def test_lifespan_seed_failure_does_not_break_startup(warehouse_env, monkeypatch, caplog):
    from src.api import lifespan as lifespan_mod

    async def _boom():
        raise RuntimeError("seed exploded")

    monkeypatch.setattr(lifespan_mod, "seed_watchlist", _boom)
    with caplog.at_level("WARNING"):
        with TestClient(create_app()) as client:
            assert client.get("/healthz").status_code == 200, "startup must survive seed failure"

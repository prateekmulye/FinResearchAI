# src/api/lifespan.py
"""App lifespan (WP-3): warehouse seeding + the gated in-process collector.

Startup: when the warehouse is enabled, idempotently seed the watchlist and —
only if ``collector_enabled`` too — start the APScheduler collector. Shutdown:
stop the scheduler (if started) and dispose the warehouse engine.

Everything degrades: a seed/scheduler/DB failure is logged and ignored so it
can NEVER affect app startup or shutdown (the WP-3 invariant).
"""
from __future__ import annotations

import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI

from src.collector import seed_watchlist, start_collector, stop_collector
from src.config.settings import get_settings
from src.warehouse.db import reset_engine, warehouse_enabled

_LOG = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    started = None
    if warehouse_enabled():
        # seed_watchlist/start_collector already never raise, but startup is
        # sacred — guard anyway per the WP-3 degrade-everywhere contract.
        try:
            seeded = await seed_watchlist()
            _LOG.info("lifespan: watchlist seeded (%d instruments)", seeded)
        except Exception as exc:
            _LOG.warning("lifespan: watchlist seeding failed: %s", exc, exc_info=exc)
        if get_settings().collector_enabled:
            try:
                started = start_collector()
            except Exception as exc:
                _LOG.warning("lifespan: collector start failed: %s", exc, exc_info=exc)
    try:
        yield
    finally:
        if started is not None:
            stop_collector()
        try:
            await reset_engine()
        except Exception as exc:
            _LOG.warning("lifespan: engine disposal failed: %s", exc, exc_info=exc)

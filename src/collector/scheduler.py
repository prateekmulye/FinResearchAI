# src/collector/scheduler.py
"""APScheduler wiring for the in-process collector (WP-3).

The scheduler only ever starts when BOTH ``collector_enabled`` (settings) and
``warehouse_enabled()`` are true; ``start_collector`` is the single gated entry
point (the API lifespan calls it). The interval job carries ~300s jitter so
multiple replicas don't sweep yfinance in lockstep.
"""
from __future__ import annotations

import logging
from datetime import UTC, datetime, timedelta

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.interval import IntervalTrigger

from src.collector.service import collect_once
from src.config.settings import get_settings
from src.warehouse.db import warehouse_enabled

_LOG = logging.getLogger(__name__)

_JOB_ID = "warehouse-collector"
_scheduler: AsyncIOScheduler | None = None


def create_scheduler() -> AsyncIOScheduler:
    """Build (without starting) the scheduler with the jittered interval job."""
    scheduler = AsyncIOScheduler(timezone="UTC")
    scheduler.add_job(
        collect_once,
        trigger=IntervalTrigger(
            hours=get_settings().collector_interval_hours, jitter=300, timezone="UTC"
        ),
        id=_JOB_ID,
        name="warehouse collector sweep",
        max_instances=1,
        coalesce=True,
        # Without this the FIRST sweep would be a full interval (hours) away:
        # prime a fresh process ~5 minutes after boot. The staleness guards in
        # collect_once make an early sweep cheap.
        next_run_time=datetime.now(UTC) + timedelta(minutes=5),
    )
    return scheduler


def start_collector() -> AsyncIOScheduler | None:
    """Start the collector iff collector_enabled AND warehouse_enabled.

    Idempotent (a second call returns the running scheduler) and never raises:
    a scheduler failure must not affect app startup. Must be called from within
    a running asyncio event loop (AsyncIOScheduler binds to it).
    """
    global _scheduler
    if not (get_settings().collector_enabled and warehouse_enabled()):
        return None
    if _scheduler is not None:
        return _scheduler
    try:
        scheduler = create_scheduler()
        scheduler.start()
    except Exception as exc:
        _LOG.warning("collector: scheduler failed to start: %s", exc, exc_info=exc)
        return None
    _scheduler = scheduler
    _LOG.info(
        "collector started: sweep every %dh (+/- 300s jitter)",
        get_settings().collector_interval_hours,
    )
    return _scheduler


def stop_collector() -> None:
    """Shut the scheduler down if it was started; safe to call regardless."""
    global _scheduler
    scheduler, _scheduler = _scheduler, None
    if scheduler is None:
        return
    try:
        scheduler.shutdown(wait=False)
    except Exception as exc:
        _LOG.warning("collector: scheduler shutdown failed: %s", exc, exc_info=exc)

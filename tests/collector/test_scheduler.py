# tests/collector/test_scheduler.py
"""Scheduler wiring (WP-3): interval from settings, jittered daily job, and the
collector_enabled AND warehouse_enabled start gate. Jobs are never fired here
(interval is hours-scale; nothing sleeps)."""
from __future__ import annotations

from datetime import UTC, datetime, timedelta

from src.collector import scheduler as scheduler_mod
from src.collector.scheduler import create_scheduler, start_collector, stop_collector
from src.collector.service import collect_once
from src.config import settings as settings_mod


def test_create_scheduler_configures_interval_job(monkeypatch):
    monkeypatch.setenv("COLLECTOR_INTERVAL_HOURS", "6")
    settings_mod.get_settings.cache_clear()

    before = datetime.now(UTC)
    sched = create_scheduler()
    after = datetime.now(UTC)

    jobs = sched.get_jobs()
    assert len(jobs) == 1
    assert jobs[0].func is collect_once  # pin the wiring
    trigger = jobs[0].trigger
    assert trigger.interval == timedelta(hours=6)
    assert trigger.jitter == 300
    # First sweep is primed ~5 minutes after boot, not a full interval away.
    five_min = timedelta(minutes=5)
    assert before + five_min <= jobs[0].next_run_time <= after + five_min
    assert not sched.running  # create only configures; start is separate


def test_start_collector_requires_collector_flag():
    # collector_enabled defaults to False -> never starts, even if warehouse on.
    assert start_collector() is None
    assert scheduler_mod._scheduler is None


def test_start_collector_requires_warehouse(monkeypatch):
    monkeypatch.setenv("COLLECTOR_ENABLED", "true")
    settings_mod.get_settings.cache_clear()
    # DATABASE_URL scrubbed by env_isolation -> warehouse disabled -> no start.
    assert start_collector() is None
    assert scheduler_mod._scheduler is None


async def test_start_and_stop_collector_with_both_flags(sqlite_warehouse, monkeypatch):
    import asyncio

    monkeypatch.setenv("COLLECTOR_ENABLED", "true")
    settings_mod.get_settings.cache_clear()

    sched = start_collector()
    try:
        assert sched is not None
        assert sched.running
        assert scheduler_mod._scheduler is sched
        # Idempotent: a second start returns the same running scheduler.
        assert start_collector() is sched
    finally:
        stop_collector()
    assert scheduler_mod._scheduler is None
    # AsyncIOScheduler._shutdown is @run_in_event_loop: called from inside the
    # loop it only SCHEDULES the state flip — yield once so it takes effect.
    await asyncio.sleep(0)
    assert not sched.running


def test_stop_collector_when_never_started_is_safe():
    stop_collector()  # must not raise
    assert scheduler_mod._scheduler is None

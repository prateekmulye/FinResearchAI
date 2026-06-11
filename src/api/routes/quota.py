"""GET /api/quota — today's demo-guard usage for the calling IP (WP-5).

Read-only: reports the UTC-day counters the demo guard increments, plus
whether the caller's X-Admin-Token grants the bypass. The UI uses this to
show "N live runs left today" and to steer capped users toward replays.

When the warehouse is disabled there IS no quota system: respond 200 with
``metered=false`` (counters null, admin still computed) so the UI can tell
"unmetered demo" apart from an outage — never a 503.

When the warehouse is enabled but the DB read FAILS (an outage, not absence):
respond 200 with ``metered=true``, ``degraded=true`` and null counters — the
honest "quota system exists but is unreadable right now" shape. Never a 500:
a status endpoint outage must not break the page (the demo guard itself fails
open on the same condition).
"""
from __future__ import annotations

import logging
from datetime import UTC, datetime

from fastapi import APIRouter, Request

from src.api.demo_guard import GLOBAL_QUOTA_KEY, is_admin, quota_key_for
from src.api.routes.dto import QuotaStatus
from src.config.settings import get_settings
from src.warehouse.db import session_scope, warehouse_enabled
from src.warehouse.repos import get_quota

_LOG = logging.getLogger(__name__)

router = APIRouter()


@router.get("/quota", response_model=QuotaStatus)
async def quota(request: Request) -> QuotaStatus:
    admin = is_admin(request)
    if not warehouse_enabled():
        return QuotaStatus(metered=False, admin=admin)
    settings = get_settings()
    day = datetime.now(UTC).date()
    try:
        async with session_scope() as session:
            ip_used = await get_quota(session, quota_key_for(request), day)
            global_used = await get_quota(session, GLOBAL_QUOTA_KEY, day)
    except Exception as exc:  # DB outage: degrade to null counters, never 500
        _LOG.warning("quota: read failed; degrading to null counters: %s", exc)
        return QuotaStatus(metered=True, degraded=True, admin=admin)
    return QuotaStatus(
        metered=True,
        ip_used=ip_used,
        ip_limit=settings.demo_runs_per_ip_per_day,
        global_used=global_used,
        global_limit=settings.demo_runs_global_per_day,
        admin=admin,
    )

"""Daily demo-run guard for POST /api/analyze (WP-5).

One FastAPI dependency (``demo_guard``) enforces, in order:

  1. **Admin bypass** — ``X-Admin-Token`` compared with
     ``secrets.compare_digest`` against ``settings.admin_token``. Only possible
     when a token is configured; empty/unset means no bypass exists. Admins
     skip BOTH the per-hour burst limiter and the daily caps.
  2. **Per-hour burst limiter** — the pre-existing sliding-window limiter
     (``app.state.limiter``, the fast abuse brake: 5 per rolling hour per IP
     by default). It runs inside this guard so admin bypass and ordering live
     in exactly one place, and so a burst-limited request never burns daily
     quota.
  3. **Daily caps** — per-IP (``ip:{client_key}``) and ``global`` counters in
     the warehouse ``demo_quota`` table, keyed by UTC day.

Increment-FIRST design (documented choice): the per-IP counter is atomically
upserted+incremented BEFORE its limit comparison, so there is no
check-then-increment race window; the cost is that an over-limit attempt still
consumes IP quota — acceptable for a demo cap, and it makes hammering strictly
unprofitable. The GLOBAL counter is only incremented when the IP counter is
within its limit (same transaction), so one hammering IP can never drain the
shared global pool. The 429 is raised AFTER the session commits, so the
increments always persist.

The guard declares the request body (``AnalyzeRequest``), so schema-invalid
requests 422 before any quota is consumed; the route receives the parsed body
through the dependency.

Degrade contract: warehouse disabled -> the daily caps no-op (the per-hour
burst limiter still applies); a broken DB logs a warning and FAILS OPEN (a
quota outage must not take down live demos — same ethos as the ingest layer).
"""
from __future__ import annotations

import logging
import secrets
from datetime import UTC, datetime

from fastapi import HTTPException, Request
from fastapi.responses import JSONResponse

from src.api.client_ip import client_key
from src.api.schemas import AnalyzeRequest
from src.config.settings import get_settings
from src.warehouse.db import session_scope, warehouse_enabled
from src.warehouse.repos import increment_quota

_LOG = logging.getLogger(__name__)

ADMIN_TOKEN_HEADER = "X-Admin-Token"
GLOBAL_QUOTA_KEY = "global"


class DailyQuotaExceeded(Exception):
    """Raised by the guard; rendered by ``daily_quota_handler`` (registered in
    create_app) as the structured 429 the UI uses to steer users to replays."""

    def __init__(self, scope: str, limit: int) -> None:
        super().__init__(f"daily live-run limit reached ({scope}: {limit})")
        self.scope = scope
        self.limit = limit


async def daily_quota_handler(request: Request, exc: Exception) -> JSONResponse:
    assert isinstance(exc, DailyQuotaExceeded)
    return JSONResponse(
        status_code=429,
        content={
            "detail": "daily live-run limit reached",
            "scope": exc.scope,
            "limit": exc.limit,
        },
    )


def is_admin(request: Request) -> bool:
    """True iff a non-empty admin token is configured AND the header matches it.

    Compares UTF-8 encoded bytes: ``secrets.compare_digest`` raises TypeError on
    non-ASCII *str* inputs, and header values are attacker-controlled — a "£" in
    the header must be a failed match, never a 500."""
    token = get_settings().admin_token
    if not token:
        return False
    supplied = request.headers.get(ADMIN_TOKEN_HEADER) or ""
    return secrets.compare_digest(supplied.encode("utf-8"), token.encode("utf-8"))


def quota_key_for(request: Request) -> str:
    return f"ip:{client_key(request)}"


async def demo_guard(request: Request, req: AnalyzeRequest) -> AnalyzeRequest:
    """Dependency for POST /api/analyze: admin bypass -> burst limiter -> daily caps."""
    if is_admin(request):
        return req

    if not request.app.state.limiter.allow(client_key(request)):
        raise HTTPException(status_code=429, detail="rate limit exceeded")

    if not warehouse_enabled():
        return req  # no quota store -> daily caps no-op (burst limiter already applied)

    settings = get_settings()
    day = datetime.now(UTC).date()
    exceeded: DailyQuotaExceeded | None = None
    try:
        # ONE session/transaction. IP counter increments first (increment-FIRST,
        # see module docstring); the global counter only increments when the IP
        # is within its limit, so over-IP-cap attempts never drain the global
        # pool. The 429 is raised only after the session commits, so the
        # increments persist.
        async with session_scope() as session:
            ip_count = await increment_quota(session, quota_key_for(request), day)
            if ip_count > settings.demo_runs_per_ip_per_day:
                exceeded = DailyQuotaExceeded("ip", settings.demo_runs_per_ip_per_day)
            else:
                global_count = await increment_quota(session, GLOBAL_QUOTA_KEY, day)
                if global_count > settings.demo_runs_global_per_day:
                    exceeded = DailyQuotaExceeded(
                        "global", settings.demo_runs_global_per_day
                    )
    except Exception as exc:  # fail OPEN: quota outage must not block demos
        _LOG.warning("demo_guard: quota increment failed; failing open: %s", exc)
        return req

    if exceeded is not None:
        raise exceeded
    return req

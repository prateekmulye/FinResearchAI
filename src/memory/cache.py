# src/memory/cache.py
"""Deterministic cross-run verdict cache, backed by the warehouse (WP-2).

Freshness is computed from the stored tz-aware ``ts`` column via a deterministic
``ORDER BY ts DESC`` query keyed by ticker — NOT semantic similarity. This is
the explicit fix for the old code's defect of using similarity search for
recency (the invariant survives the Chroma -> Postgres migration).

The cache is opt-in: when the warehouse is disabled (no ``DATABASE_URL``),
``store_verdict`` is a no-op and ``get_cached_verdict`` returns None. Lookup
errors degrade to None — the cache must never raise into the graph.
"""
from __future__ import annotations

import logging
import time
from datetime import UTC, datetime

from src.llm.schemas import FinalDecision
from src.warehouse.db import session_scope, warehouse_enabled
from src.warehouse.repos import insert_verdict, latest_verdict

_LOG = logging.getLogger(__name__)


async def store_verdict(
    ticker: str,
    decision: FinalDecision,
    *,
    now: int | None = None,
) -> None:
    """Persist a FinalDecision for `ticker`, stamped with epoch `ts`.

    No-op (debug log) when the warehouse is disabled. DB errors propagate; the
    arbiter call site wraps this in its own never-fail try/except.
    """
    if not warehouse_enabled():
        _LOG.debug("verdict cache disabled (no DATABASE_URL); skipping store for %s", ticker)
        return
    ts = int(now if now is not None else time.time())
    async with session_scope() as session:
        await insert_verdict(
            session, ticker, decision.model_dump(), datetime.fromtimestamp(ts, tz=UTC)
        )


async def get_cached_verdict(
    ticker: str,
    max_age_min: int,
    *,
    now: int | None = None,
) -> FinalDecision | None:
    """Return the newest cached FinalDecision for `ticker` if it is no older than
    `max_age_min` minutes (inclusive — exactly at the limit is still fresh);
    otherwise None. Recency is a deterministic ``ORDER BY ts DESC`` (id DESC
    tie-break) query, never similarity search.

    Staleness boundary: a verdict stored at time ``T`` is fresh when called at
    time ``now`` if ``now - T <= max_age_min * 60`` (epoch-seconds arithmetic).
    Returns None when the warehouse is disabled; any DB/parse error is logged
    and degrades to None (a cache miss must never abort the graph).
    """
    if not warehouse_enabled():
        return None
    try:
        # Deliberate session_scope reuse on the read path: a commit after the SELECT
        # is accepted for the simplicity of one shared transaction helper.
        async with session_scope() as session:
            row = await latest_verdict(session, ticker)
            if row is None:
                return None
            current = int(now if now is not None else time.time())
            if current - int(row.ts.timestamp()) > max_age_min * 60:
                return None
            return FinalDecision(**row.decision)
    except Exception as exc:
        _LOG.warning("verdict cache lookup failed (%s); treating as miss", exc, exc_info=exc)
        return None

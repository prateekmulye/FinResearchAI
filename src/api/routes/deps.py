"""Shared request dependencies for the /api routers (WP-5)."""
from __future__ import annotations

from fastapi import HTTPException

from src.api.schemas import TICKER_RE
from src.warehouse.db import warehouse_enabled


def require_warehouse() -> None:
    """503 when the warehouse subsystem is disabled (DATABASE_URL unset).

    Applied to every warehouse-read endpoint EXCEPT /api/runs/{id}, which keeps
    a JSONL fallback when the warehouse can't answer."""
    if not warehouse_enabled():
        raise HTTPException(status_code=503, detail="warehouse disabled")


def ticker_path(ticker: str) -> str:
    """Normalize + validate a {ticker} path param against the strict allowlist.

    Junk (traversal, injection attempts, emoji, over-long strings) gets a 422
    before any DB or LLM work — the same regex AnalyzeRequest enforces."""
    normalized = ticker.strip().upper()
    if not TICKER_RE.fullmatch(normalized):
        raise HTTPException(status_code=422, detail=f"invalid ticker: {ticker!r}")
    return normalized


def clamp_limit(limit: int, *, lo: int = 1, hi: int = 100) -> int:
    """Silently clamp a client-supplied limit into [lo, hi]."""
    return max(lo, min(limit, hi))

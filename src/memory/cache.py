# src/memory/cache.py
"""Deterministic cross-run verdict cache.

Freshness is computed from a stored integer `ts` (epoch seconds) via a metadata
`where` query keyed by ticker — NOT semantic similarity. This is the explicit
fix for the old code's defect of using similarity search for recency.
"""
from __future__ import annotations

import json
import time
from typing import Any, Callable

from src.llm.schemas import FinalDecision
from src.memory.store import VectorStore

_COLLECTION = "verdicts"


def _get_store(store: Any | None) -> Any:
    return store if store is not None else VectorStore()


def store_verdict(
    ticker: str,
    decision: FinalDecision,
    *,
    store: Any | None = None,
    now: int | None = None,
    clock: Callable[[], float] = time.time,
) -> None:
    """Persist a FinalDecision for `ticker`, stamped with epoch `ts`."""
    store = _get_store(store)
    ts = int(now if now is not None else clock())
    doc = json.dumps(decision.model_dump())
    store.add(doc=doc, metadata={"ticker": ticker, "ts": ts})


def get_cached_verdict(
    ticker: str,
    max_age_min: int,
    *,
    store: Any | None = None,
    now: int | None = None,
    clock: Callable[[], float] = time.time,
) -> FinalDecision | None:
    """Return the newest cached FinalDecision for `ticker` if it is younger than
    `max_age_min`; otherwise None. Uses a deterministic metadata `where` query."""
    store = _get_store(store)
    rows = store.query_by({"ticker": ticker})  # metadata filter, NOT similarity
    if not rows:
        return None
    newest = max(rows, key=lambda r: r["metadata"].get("ts", 0))
    ts = int(newest["metadata"].get("ts", 0))
    current = int(now if now is not None else clock())
    if current - ts > max_age_min * 60:
        return None
    return FinalDecision(**json.loads(newest["document"]))

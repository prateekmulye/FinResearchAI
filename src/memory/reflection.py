# src/memory/reflection.py
"""STRETCH: reflection log — store a past verdict + realized forward return,
retrieve prior outcomes for a ticker. Reuses VectorStore + metadata `where`
query (no similarity). Behind the same store; additive to the frozen contract.
"""
from __future__ import annotations

import json
import time
from typing import Any, Callable

from src.llm.schemas import FinalDecision
from src.memory.store import VectorStore

_COLLECTION = "reflections"


def _get_store(store: Any | None) -> Any:
    return store if store is not None else VectorStore(collection=_COLLECTION)


def log_outcome(
    ticker: str,
    decision: FinalDecision,
    forward_return: float,
    *,
    store: Any | None = None,
    now: int | None = None,
    clock: Callable[[], float] = time.time,
) -> None:
    """Persist {decision, realized forward_return} for later reflection."""
    store = _get_store(store)
    ts = int(now if now is not None else clock())
    doc = json.dumps(decision.model_dump())
    store.add(
        doc=doc,
        metadata={"ticker": ticker, "ts": ts, "forward_return": float(forward_return)},
    )


def get_prior_outcomes(ticker: str, *, store: Any | None = None) -> list[dict[str, Any]]:
    """Return prior outcomes for `ticker`, newest first, via metadata query.

    Each item: {"decision": FinalDecision, "forward_return": float, "ts": int}.
    """
    store = _get_store(store)
    rows = store.query_by({"ticker": ticker})
    out: list[dict[str, Any]] = []
    for r in rows:
        meta = r["metadata"]
        out.append(
            {
                "decision": FinalDecision(**json.loads(r["document"])),
                "forward_return": float(meta.get("forward_return", 0.0)),
                "ts": int(meta.get("ts", 0)),
            }
        )
    out.sort(key=lambda o: o["ts"], reverse=True)
    return out

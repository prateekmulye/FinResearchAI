"""Router node: resolve ticker -> (resolved_ticker, screener, exchange), pick a
model plan, and optionally short-circuit on a cached verdict.

`TickerResolution` is defined locally (not in the frozen src/llm/schemas.py) to
keep the data contract untouched, per WP-B scope.

STRUCT_METHOD is imported from src.llm.factory per COORDINATION §7.5 so a
single flip there propagates to all nodes.
"""
from __future__ import annotations

import logging

from langchain_core.messages import HumanMessage, SystemMessage
from pydantic import BaseModel, Field

from src.agents._metrics import zero_metrics
from src.llm.cost import CostTracker
from src.llm.factory import STRUCT_METHOD, get_llm

_LOG = logging.getLogger(__name__)

_SYSTEM = """You resolve a user-provided stock symbol or company name to an exact
exchange-qualified ticker for data APIs.

Rules:
- US (NASDAQ/NYSE/AMEX): no suffix. screener="america".
- India NSE: suffix ".NS", screener="india", exchange="NSE". BSE: ".BO", "BSE".
- Japan TSE: ".T", screener="japan", exchange="TSE".
- China SSE: ".SS" / SZSE: ".SZ", screener="china".
- Hong Kong HKEX: ".HK", screener="hongkong", exchange="HKEX".
Return resolved_ticker exactly as a data API expects it."""


class TickerResolution(BaseModel):
    """LLM-resolved symbol routing. Local to WP-B (not the frozen schema set)."""

    resolved_ticker: str = Field(description="Exchange-qualified ticker, e.g. AAPL or RELIANCE.NS")
    screener: str = Field(default="america", description="TradingView screener, e.g. america, india")
    exchange: str = Field(default="NASDAQ", description="Exchange code, e.g. NASDAQ, NSE")


def _model_plan() -> dict:
    """Tier-per-phase routing (M7). Quick for retrieval/analysts; deep for reasoning."""
    return {"analysts": "quick", "debate": "deep", "verdict": "deep", "risk": "deep"}


def _get_cached_verdict(ticker: str, max_age_min: int):
    """Guarded import of the WP-C cache. Returns None if memory is not merged yet."""
    try:
        from src.memory.cache import get_cached_verdict
    except ImportError:
        # Expected when WP-C is not yet merged; stay silent.
        return None
    try:
        return get_cached_verdict(ticker, max_age_min)
    except Exception as exc:
        _LOG.warning("verdict cache lookup failed: %s", exc)
        return None


async def router(state: dict) -> dict:
    tracker = CostTracker("router")
    raw_ticker = (state.get("ticker") or "").strip()

    llm = get_llm("quick").with_structured_output(TickerResolution, method=STRUCT_METHOD)
    messages = [
        SystemMessage(content=_SYSTEM),
        HumanMessage(content=f"Resolve this symbol or company: {raw_ticker!r}"),
    ]
    resolution: TickerResolution = await llm.ainvoke(messages, config={"callbacks": [tracker]})

    per_node = tracker.totals()["per_node"]
    # Guarantee at least one metrics record (tracker is empty when LLM call was
    # a no-op in unit tests or when structured-output bypasses callbacks).
    if not per_node:
        per_node = zero_metrics("router")

    out: dict = {
        "resolved_ticker": resolution.resolved_ticker,
        "screener": resolution.screener,
        "exchange": resolution.exchange,
        "model_plan": _model_plan(),
        "run_metrics": per_node,
    }

    # Optional cache short-circuit (WP-C). If a fresh verdict exists, attach it so
    # the graph (WP-D's conditional edge) can skip straight to the reporter.
    cached = _get_cached_verdict(resolution.resolved_ticker, max_age_min=60)
    if cached is not None:
        out["final_decision"] = cached.model_dump()
        out["model_plan"] = {**out["model_plan"], "cache_hit": True}

    return out

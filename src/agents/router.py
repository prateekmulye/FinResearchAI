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
from src.warehouse.ingest import ensure_instrument

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


async def _get_cached_verdict(ticker: str, max_age_min: int):
    """Guarded import of the verdict cache (WP-2: async, warehouse-backed).

    Returns None if the memory module is absent or the lookup fails.
    """
    try:
        from src.memory.cache import get_cached_verdict
    except ImportError:
        # Expected when the memory module is not present; stay silent.
        return None
    try:
        return await get_cached_verdict(ticker, max_age_min)
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
    resolved_ok = True
    try:
        resolution: TickerResolution = await llm.ainvoke(
            messages, config={"callbacks": [tracker]}
        )
    except Exception as exc:
        # The router is the entry node: an unhandled failure would abort the whole
        # graph. Degrade to a US-default resolution so the pipeline still runs.
        _LOG.warning("router: LLM resolution failed (%s); degrading to raw ticker", exc)
        resolved_ok = False
        resolution = TickerResolution(
            resolved_ticker=raw_ticker or "UNKNOWN", screener="america", exchange="NASDAQ"
        )

    if resolved_ok:
        # Write-through (WP-3): persist the resolved instrument so the warehouse
        # knows every ticker ever analyzed. Deliberately a bare call (no local
        # try/except): ensure_instrument never raises — it no-ops when the
        # warehouse is disabled and logs+degrades on any DB error — so a DB
        # problem cannot affect routing. The degraded path above is skipped:
        # an unverified default resolution must not pollute the instruments table.
        # Known limitation: ``exchange`` comes straight from the LLM resolution;
        # a wrong exchange (e.g. the NASDAQ default for an NYSE-listed name)
        # splits an instrument across two (ticker, exchange) rows. Exchange
        # normalization is deferred to the debt-sweep WP.
        await ensure_instrument(
            resolution.resolved_ticker, resolution.exchange, resolution.screener
        )

    per_node = tracker.totals()["per_node"]
    # Guarantee at least one metrics record (tracker is empty when LLM call was
    # a no-op in unit tests, degraded above, or when structured-output bypasses callbacks).
    if not per_node:
        per_node = zero_metrics("router")

    out: dict = {
        "resolved_ticker": resolution.resolved_ticker,
        "screener": resolution.screener,
        "exchange": resolution.exchange,
        "model_plan": _model_plan(),
        "run_metrics": per_node,
    }

    # Optional cache short-circuit. If a fresh verdict exists, attach it so
    # the graph (WP-D's conditional edge) can skip straight to the reporter.
    cached = await _get_cached_verdict(resolution.resolved_ticker, max_age_min=60)
    if cached is not None:
        out["final_decision"] = cached.model_dump()
        out["model_plan"] = {**out["model_plan"], "cache_hit": True}

    return out

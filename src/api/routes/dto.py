"""Response DTOs for the /api read endpoints (WP-5).

These are API-shape models ONLY — deliberately separate from the frozen node
I/O contract in ``src/llm/schemas.py``. ``from_attributes=True`` lets routes
validate straight from the warehouse ORM rows.
"""
from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict


# --------------------------------------------------------------------- library


class RunCostSummary(BaseModel):
    """Totals derived from the stored per-node ``run_metrics`` records."""

    cost_usd: float = 0.0
    latency_s: float = 0.0
    prompt_tokens: int = 0
    completion_tokens: int = 0
    total_tokens: int = 0


def cost_from_metrics(metrics: Any) -> RunCostSummary | None:
    """Sum per-node metric dicts into a RunCostSummary; None when there are none.

    Tolerant of missing keys/odd shapes (metrics is a free-form JSON column)."""
    if not isinstance(metrics, list) or not metrics:
        return None
    records = [r for r in metrics if isinstance(r, dict)]
    if not records:
        return None
    prompt = sum(int(r.get("prompt_tokens", 0) or 0) for r in records)
    completion = sum(int(r.get("completion_tokens", 0) or 0) for r in records)
    return RunCostSummary(
        cost_usd=round(sum(float(r.get("cost_usd", 0.0) or 0.0) for r in records), 6),
        latency_s=round(sum(float(r.get("latency_s", 0.0) or 0.0) for r in records), 4),
        prompt_tokens=prompt,
        completion_tokens=completion,
        total_tokens=prompt + completion,
    )


class RunSummary(BaseModel):
    run_id: str
    ticker: str
    debate_mode: str
    status: str
    started_at: datetime
    finished_at: datetime | None = None
    final_decision: dict[str, Any] | None = None
    cost: RunCostSummary | None = None


class LibraryResponse(BaseModel):
    runs: list[RunSummary]
    total: int


class RunDetail(BaseModel):
    """Full run + replay payload. ``source`` says which store answered:
    "warehouse" rows carry the run fields + ordered name/data/ts_ms events;
    the "jsonl" fallback carries only run_id + the raw RunRecorder lines."""

    run_id: str
    source: Literal["warehouse", "jsonl"]
    ticker: str | None = None
    debate_mode: str | None = None
    status: str | None = None
    started_at: datetime | None = None
    finished_at: datetime | None = None
    final_decision: dict[str, Any] | None = None
    report: str | None = None
    metrics: Any = None
    cost: RunCostSummary | None = None
    events: list[dict[str, Any]]


# ---------------------------------------------------------------------- market


class InstrumentOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    ticker: str
    exchange: str
    screener: str
    name: str | None = None
    country: str | None = None
    currency: str | None = None
    sector: str | None = None
    watched: bool = False


class InstrumentsResponse(BaseModel):
    instruments: list[InstrumentOut]


class PriceBarOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    ts: datetime
    open: float
    high: float
    low: float
    close: float
    volume: int | None = None


class PricesResponse(BaseModel):
    ticker: str
    exchange: str
    interval: str = "1d"
    bars: list[PriceBarOut]


class FundamentalsResponse(BaseModel):
    ticker: str
    exchange: str
    ts: datetime
    market_cap: float | None = None
    pe_ratio: float | None = None
    eps: float | None = None
    revenue_growth: float | None = None
    profit_margin: float | None = None
    payload: dict[str, Any] = {}


class NewsItemOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    ts: datetime
    title: str
    url: str
    source: str | None = None
    snippet: str | None = None


class NewsResponse(BaseModel):
    ticker: str
    exchange: str
    items: list[NewsItemOut]


# ---------------------------------------------------------------------- search


class SearchHitOut(BaseModel):
    """One /api/search hit (validates straight from ``repos.SearchHit``).

    ``ref`` is the news url or the run_id depending on ``kind``. ``score`` is
    the cosine distance (lower = closer) in semantic mode, null in keyword mode.
    """

    model_config = ConfigDict(from_attributes=True)

    kind: Literal["news", "run"]
    ref: str
    ticker: str
    title: str
    snippet: str | None = None
    score: float | None = None
    ts: datetime


class SearchResponse(BaseModel):
    """``mode`` reports which path actually answered (honest fallback)."""

    mode: Literal["semantic", "keyword"]
    hits: list[SearchHitOut]


# ------------------------------------------------------------------------ eval


class EvalResultOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    label: str
    created_at: datetime
    summary: dict[str, Any]
    pairs: Any = None


class EvalResultsResponse(BaseModel):
    results: list[EvalResultOut]


# ----------------------------------------------------------------------- quota


class QuotaStatus(BaseModel):
    """``metered=False`` means there is no quota system at all (warehouse
    disabled) — distinct from a quota outage — and the counter fields are null.
    ``degraded=True`` means the quota system exists but its DB read failed
    (``metered=True`` with null counters — the guard fails open on the same
    condition). ``admin`` is computed in every case."""

    metered: bool
    degraded: bool = False
    ip_used: int | None = None
    ip_limit: int | None = None
    global_used: int | None = None
    global_limit: int | None = None
    admin: bool

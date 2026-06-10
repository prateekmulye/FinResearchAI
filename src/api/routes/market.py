"""Market Explorer reads (WP-5): /api/market/instruments and per-ticker
prices/fundamentals/news. All endpoints require the warehouse (503 otherwise)
and validate the {ticker} path param before touching the DB.
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from src.api.routes.deps import clamp_limit, require_warehouse, ticker_path
from src.api.routes.dto import (
    FundamentalsResponse,
    InstrumentOut,
    InstrumentsResponse,
    NewsItemOut,
    NewsResponse,
    PriceBarOut,
    PricesResponse,
)
from src.warehouse.db import session_scope
from src.warehouse.models import Instrument
from src.warehouse.repos import (
    latest_fundamentals,
    list_news_items,
    list_price_bars,
    resolve_instrument,
    search_instruments,
)

router = APIRouter(dependencies=[Depends(require_warehouse)])


async def _resolve_or_404(
    session: AsyncSession, ticker: str, exchange: str | None
) -> Instrument:
    inst = await resolve_instrument(session, ticker, exchange)
    if inst is None:
        raise HTTPException(status_code=404, detail=f"unknown ticker: {ticker}")
    return inst


@router.get("/instruments", response_model=InstrumentsResponse)
async def instruments(q: str = "", limit: int = 20) -> InstrumentsResponse:
    """Case-insensitive substring search on ticker OR name (empty q = all)."""
    limit = clamp_limit(limit)
    async with session_scope() as session:
        rows = await search_instruments(session, q.strip(), limit=limit)
        return InstrumentsResponse(
            instruments=[InstrumentOut.model_validate(r) for r in rows]
        )


@router.get("/{ticker}/prices", response_model=PricesResponse)
async def prices(
    ticker: str = Depends(ticker_path),
    exchange: str | None = None,
    days: int = 365,
) -> PricesResponse:
    """Daily bars ascending by ts within the trailing ``days`` window."""
    days = max(1, min(days, 3650))
    async with session_scope() as session:
        inst = await _resolve_or_404(session, ticker, exchange)
        bars = await list_price_bars(session, inst.id, days=days)
        return PricesResponse(
            ticker=inst.ticker,
            exchange=inst.exchange,
            bars=[PriceBarOut.model_validate(b) for b in bars],
        )


@router.get("/{ticker}/fundamentals", response_model=FundamentalsResponse)
async def fundamentals(
    ticker: str = Depends(ticker_path), exchange: str | None = None
) -> FundamentalsResponse:
    """Latest fundamentals snapshot (known columns + full payload + ts)."""
    async with session_scope() as session:
        inst = await _resolve_or_404(session, ticker, exchange)
        snap = await latest_fundamentals(session, inst.id)
        if snap is None:
            raise HTTPException(
                status_code=404, detail=f"no fundamentals for {ticker}"
            )
        return FundamentalsResponse(
            ticker=inst.ticker,
            exchange=inst.exchange,
            ts=snap.ts,
            market_cap=snap.market_cap,
            pe_ratio=snap.pe_ratio,
            eps=snap.eps,
            revenue_growth=snap.revenue_growth,
            profit_margin=snap.profit_margin,
            payload=snap.payload or {},
        )


@router.get("/{ticker}/news", response_model=NewsResponse)
async def news(
    ticker: str = Depends(ticker_path),
    exchange: str | None = None,
    limit: int = 20,
) -> NewsResponse:
    """Stored headlines for the ticker, newest first."""
    limit = clamp_limit(limit)
    async with session_scope() as session:
        inst = await _resolve_or_404(session, ticker, exchange)
        items = await list_news_items(session, inst.id, limit=limit)
        return NewsResponse(
            ticker=inst.ticker,
            exchange=inst.exchange,
            items=[NewsItemOut.model_validate(i) for i in items],
        )

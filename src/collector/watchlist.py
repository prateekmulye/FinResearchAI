# src/collector/watchlist.py
"""Seed watchlist for the scheduled collector (WP-3): ~30 watched global tickers.

Screener values align with the router prompt vocabulary (src/agents/router.py:
america/india/japan/china/hongkong); the European markets the router doesn't map
use TradingView's country screener names (germany/france/switzerland/uk/
netherlands). Tickers are yfinance-style (exchange suffixes), matching what the
router resolves and what the ingest layer fetches.
"""
from __future__ import annotations

import logging
from typing import NamedTuple

from src.warehouse.db import session_scope, warehouse_enabled
from src.warehouse.repos import upsert_instrument

_LOG = logging.getLogger(__name__)


class SeedInstrument(NamedTuple):
    ticker: str
    exchange: str
    screener: str
    name: str
    country: str


SEED_WATCHLIST: tuple[SeedInstrument, ...] = (
    # --- United States ---
    SeedInstrument("AAPL", "NASDAQ", "america", "Apple Inc.", "United States"),
    SeedInstrument("MSFT", "NASDAQ", "america", "Microsoft Corporation", "United States"),
    SeedInstrument("NVDA", "NASDAQ", "america", "NVIDIA Corporation", "United States"),
    SeedInstrument("AMZN", "NASDAQ", "america", "Amazon.com, Inc.", "United States"),
    SeedInstrument("GOOGL", "NASDAQ", "america", "Alphabet Inc.", "United States"),
    SeedInstrument("META", "NASDAQ", "america", "Meta Platforms, Inc.", "United States"),
    SeedInstrument("TSLA", "NASDAQ", "america", "Tesla, Inc.", "United States"),
    SeedInstrument("BRK-B", "NYSE", "america", "Berkshire Hathaway Inc. (Class B)",
                   "United States"),
    SeedInstrument("JPM", "NYSE", "america", "JPMorgan Chase & Co.", "United States"),
    SeedInstrument("V", "NYSE", "america", "Visa Inc.", "United States"),
    SeedInstrument("UNH", "NYSE", "america", "UnitedHealth Group Incorporated",
                   "United States"),
    SeedInstrument("XOM", "NYSE", "america", "Exxon Mobil Corporation", "United States"),
    # --- India (NSE) ---
    SeedInstrument("RELIANCE.NS", "NSE", "india", "Reliance Industries Limited", "India"),
    SeedInstrument("TCS.NS", "NSE", "india", "Tata Consultancy Services Limited", "India"),
    SeedInstrument("HDFCBANK.NS", "NSE", "india", "HDFC Bank Limited", "India"),
    SeedInstrument("INFY.NS", "NSE", "india", "Infosys Limited", "India"),
    # --- Japan (TSE) ---
    SeedInstrument("7203.T", "TSE", "japan", "Toyota Motor Corporation", "Japan"),
    SeedInstrument("6758.T", "TSE", "japan", "Sony Group Corporation", "Japan"),
    SeedInstrument("9984.T", "TSE", "japan", "SoftBank Group Corp.", "Japan"),
    # --- China (SSE / SZSE) ---
    SeedInstrument("600519.SS", "SSE", "china", "Kweichow Moutai Co., Ltd.", "China"),
    SeedInstrument("000858.SZ", "SZSE", "china", "Wuliangye Yibin Co., Ltd.", "China"),
    # --- Hong Kong (HKEX) ---
    SeedInstrument("0700.HK", "HKEX", "hongkong", "Tencent Holdings Limited", "Hong Kong"),
    SeedInstrument("9988.HK", "HKEX", "hongkong", "Alibaba Group Holding Limited",
                   "Hong Kong"),
    SeedInstrument("1299.HK", "HKEX", "hongkong", "AIA Group Limited", "Hong Kong"),
    # --- Europe ---
    SeedInstrument("ASML.AS", "EURONEXT", "netherlands", "ASML Holding N.V.", "Netherlands"),
    SeedInstrument("SAP.DE", "XETR", "germany", "SAP SE", "Germany"),
    SeedInstrument("MC.PA", "EURONEXT", "france",
                   "LVMH Moet Hennessy Louis Vuitton SE", "France"),
    SeedInstrument("NESN.SW", "SIX", "switzerland", "Nestle S.A.", "Switzerland"),
    SeedInstrument("SHEL.L", "LSE", "uk", "Shell plc", "United Kingdom"),
    SeedInstrument("AZN.L", "LSE", "uk", "AstraZeneca PLC", "United Kingdom"),
)


async def seed_watchlist() -> int:
    """Idempotently upsert every seed instrument with ``watched=True``.

    Every restart re-asserts ``watched=True`` on the seed set — by design: a
    manually un-watched seed instrument is re-watched on the next boot.

    Returns the number of seeded instruments; 0 when the warehouse is disabled
    or on any DB error (logged) — never raises, safe to call at app startup.
    """
    if not warehouse_enabled():
        return 0
    try:
        async with session_scope() as session:
            for seed in SEED_WATCHLIST:
                await upsert_instrument(
                    session,
                    ticker=seed.ticker,
                    exchange=seed.exchange,
                    screener=seed.screener,
                    name=seed.name,
                    country=seed.country,
                    watched=True,
                )
        return len(SEED_WATCHLIST)
    except Exception as exc:
        _LOG.warning("collector: seed_watchlist failed: %s", exc, exc_info=exc)
        return 0

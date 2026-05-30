"""tradingview-ta wrapper (tradingview-ta==3.3.0).

fetch_technicals(ticker, screener, exchange) -> Technicals.
Uses TA_Handler(...).get_analysis(); reads .summary + .indicators.
Keeps an exchange-fallback retry with exponential backoff (mitigates the
rate-limit / wrong-exchange risk noted in the design spec §8.4), then ToolError.
Blocking I/O — callers wrap with `await asyncio.to_thread(...)`.
"""
from __future__ import annotations

import time
from dataclasses import asdict, dataclass

from src.tools import ToolError

# Fallback chain by screener: if the primary exchange fails, try siblings.
_FALLBACKS: dict[str, list[str]] = {
    "america": ["NASDAQ", "NYSE", "AMEX"],
    "india": ["NSE", "BSE"],
}
_MAX_ATTEMPTS = 3
_BACKOFF_BASE = 0.5  # seconds; monkeypatched to 0.0 in unit tests


@dataclass
class Technicals:
    ticker: str
    exchange: str
    recommendation: str
    buy_signals: int
    neutral_signals: int
    sell_signals: int
    rsi: float | None
    macd: float | None
    macd_signal: float | None
    close: float | None

    def to_dict(self) -> dict:
        return asdict(self)


def _analyze(*, symbol: str, screener: str, exchange: str):
    from tradingview_ta import TA_Handler, Interval

    handler = TA_Handler(
        symbol=symbol,
        screener=screener,
        exchange=exchange,
        interval=Interval.INTERVAL_1_DAY,
        timeout=10,
    )
    return handler.get_analysis()


def _candidate_exchanges(screener: str, exchange: str) -> list[str]:
    chain = list(_FALLBACKS.get(screener, []))
    ordered = [exchange] + [e for e in chain if e != exchange]
    # Enforce _MAX_ATTEMPTS bound so dead constant is actually respected.
    return (ordered or [exchange])[:_MAX_ATTEMPTS]


def fetch_technicals(ticker: str, screener: str, exchange: str) -> Technicals:
    candidates = _candidate_exchanges(screener, exchange)
    last_exc: Exception | None = None
    for attempt, ex in enumerate(candidates):
        try:
            analysis = _analyze(symbol=ticker, screener=screener, exchange=ex)
        except Exception as exc:  # rate limit / wrong exchange / network
            last_exc = exc
            # Back off only between retries; skip sleep after the last candidate.
            if attempt < len(candidates) - 1:
                time.sleep(_BACKOFF_BASE * (2 ** attempt))
            continue
        summary = analysis.summary or {}
        ind = analysis.indicators or {}
        return Technicals(
            ticker=ticker,
            exchange=ex,
            recommendation=summary.get("RECOMMENDATION", "NEUTRAL"),
            buy_signals=int(summary.get("BUY", 0)),
            neutral_signals=int(summary.get("NEUTRAL", 0)),
            sell_signals=int(summary.get("SELL", 0)),
            rsi=ind.get("RSI"),
            macd=ind.get("MACD.macd"),
            macd_signal=ind.get("MACD.signal"),
            close=ind.get("close"),
        )
    raise ToolError(
        "tradingview",
        f"all exchanges failed for {ticker} ({screener}): {last_exc}",
    )

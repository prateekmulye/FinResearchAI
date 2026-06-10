"""yfinance wrapper (yfinance==0.2.66).

fetch_fundamentals(ticker) -> Fundamentals. Reads `yf.Ticker(t).info` (a dict)
and maps the verified keys. Missing keys are tolerated (yfinance omits them per
ticker); an empty/unusable info dict or any SDK error surfaces as ToolError.
Blocking I/O — callers wrap with `await asyncio.to_thread(...)`.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass

from src.config.settings import get_settings
from src.tools import ToolError


@dataclass
class Fundamentals:
    ticker: str
    name: str | None
    sector: str | None
    trailing_pe: float | None
    forward_pe: float | None
    earnings_growth: float | None
    revenue_growth: float | None
    dividend_yield: float | None
    payout_ratio: float | None
    profit_margins: float | None
    gross_margins: float | None
    market_cap: float | None
    beta: float | None

    def to_dict(self) -> dict:
        return asdict(self)


def _ticker_info(ticker: str) -> dict:
    import yfinance as yf

    return yf.Ticker(ticker).info or {}


def fetch_fundamentals(ticker: str) -> Fundamentals:
    # APP_FAKE_LLM seam (WP-5): flag read at CALL time; canned deterministic data,
    # no network. Lazy import avoids a module cycle (fake_data imports Fundamentals).
    if get_settings().fake_llm:
        from src.tools.fake_data import fake_fundamentals

        return fake_fundamentals(ticker)
    try:
        info = _ticker_info(ticker)
    except Exception as exc:
        raise ToolError("yfinance", f"info fetch failed for {ticker}: {exc}") from exc

    # A valid ticker returns a rich dict; an unknown symbol returns {} or a
    # near-empty stub with no name/marketCap.  ETFs often have only shortName,
    # so we require all three to be None before rejecting.
    if not info or (
        info.get("longName") is None
        and info.get("shortName") is None
        and info.get("marketCap") is None
    ):
        raise ToolError("yfinance", f"no fundamentals for {ticker!r}")

    return Fundamentals(
        ticker=ticker,
        name=info.get("longName") or info.get("shortName"),
        sector=info.get("sector"),
        trailing_pe=info.get("trailingPE"),
        forward_pe=info.get("forwardPE"),
        earnings_growth=info.get("earningsQuarterlyGrowth"),
        revenue_growth=info.get("revenueGrowth"),
        dividend_yield=info.get("dividendYield"),
        payout_ratio=info.get("payoutRatio"),
        profit_margins=info.get("profitMargins"),
        gross_margins=info.get("grossMargins"),
        market_cap=info.get("marketCap"),
        beta=info.get("beta"),
    )

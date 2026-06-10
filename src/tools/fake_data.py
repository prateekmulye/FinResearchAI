"""Canned, deterministic market data for APP_FAKE_LLM demo mode (WP-5).

Seam choice (documented): each tool's PUBLIC fetcher checks ``settings.fake_llm``
AT CALL TIME and returns these instead of touching the network — one seam per
tool, inside the tool itself, so node call sites (and test monkeypatching of
the SDK-level helpers) stay untouched. ``src/warehouse/ingest._fetch_daily_bars``
applies the same seam for price-bar backfills.

Everything here is a pure function of the ticker (plus the date for OHLCV):
same inputs -> same outputs, and different tickers look visibly different.
"""
from __future__ import annotations

import hashlib
import math
from datetime import UTC, date, datetime, timedelta
from typing import Any

from src.tools.firecrawl import NewsHit
from src.tools.tradingview import Technicals
from src.tools.yfinance import Fundamentals


def _h(key: str) -> int:
    """Stable 64-bit hash (NOT Python's salted hash) for deterministic variation."""
    return int.from_bytes(hashlib.sha256(key.encode("utf-8")).digest()[:8], "big")


def base_price(ticker: str) -> float:
    return float(40 + _h(f"{ticker}:base") % 460)


def demo_score(ticker: str) -> int:
    """0-100 outlook score; >= 70 reads as BUY (AAPL-style demo tickers lean bullish)."""
    return 55 + _h(f"{ticker}:score") % 40


def news_url(ticker: str, i: int) -> str:
    return f"https://demo.finresearch.ai/news/{ticker.lower()}/{i}"


_SECTORS = (
    "Technology", "Consumer Cyclical", "Healthcare", "Financial Services",
    "Industrials", "Energy", "Communication Services",
)


def fake_fundamentals(ticker: str) -> Fundamentals:
    h = _h(f"{ticker}:fund")
    score = demo_score(ticker)
    return Fundamentals(
        ticker=ticker,
        name=f"{ticker.split('.')[0].title()} Corporation",
        sector=_SECTORS[h % len(_SECTORS)],
        trailing_pe=round(12 + (h >> 3) % 30 + score / 10, 1),
        forward_pe=round(10 + (h >> 5) % 26 + score / 12, 1),
        earnings_growth=round(((score - 50) / 200) + ((h >> 7) % 10) / 100, 3),
        revenue_growth=round(((score - 45) / 250) + ((h >> 9) % 8) / 100, 3),
        dividend_yield=round(((h >> 11) % 30) / 1000, 4),
        payout_ratio=round(((h >> 13) % 40) / 100, 2),
        profit_margins=round(0.08 + ((h >> 15) % 25) / 100, 3),
        gross_margins=round(0.30 + ((h >> 17) % 35) / 100, 3),
        market_cap=round(base_price(ticker) * (1 + (h >> 19) % 50) * 1e9, 0),
        beta=round(0.7 + ((h >> 21) % 90) / 100, 2),
    )


_NEWS_TEMPLATES: tuple[tuple[str, str], ...] = (
    ("{t} beats quarterly earnings estimates on resilient demand",
     "Revenue and EPS both topped consensus, with management citing strong execution."),
    ("{t} unveils next-generation product line at annual showcase",
     "Analysts called the launch an incremental but meaningful refresh of the portfolio."),
    ("Analysts lift price targets on {t} after upbeat guidance",
     "Several brokerages raised targets, pointing to margin expansion into year-end."),
    ("{t} faces regulatory scrutiny over market practices",
     "A regional regulator opened an inquiry; the company says it is cooperating fully."),
    ("{t} announces strategic partnership to expand cloud and AI offerings",
     "The multi-year deal broadens distribution and adds a recurring revenue stream."),
    ("{t} board approves expanded share buyback program",
     "The authorization signals confidence in cash generation, though some flag valuation."),
    ("Supply-chain pressures ease for {t}, lifting margin outlook",
     "Component costs and logistics normalized through the quarter, executives said."),
    ("Institutional investors raise stakes in {t}, filings show",
     "Quarterly filings revealed net accumulation by several large asset managers."),
)


def fake_news_hits(query: str, limit: int = 5) -> list[NewsHit]:
    """~8 plausible headlines for the ticker (first token of the query)."""
    ticker = (query.split() or ["DEMO"])[0].upper()
    start = _h(f"{ticker}:news") % len(_NEWS_TEMPLATES)
    hits: list[NewsHit] = []
    for i in range(min(max(limit, 0), len(_NEWS_TEMPLATES))):
        title_tpl, snippet = _NEWS_TEMPLATES[(start + i) % len(_NEWS_TEMPLATES)]
        hits.append(
            NewsHit(
                title=title_tpl.format(t=ticker),
                url=news_url(ticker, i),
                snippet=snippet,
                markdown=None,
            )
        )
    return hits


def fake_technicals(ticker: str, screener: str, exchange: str) -> Technicals:
    h = _h(f"{ticker}:ta")
    score = demo_score(ticker)
    rec = "BUY" if score >= 70 else "NEUTRAL" if score >= 60 else "SELL"
    buy = 8 + h % 9          # 8..16
    sell = 2 + (h >> 4) % 5  # 2..6
    if rec == "SELL":
        buy, sell = sell, buy
    macd = round((score - 60) / 25 + ((h >> 6) % 100) / 200, 3)
    return Technicals(
        ticker=ticker,
        exchange=exchange,
        recommendation=rec,
        buy_signals=buy,
        neutral_signals=26 - buy - sell,
        sell_signals=sell,
        rsi=round(35.0 + (score - 55) + (h >> 8) % 10, 1),
        macd=macd,
        macd_signal=round(macd - 0.2, 3),
        close=base_price(ticker),
    )


def _close_for(ticker: str, day: date) -> float:
    """Deterministic per-(ticker, date) close: slow drift + bounded daily jitter.

    Date-keyed (not a sequential walk) so the same calendar day always prices
    identically regardless of the requested window."""
    drift = 1 + 0.18 * math.sin(day.toordinal() / 37 + _h(f"{ticker}:phase") % 7)
    jitter = 1 + ((_h(f"{ticker}:{day.isoformat()}") % 2001) - 1000) / 25000  # +/-4%
    return round(base_price(ticker) * drift * jitter, 2)


def fake_daily_bars(ticker: str, start: datetime | None) -> list[dict[str, Any]]:
    """Business-day OHLCV bars from ``start`` (default: 365d ago) through today."""
    end = datetime.now(UTC).date()
    first = (start.date() if isinstance(start, datetime) else start) if start else None
    first = first or (end - timedelta(days=365))
    bars: list[dict[str, Any]] = []
    day = first
    while day <= end:
        if day.weekday() < 5:  # Mon-Fri
            close = _close_for(ticker, day)
            spread = 1 + ((_h(f"{ticker}:o:{day.isoformat()}") % 401) - 200) / 10000
            open_ = round(close * spread, 2)
            high = round(max(open_, close) * 1.012, 2)
            low = round(min(open_, close) * 0.988, 2)
            volume = 1_000_000 + _h(f"{ticker}:v:{day.isoformat()}") % 5_000_000
            bars.append(
                {
                    "ts": datetime(day.year, day.month, day.day, tzinfo=UTC),
                    "open": open_,
                    "high": high,
                    "low": low,
                    "close": close,
                    "volume": volume,
                }
            )
        day += timedelta(days=1)
    return bars

import os
from types import SimpleNamespace

import pytest

from src.tools import ToolError
from src.tools import tradingview as tv


def _fake_analysis():
    return SimpleNamespace(
        summary={"RECOMMENDATION": "BUY", "BUY": 12, "NEUTRAL": 9, "SELL": 7},
        oscillators={"RECOMMENDATION": "NEUTRAL"},
        moving_averages={"RECOMMENDATION": "BUY"},
        indicators={"RSI": 55.2, "MACD.macd": 2.4, "MACD.signal": 1.9, "close": 170.0},
    )


def test_fetch_technicals_maps_fields(monkeypatch):
    monkeypatch.setattr(tv, "_analyze", lambda **kw: _fake_analysis())
    t = tv.fetch_technicals("AAPL", screener="america", exchange="NASDAQ")
    assert t.recommendation == "BUY"
    assert t.rsi == 55.2
    assert t.macd == 2.4
    assert t.macd_signal == 1.9
    d = t.to_dict()
    assert d["buy_signals"] == 12
    assert d["sell_signals"] == 7


@pytest.mark.parametrize(
    ("ticker", "screener", "exchange", "expected_symbol"),
    [
        ("AAPL", "america", "NASDAQ", "AAPL"),        # US: untouched
        ("RELIANCE.NS", "india", "NSE", "RELIANCE"),  # NSE suffix stripped
        ("RELIANCE.BO", "india", "BSE", "RELIANCE"),  # BSE suffix stripped
        ("7203.T", "japan", "TSE", "7203"),           # TSE suffix stripped
        ("600519.SS", "china", "SSE", "600519"),      # SSE suffix stripped
        ("000001.SZ", "china", "SZSE", "000001"),     # SZSE: suffix stripped, zeros KEPT
        ("0700.HK", "hongkong", "HKEX", "700"),       # HK: suffix + leading zeros dropped
        ("0005.HK", "hongkong", "HKEX", "5"),
    ],
)
def test_fetch_technicals_strips_yfinance_suffix_for_ta_symbol(
    monkeypatch, ticker, screener, exchange, expected_symbol
):
    """tradingview_ta wants EXCHANGE:SYMBOL without the yfinance suffix (and HK
    symbols without leading zeros); the tool owns that munging."""
    captured = {}

    def _analyze(*, symbol, screener, exchange, **kw):
        captured["symbol"] = symbol
        return _fake_analysis()

    monkeypatch.setattr(tv, "_analyze", _analyze)
    t = tv.fetch_technicals(ticker, screener=screener, exchange=exchange)
    assert captured["symbol"] == expected_symbol
    # The caller-facing ticker is preserved un-munged in the result.
    assert t.ticker == ticker


def test_fetch_technicals_exchange_fallback(monkeypatch):
    calls = []

    def _analyze(*, symbol, screener, exchange, **kw):
        calls.append(exchange)
        if exchange == "NASDAQ":
            raise ValueError("symbol not found on NASDAQ")
        return _fake_analysis()

    monkeypatch.setattr(tv, "_analyze", _analyze)
    monkeypatch.setattr(tv, "_BACKOFF_BASE", 0.0)  # no real sleeping in tests
    t = tv.fetch_technicals("AAPL", screener="america", exchange="NASDAQ")
    assert t.recommendation == "BUY"
    assert "NASDAQ" in calls and "NYSE" in calls  # fell back to NYSE


def test_fetch_technicals_all_exchanges_fail_raises(monkeypatch):
    def _always_fail(**kw):
        raise ValueError("nope")

    monkeypatch.setattr(tv, "_analyze", _always_fail)
    monkeypatch.setattr(tv, "_BACKOFF_BASE", 0.0)
    with pytest.raises(ToolError) as ei:
        tv.fetch_technicals("AAPL", screener="america", exchange="NASDAQ")
    assert ei.value.tool == "tradingview"


@pytest.mark.live
@pytest.mark.skipif(os.getenv("RUN_LIVE") != "1", reason="set RUN_LIVE=1 for live API")
def test_fetch_technicals_live():
    t = tv.fetch_technicals("AAPL", screener="america", exchange="NASDAQ")
    assert t.recommendation in {"STRONG_BUY", "BUY", "NEUTRAL", "SELL", "STRONG_SELL"}

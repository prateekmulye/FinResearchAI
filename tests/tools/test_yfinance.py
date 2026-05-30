import os

import pytest

from src.tools import ToolError
from src.tools import yfinance as yfw


def test_fetch_fundamentals_maps_keys(monkeypatch):
    info = {
        "longName": "Apple Inc.",
        "sector": "Technology",
        "trailingPE": 28.0,
        "forwardPE": 25.0,
        "earningsQuarterlyGrowth": 0.1,
        "revenueGrowth": 0.05,
        "dividendYield": 0.0056,
        "payoutRatio": 0.15,
        "profitMargins": 0.25,
        "grossMargins": 0.44,
        "marketCap": 2_700_000_000_000,
        "beta": 1.2,
    }
    monkeypatch.setattr(yfw, "_ticker_info", lambda t: info)
    f = yfw.fetch_fundamentals("AAPL")
    assert f.name == "Apple Inc."
    assert f.trailing_pe == 28.0
    assert f.dividend_yield == 0.0056
    assert f.profit_margins == 0.25
    d = f.to_dict()
    assert d["forward_pe"] == 25.0
    assert d["sector"] == "Technology"


def test_fetch_fundamentals_tolerates_missing_keys(monkeypatch):
    monkeypatch.setattr(yfw, "_ticker_info", lambda t: {"longName": "X Corp"})
    f = yfw.fetch_fundamentals("X")
    assert f.name == "X Corp"
    assert f.trailing_pe is None
    assert f.market_cap is None


def test_fetch_fundamentals_empty_info_raises(monkeypatch):
    monkeypatch.setattr(yfw, "_ticker_info", lambda t: {})
    with pytest.raises(ToolError) as ei:
        yfw.fetch_fundamentals("BADTICKER")
    assert ei.value.tool == "yfinance"


def test_fetch_fundamentals_surfaces_sdk_error(monkeypatch):
    def _boom(t):
        raise ConnectionError("yahoo down")

    monkeypatch.setattr(yfw, "_ticker_info", _boom)
    with pytest.raises(ToolError):
        yfw.fetch_fundamentals("AAPL")


@pytest.mark.live
@pytest.mark.skipif(os.getenv("RUN_LIVE") != "1", reason="set RUN_LIVE=1 for live API")
def test_fetch_fundamentals_live():
    f = yfw.fetch_fundamentals("AAPL")
    assert f.name

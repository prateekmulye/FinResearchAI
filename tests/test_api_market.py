# tests/test_api_market.py
"""WP-5 read endpoints: /api/market/* (instruments, prices, fundamentals, news)
and /api/eval/results. Warehouse-backed via api_sqlite_warehouse; includes the
ticker-path hardening (junk -> 422) and warehouse-disabled (503) paths.
"""
from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest
from starlette.testclient import TestClient

from src.api.main import create_app
from src.warehouse.repos import (
    bulk_upsert_price_bars,
    insert_fundamentals,
    save_eval_result,
    upsert_instrument,
    upsert_news,
)

NOW = datetime.now(UTC)


def _seed_market(seed) -> None:
    async def _go(session):
        aapl = await upsert_instrument(
            session, ticker="AAPL", exchange="NASDAQ", screener="america",
            name="Apple Inc.", sector="Technology", watched=True,
        )
        await upsert_instrument(
            session, ticker="MSFT", exchange="NASDAQ", screener="america",
            name="Microsoft Corporation",
        )
        await bulk_upsert_price_bars(
            session, aapl.id,
            [
                {"ts": NOW - timedelta(days=d), "open": 100.0 + d, "high": 105.0 + d,
                 "low": 95.0 + d, "close": 102.0 + d, "volume": 1000 + d}
                for d in (400, 2, 1)
            ],
        )
        await insert_fundamentals(
            session, aapl.id, NOW - timedelta(days=2), pe_ratio=10.0, payload={"old": True}
        )
        await insert_fundamentals(
            session, aapl.id, NOW, market_cap=2.7e12, pe_ratio=28.0, eps=6.1,
            revenue_growth=0.05, profit_margin=0.25, payload={"beta": 1.2},
        )
        await upsert_news(
            session, aapl.id,
            [
                {"ts": NOW - timedelta(hours=h), "title": f"headline-{h}",
                 "url": f"https://news.example/{h}", "source": "wire",
                 "snippet": f"snippet {h}"}
                for h in (3, 1, 2)
            ],
        )

    seed(_go)


def _seed_dual_listing(seed) -> None:
    """Same ticker on two exchanges; the NSE listing has the newest bar."""

    async def _go(session):
        stale = await upsert_instrument(
            session, ticker="DUAL", exchange="BSE", screener="india"
        )
        fresh = await upsert_instrument(
            session, ticker="DUAL", exchange="NSE", screener="india"
        )
        await bulk_upsert_price_bars(
            session, stale.id,
            [{"ts": NOW - timedelta(days=30), "open": 1.0, "high": 1.0, "low": 1.0,
              "close": 111.0}],
        )
        await bulk_upsert_price_bars(
            session, fresh.id,
            [{"ts": NOW - timedelta(days=1), "open": 2.0, "high": 2.0, "low": 2.0,
              "close": 222.0}],
        )

    seed(_go)


# ------------------------------------------------------- /api/market/instruments


def test_instruments_search_matches_ticker_or_name(api_sqlite_warehouse):
    _seed_market(api_sqlite_warehouse)
    with TestClient(create_app()) as client:
        by_ticker = client.get("/api/market/instruments", params={"q": "aap"}).json()
        by_name = client.get("/api/market/instruments", params={"q": "micro"}).json()
        all_rows = client.get("/api/market/instruments").json()
    assert [i["ticker"] for i in by_ticker["instruments"]] == ["AAPL"]
    assert by_ticker["instruments"][0]["watched"] is True
    assert by_ticker["instruments"][0]["name"] == "Apple Inc."
    assert [i["ticker"] for i in by_name["instruments"]] == ["MSFT"]
    assert by_name["instruments"][0]["watched"] is False
    # empty q lists everything, ticker asc
    assert [i["ticker"] for i in all_rows["instruments"]] == ["AAPL", "MSFT"]


def test_instruments_search_empty_result_and_limit_clamp(api_sqlite_warehouse):
    _seed_market(api_sqlite_warehouse)
    with TestClient(create_app()) as client:
        none = client.get("/api/market/instruments", params={"q": "zzz"}).json()
        low = client.get("/api/market/instruments", params={"limit": 0}).json()
    assert none["instruments"] == []
    assert len(low["instruments"]) == 1  # clamped up to 1


# ---------------------------------------------------- /api/market/{ticker}/prices


def test_prices_returns_daily_bars_ascending_within_window(api_sqlite_warehouse):
    _seed_market(api_sqlite_warehouse)
    with TestClient(create_app()) as client:
        body = client.get("/api/market/AAPL/prices").json()
    assert body["ticker"] == "AAPL"
    assert body["exchange"] == "NASDAQ"
    bars = body["bars"]
    assert len(bars) == 2  # the 400-day-old bar is outside the default 365d window
    assert [b["ts"] for b in bars] == sorted(b["ts"] for b in bars)
    assert {"open", "high", "low", "close", "volume"} <= set(bars[0])


def test_prices_lowercase_ticker_normalized(api_sqlite_warehouse):
    _seed_market(api_sqlite_warehouse)
    with TestClient(create_app()) as client:
        assert client.get("/api/market/aapl/prices").json()["ticker"] == "AAPL"


def test_prices_404_for_unknown_ticker(api_sqlite_warehouse):
    _seed_market(api_sqlite_warehouse)
    with TestClient(create_app()) as client:
        assert client.get("/api/market/ZZZT/prices").status_code == 404


def test_prices_exchange_disambiguation(api_sqlite_warehouse):
    _seed_dual_listing(api_sqlite_warehouse)
    with TestClient(create_app()) as client:
        # ambiguous without exchange -> the listing with the newest bar (NSE)
        auto = client.get("/api/market/DUAL/prices").json()
        explicit = client.get("/api/market/DUAL/prices", params={"exchange": "BSE"}).json()
        unknown = client.get("/api/market/DUAL/prices", params={"exchange": "TSE"})
    assert auto["exchange"] == "NSE"
    assert auto["bars"][0]["close"] == 222.0
    assert explicit["exchange"] == "BSE"
    assert explicit["bars"][0]["close"] == 111.0
    assert unknown.status_code == 404


# ----------------------------------------------- /api/market/{ticker}/fundamentals


def test_fundamentals_returns_latest_snapshot(api_sqlite_warehouse):
    _seed_market(api_sqlite_warehouse)
    with TestClient(create_app()) as client:
        body = client.get("/api/market/AAPL/fundamentals").json()
    assert body["ticker"] == "AAPL"
    assert body["pe_ratio"] == 28.0
    assert body["market_cap"] == 2.7e12
    assert body["payload"] == {"beta": 1.2}  # the NEWEST snapshot, not the old one
    assert body["ts"]


def test_fundamentals_404_when_none_stored(api_sqlite_warehouse):
    _seed_market(api_sqlite_warehouse)
    with TestClient(create_app()) as client:
        # MSFT exists but has no fundamentals snapshot
        assert client.get("/api/market/MSFT/fundamentals").status_code == 404
        assert client.get("/api/market/ZZZT/fundamentals").status_code == 404


# ----------------------------------------------------- /api/market/{ticker}/news


def test_news_newest_first_with_limit(api_sqlite_warehouse):
    _seed_market(api_sqlite_warehouse)
    with TestClient(create_app()) as client:
        body = client.get("/api/market/AAPL/news").json()
        limited = client.get("/api/market/AAPL/news", params={"limit": 2}).json()
    assert [n["title"] for n in body["items"]] == ["headline-1", "headline-2", "headline-3"]
    assert body["items"][0]["url"] == "https://news.example/1"
    assert [n["title"] for n in limited["items"]] == ["headline-1", "headline-2"]


def test_news_404_for_unknown_ticker_and_empty_for_known(api_sqlite_warehouse):
    _seed_market(api_sqlite_warehouse)
    with TestClient(create_app()) as client:
        assert client.get("/api/market/ZZZT/news").status_code == 404
        body = client.get("/api/market/MSFT/news").json()
    assert body["items"] == []


# -------------------------------------------------------------- ticker hardening


@pytest.mark.parametrize(
    "junk",
    [
        "..etc",               # traversal-ish (dots are only allowed mid-ticker)
        "AAPL; DROP",          # injection-ish
        "\U0001f680",          # emoji
        "A" * 30,              # too long
        "-AAPL",               # must start alphanumeric
    ],
)
def test_market_routes_reject_junk_tickers_with_422(api_sqlite_warehouse, junk):
    with TestClient(create_app()) as client:
        for path in ("prices", "fundamentals", "news"):
            assert client.get(f"/api/market/{junk}/{path}").status_code == 422


# ------------------------------------------------------------- warehouse disabled


def test_market_routes_503_when_warehouse_disabled():
    with TestClient(create_app()) as client:
        for path in (
            "/api/market/instruments",
            "/api/market/AAPL/prices",
            "/api/market/AAPL/fundamentals",
            "/api/market/AAPL/news",
        ):
            resp = client.get(path)
            assert resp.status_code == 503, path
            assert resp.json()["detail"] == "warehouse disabled"


# ------------------------------------------------------------- /api/eval/results


def test_eval_results_newest_first(api_sqlite_warehouse):
    async def _go(session):
        await save_eval_result(session, "old", {"n": 1}, [{"ticker": "AAPL"}])
        await save_eval_result(session, "new", {"n": 2}, [{"ticker": "MSFT"}])

    api_sqlite_warehouse(_go)
    with TestClient(create_app()) as client:
        body = client.get("/api/eval/results").json()
        limited = client.get("/api/eval/results", params={"limit": 1}).json()
    assert [r["label"] for r in body["results"]] == ["new", "old"]
    assert body["results"][0]["summary"] == {"n": 2}
    assert body["results"][0]["pairs"] == [{"ticker": "MSFT"}]
    assert body["results"][0]["created_at"]
    assert [r["label"] for r in limited["results"]] == ["new"]


def test_eval_results_empty_when_no_rows_stored(api_sqlite_warehouse):
    with TestClient(create_app()) as client:
        assert client.get("/api/eval/results").json() == {"results": []}


def test_eval_results_serves_record_eval_result_rows(api_sqlite_warehouse):
    """WP-10 end-to-end seam: a row persisted through the ingest write path
    (what src.eval.run calls) comes back through GET /api/eval/results with the
    full dashboard payload — label, created_at, summary, untruncated pairs."""
    import asyncio

    from src.warehouse.db import reset_engine
    from src.warehouse.ingest import record_eval_result

    summary = {"n_tickers": 1, "judge_prefers_on_rate": 1.0}
    rows = [
        {"ticker": "AAPL", "action_on": "BUY", "action_off": "HOLD",
         "score_on": 80, "score_off": 55, "cost_on": 0.06, "cost_off": 0.02,
         "latency_on": 4.0, "latency_off": 1.5, "tokens_on": 150, "tokens_off": 60,
         "judge_preferred": "on", "judge_agreement": False, "judge_confidence": 0.7},
    ]

    async def _persist() -> None:
        # Ingest memoizes an engine on THIS loop; reset before TestClient's
        # lifespan creates its own (AsyncEngine has event-loop affinity).
        assert await record_eval_result("wp10-e2e", summary, rows) is True
        await reset_engine()

    asyncio.run(_persist())
    with TestClient(create_app()) as client:
        body = client.get("/api/eval/results").json()
    (result,) = body["results"]
    assert result["label"] == "wp10-e2e"
    assert result["summary"] == summary
    assert result["pairs"] == rows
    assert result["created_at"]
    assert result["id"]


def test_eval_results_503_when_warehouse_disabled():
    with TestClient(create_app()) as client:
        resp = client.get("/api/eval/results")
    assert resp.status_code == 503
    assert resp.json()["detail"] == "warehouse disabled"

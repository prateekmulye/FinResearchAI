# tests/test_api_search.py
"""WP-9 GET /api/search: keyword mode on SQLite, the semantic path (stubbed —
the live pgvector cosine path is tests/warehouse/test_pg_integration.py, marker
db), honest mode fallbacks, query validation, and warehouse-disabled 503.
"""
from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest
from starlette.testclient import TestClient

import src.api.routes.search as search_routes
from src.api.main import create_app
from src.warehouse.repos import SearchHit, create_run, finish_run, upsert_instrument, upsert_news

NOW = datetime.now(UTC)


def _seed_search(seed) -> None:
    async def _go(session):
        aapl = await upsert_instrument(
            session, ticker="AAPL", exchange="NASDAQ", screener="america"
        )
        await upsert_news(
            session, aapl.id,
            [
                {"ts": NOW - timedelta(hours=2), "title": "Apple margin expansion",
                 "url": "https://n.example/a1", "snippet": "services growth"},
                {"ts": NOW - timedelta(hours=1), "title": "iPhone demand steady",
                 "url": "https://n.example/a2", "snippet": "margin pressure easing"},
            ],
        )
        await create_run(session, "run-aapl", "AAPL", "on")
        await finish_run(
            session, "run-aapl", status="finished",
            final_decision={"action": "BUY", "rationale": "margin upside"},
            report="Deep dive on AAPL margin drivers.",
        )

    seed(_go)


# -------------------------------------------------------------- keyword mode


def test_search_keyword_mode_on_sqlite(api_sqlite_warehouse):
    _seed_search(api_sqlite_warehouse)
    with TestClient(create_app()) as client:
        body = client.get("/api/search", params={"q": "margin"}).json()
    assert body["mode"] == "keyword"
    refs = [h["ref"] for h in body["hits"]]
    assert "https://n.example/a1" in refs
    assert "https://n.example/a2" in refs
    assert "run-aapl" in refs
    news_hit = next(h for h in body["hits"] if h["ref"] == "https://n.example/a2")
    assert news_hit == {
        "kind": "news",
        "ref": "https://n.example/a2",
        "ticker": "AAPL",
        "title": "iPhone demand steady",
        "snippet": "margin pressure easing",
        "score": None,
        "ts": news_hit["ts"],
    }
    assert news_hit["ts"]
    run_hit = next(h for h in body["hits"] if h["ref"] == "run-aapl")
    assert run_hit["kind"] == "run"
    assert run_hit["ticker"] == "AAPL"
    assert run_hit["title"] == "AAPL run — BUY"
    assert run_hit["score"] is None


def test_search_limit_applies_and_clamps(api_sqlite_warehouse):
    _seed_search(api_sqlite_warehouse)
    with TestClient(create_app()) as client:
        limited = client.get("/api/search", params={"q": "margin", "limit": 1}).json()
        clamped = client.get("/api/search", params={"q": "margin", "limit": 0}).json()
    assert len(limited["hits"]) == 1
    assert len(clamped["hits"]) == 1  # clamped up to 1


def test_search_no_match_is_empty_keyword(api_sqlite_warehouse):
    _seed_search(api_sqlite_warehouse)
    with TestClient(create_app()) as client:
        body = client.get("/api/search", params={"q": "zzz-no-such"}).json()
    assert body == {"mode": "keyword", "hits": []}


# ------------------------------------------------------------ query hardening


@pytest.mark.parametrize("bad_q", ["", " ", "a", " a ", "x" * 257])
def test_search_rejects_blank_short_or_oversized_q(api_sqlite_warehouse, bad_q):
    with TestClient(create_app()) as client:
        assert client.get("/api/search", params={"q": bad_q}).status_code == 422


def test_search_missing_q_param_rejected(api_sqlite_warehouse):
    with TestClient(create_app()) as client:
        assert client.get("/api/search").status_code == 422


def test_search_503_when_warehouse_disabled():
    with TestClient(create_app()) as client:
        resp = client.get("/api/search", params={"q": "margin"})
    assert resp.status_code == 503
    assert resp.json()["detail"] == "warehouse disabled"


# -------------------------------------------------------------- semantic path


def test_search_semantic_mode_with_stubbed_repo(
    api_sqlite_warehouse, warehouse_fake_embedder, monkeypatch
):
    _seed_search(api_sqlite_warehouse)
    captured: dict = {}

    async def _fake_semantic(session, query_vec, *, limit=20):
        captured["query_vec"] = query_vec
        captured["limit"] = limit
        return [
            SearchHit(kind="news", ref="https://n.example/a1", ticker="AAPL",
                      title="Apple margin expansion", snippet="services growth",
                      score=0.12, ts=NOW - timedelta(hours=2)),
            SearchHit(kind="run", ref="run-aapl", ticker="AAPL",
                      title="AAPL run — BUY", snippet="Deep dive",
                      score=0.34, ts=NOW - timedelta(minutes=5)),
        ]

    monkeypatch.setattr(search_routes, "_semantic_eligible", lambda: True)
    monkeypatch.setattr(search_routes, "semantic_search", _fake_semantic)
    with TestClient(create_app()) as client:
        body = client.get("/api/search", params={"q": "margin expansion"}).json()
    assert body["mode"] == "semantic"
    assert [h["ref"] for h in body["hits"]] == ["https://n.example/a1", "run-aapl"]
    assert body["hits"][0]["score"] == 0.12
    # The query embedding came from the seam (deterministic fake) at full dim.
    assert captured["query_vec"] == warehouse_fake_embedder.vector("margin expansion")
    assert captured["limit"] == 20


def test_search_falls_back_to_keyword_when_embedder_unavailable(
    api_sqlite_warehouse, monkeypatch
):
    # autouse no_real_embedder pins the seam to None: semantic-eligible dialect
    # but no embedder -> honest "keyword" mode.
    _seed_search(api_sqlite_warehouse)
    monkeypatch.setattr(search_routes, "_semantic_eligible", lambda: True)
    with TestClient(create_app()) as client:
        body = client.get("/api/search", params={"q": "margin"}).json()
    assert body["mode"] == "keyword"
    assert body["hits"]


def test_search_falls_back_on_unsupported_dialect(
    api_sqlite_warehouse, warehouse_fake_embedder, monkeypatch
):
    # Embedder available + eligibility forced True, but the REAL semantic_search
    # raises UnsupportedDialectError on sqlite -> keyword fallback, mode honest.
    _seed_search(api_sqlite_warehouse)
    monkeypatch.setattr(search_routes, "_semantic_eligible", lambda: True)
    with TestClient(create_app()) as client:
        body = client.get("/api/search", params={"q": "margin"}).json()
    assert body["mode"] == "keyword"
    assert "run-aapl" in [h["ref"] for h in body["hits"]]


def test_search_falls_back_to_keyword_on_semantic_failure(
    api_sqlite_warehouse, warehouse_fake_embedder, monkeypatch
):
    # A transient failure INSIDE the semantic path (DB hiccup, driver error)
    # must degrade to keyword with mode honest — never a 500.
    _seed_search(api_sqlite_warehouse)

    async def _boom(session, query_vec, *, limit=20):
        raise RuntimeError("transient db error")

    monkeypatch.setattr(search_routes, "_semantic_eligible", lambda: True)
    monkeypatch.setattr(search_routes, "semantic_search", _boom)
    with TestClient(create_app()) as client:
        resp = client.get("/api/search", params={"q": "margin"})
    assert resp.status_code == 200
    body = resp.json()
    assert body["mode"] == "keyword"
    assert "run-aapl" in [h["ref"] for h in body["hits"]]

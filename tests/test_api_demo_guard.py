# tests/test_api_demo_guard.py
"""WP-5 demo guard: daily per-IP/global live-run caps on POST /api/analyze,
layered ON TOP of the per-hour burst limiter, with an X-Admin-Token bypass for
BOTH, plus the GET /api/quota status endpoint.

Design under test (see src/api/demo_guard.py): increment-FIRST for the IP
counter — it is consumed atomically before the limit check, so an over-limit
attempt still counts (race-proof; no check-then-increment window). The GLOBAL
counter is only incremented when the IP counter is within its limit, so one
hammering IP cannot drain the shared global pool.
"""
from __future__ import annotations

import logging
from datetime import UTC, datetime

import pytest
from starlette.testclient import TestClient

from src.api.main import create_app
from src.config import settings as settings_mod

BODY = {"ticker": "AAPL", "investor_mode": "Neutral"}


@pytest.fixture
def no_price_backfill(monkeypatch):
    """Warehouse enabled -> prices_stale() is True and refresh_prices would hit
    yfinance; patch it to an offline no-op (same pattern as test_api_stream)."""
    import src.agents.analysts.fundamentals as fund_mod

    async def _noop(*args, **kwargs):
        return 0

    monkeypatch.setattr(fund_mod, "refresh_prices", _noop)


@pytest.fixture
def guarded_app(offline_graph, api_sqlite_warehouse, no_price_backfill, monkeypatch):
    """App factory with warehouse-backed demo guard; returns (make_client, seed)."""

    def make_client(*, ip_cap=None, global_cap=None, admin_token=None, rate_limit=100):
        if ip_cap is not None:
            monkeypatch.setenv("DEMO_RUNS_PER_IP_PER_DAY", str(ip_cap))
        if global_cap is not None:
            monkeypatch.setenv("DEMO_RUNS_GLOBAL_PER_DAY", str(global_cap))
        if admin_token is not None:
            monkeypatch.setenv("ADMIN_TOKEN", admin_token)
        settings_mod.get_settings.cache_clear()
        return TestClient(create_app(rate_limit=rate_limit))

    return make_client, api_sqlite_warehouse


def _quota_rows(seed):
    async def _go(session):
        from sqlalchemy import select

        from src.warehouse.models import DemoQuota

        rows = (await session.execute(select(DemoQuota))).scalars().all()
        return [(r.key, r.day, r.count) for r in rows]

    return seed(_go)


# ----------------------------------------------------------------- daily caps


def test_under_limit_runs_succeed(guarded_app):
    make_client, _ = guarded_app
    with make_client(ip_cap=2) as client:
        assert client.post("/api/analyze", json=BODY).status_code == 200
        assert client.post("/api/analyze", json=BODY).status_code == 200


def test_ip_cap_429_with_scope_ip(guarded_app):
    make_client, _ = guarded_app
    with make_client(ip_cap=1, global_cap=100) as client:
        assert client.post("/api/analyze", json=BODY).status_code == 200
        resp = client.post("/api/analyze", json=BODY)
    assert resp.status_code == 429
    assert resp.json() == {
        "detail": "daily live-run limit reached", "scope": "ip", "limit": 1,
    }


def test_global_cap_429_with_scope_global(guarded_app):
    make_client, _ = guarded_app
    with make_client(ip_cap=100, global_cap=1) as client:
        assert client.post("/api/analyze", json=BODY).status_code == 200
        resp = client.post("/api/analyze", json=BODY)
    assert resp.status_code == 429
    assert resp.json() == {
        "detail": "daily live-run limit reached", "scope": "global", "limit": 1,
    }


def test_quota_keys_are_per_ip_and_utc_day(guarded_app):
    make_client, seed = guarded_app
    with make_client(ip_cap=5) as client:
        client.post("/api/analyze", json=BODY)
    rows = dict((key, (day, count)) for key, day, count in _quota_rows(seed))
    today = datetime.now(UTC).date()
    assert rows["ip:testclient"] == (today, 1)
    assert rows["global"] == (today, 1)


def test_over_limit_attempt_still_consumes_quota(guarded_app):
    # Increment-first: the 429'd attempt itself counted against the IP
    # (documented choice) — but NOT against the shared global pool.
    make_client, seed = guarded_app
    with make_client(ip_cap=1) as client:
        client.post("/api/analyze", json=BODY)
        client.post("/api/analyze", json=BODY)  # 429, but still incremented
    rows = {key: count for key, _, count in _quota_rows(seed)}
    assert rows["ip:testclient"] == 2
    assert rows["global"] == 1  # only the admitted run touched the global pool


def test_over_ip_cap_attempts_do_not_drain_global_pool(guarded_app):
    # Hammering one IP past its cap must not consume the shared global quota.
    make_client, seed = guarded_app
    with make_client(ip_cap=1, global_cap=100) as client:
        assert client.post("/api/analyze", json=BODY).status_code == 200
        for _ in range(4):
            resp = client.post("/api/analyze", json=BODY)
            assert resp.status_code == 429
            assert resp.json()["scope"] == "ip"
    rows = {key: count for key, _, count in _quota_rows(seed)}
    assert rows["ip:testclient"] == 5  # every attempt burned the IP counter
    assert rows["global"] == 1  # global pool untouched after the cap


def test_within_limit_requests_increment_both_counters(guarded_app):
    # Admitted runs consume IP and global atomically in one transaction.
    make_client, seed = guarded_app
    with make_client(ip_cap=5, global_cap=5) as client:
        assert client.post("/api/analyze", json=BODY).status_code == 200
        assert client.post("/api/analyze", json=BODY).status_code == 200
    rows = {key: count for key, _, count in _quota_rows(seed)}
    assert rows["ip:testclient"] == 2
    assert rows["global"] == 2


def test_invalid_body_does_not_consume_quota(guarded_app):
    # The guard declares the body, so a 422 fires before any increment.
    make_client, seed = guarded_app
    with make_client(ip_cap=5) as client:
        assert client.post("/api/analyze", json={"ticker": "; DROP"}).status_code == 422
    assert _quota_rows(seed) == []


# --------------------------------------------------------------- admin bypass


def test_admin_token_bypasses_daily_caps_and_minute_limiter(guarded_app):
    make_client, seed = guarded_app
    # rate_limit=0: the per-hour burst limiter rejects EVERYTHING without the bypass.
    with make_client(ip_cap=0, global_cap=0, admin_token="s3cr3t", rate_limit=0) as client:
        denied = client.post("/api/analyze", json=BODY)
        allowed = client.post(
            "/api/analyze", json=BODY, headers={"X-Admin-Token": "s3cr3t"}
        )
        again = client.post(
            "/api/analyze", json=BODY, headers={"X-Admin-Token": "s3cr3t"}
        )
    assert denied.status_code == 429
    assert allowed.status_code == 200
    assert again.status_code == 200
    assert _quota_rows(seed) == []  # admin runs never touch the quota table


def test_bad_admin_token_is_not_a_bypass(guarded_app):
    make_client, _ = guarded_app
    with make_client(ip_cap=0, admin_token="s3cr3t") as client:
        resp = client.post(
            "/api/analyze", json=BODY, headers={"X-Admin-Token": "wrong"}
        )
    assert resp.status_code == 429


def test_admin_header_without_configured_token_is_not_a_bypass(guarded_app):
    # No ADMIN_TOKEN configured (empty/None) -> no bypass possible.
    make_client, _ = guarded_app
    with make_client(ip_cap=0) as client:
        resp = client.post(
            "/api/analyze", json=BODY, headers={"X-Admin-Token": ""}
        )
    assert resp.status_code == 429


def test_non_ascii_admin_token_header_is_not_admin_and_not_500(guarded_app):
    # secrets.compare_digest raises TypeError on non-ASCII str; the guard must
    # compare UTF-8 bytes so a "£" header is just a failed match (quota applies),
    # never a 500.
    make_client, _ = guarded_app
    with make_client(ip_cap=0, admin_token="s3cr3t") as client:
        resp = client.post(
            "/api/analyze", json=BODY,
            headers={"X-Admin-Token": "£".encode("utf-8")},
        )
    assert resp.status_code == 429  # treated as non-admin -> daily cap applies


# ------------------------------------------------------------------- fail open


def test_guard_fails_open_when_quota_db_is_broken(guarded_app, monkeypatch, caplog):
    # Warehouse enabled but the sessionmaker is dead (same DB-error pattern as
    # tests/test_cache.py): the guard must log a warning and ADMIT the request —
    # a quota outage must never take down live demos.
    from src.warehouse import db as db_mod

    make_client, seed = guarded_app
    with make_client(ip_cap=0, global_cap=0) as client:  # caps would reject everything
        def _boom():
            raise RuntimeError("db down")

        monkeypatch.setattr(db_mod, "get_sessionmaker", _boom)
        with caplog.at_level(logging.WARNING, logger="src.api.demo_guard"):
            resp = client.post("/api/analyze", json=BODY)
    assert resp.status_code == 200  # admitted: no 429/500 from the guard
    assert "failing open" in caplog.text


# -------------------------------------------------------- warehouse disabled


def test_guard_noops_when_warehouse_disabled(offline_graph, monkeypatch):
    # env_isolation scrubs DATABASE_URL; only the per-hour burst limiter applies.
    monkeypatch.setenv("DEMO_RUNS_PER_IP_PER_DAY", "0")
    settings_mod.get_settings.cache_clear()
    with TestClient(create_app(rate_limit=2)) as client:
        assert client.post("/api/analyze", json=BODY).status_code == 200
        assert client.post("/api/analyze", json=BODY).status_code == 200
        assert client.post("/api/analyze", json=BODY).status_code == 429  # burst limiter


# ------------------------------------------------------------------ /api/quota


def test_quota_endpoint_reflects_usage(guarded_app):
    make_client, _ = guarded_app
    with make_client(ip_cap=3, global_cap=25) as client:
        before = client.get("/api/quota").json()
        client.post("/api/analyze", json=BODY)
        after = client.get("/api/quota").json()
    assert before == {
        "metered": True, "degraded": False,
        "ip_used": 0, "ip_limit": 3, "global_used": 0, "global_limit": 25,
        "admin": False,
    }
    assert after["ip_used"] == 1
    assert after["global_used"] == 1


def test_quota_endpoint_reports_admin_flag(guarded_app):
    make_client, _ = guarded_app
    with make_client(admin_token="s3cr3t") as client:
        anon = client.get("/api/quota").json()
        admin = client.get("/api/quota", headers={"X-Admin-Token": "s3cr3t"}).json()
        wrong = client.get("/api/quota", headers={"X-Admin-Token": "nope"}).json()
    assert anon["admin"] is False
    assert admin["admin"] is True
    assert wrong["admin"] is False


def test_quota_endpoint_unmetered_when_warehouse_disabled(monkeypatch):
    # No quota system is NOT an outage: the UI must be able to distinguish
    # "unmetered" (200, metered=false) from a real failure. Admin detection
    # still works without the warehouse.
    monkeypatch.setenv("ADMIN_TOKEN", "s3cr3t")
    settings_mod.get_settings.cache_clear()
    with TestClient(create_app()) as client:
        anon = client.get("/api/quota")
        admin = client.get("/api/quota", headers={"X-Admin-Token": "s3cr3t"})
    assert anon.status_code == 200
    assert anon.json() == {
        "metered": False, "degraded": False,
        "ip_used": None, "ip_limit": None, "global_used": None, "global_limit": None,
        "admin": False,
    }
    assert admin.json()["metered"] is False
    assert admin.json()["admin"] is True


def test_quota_endpoint_degrades_to_200_on_db_outage(guarded_app, monkeypatch, caplog):
    # A DB outage is NOT "unmetered": respond 200 with metered=true,
    # degraded=true and null counters (never a 500) so the UI can tell
    # "quota system down" apart from "no quota system at all".
    from src.warehouse import db as db_mod

    make_client, _ = guarded_app
    with make_client(admin_token="s3cr3t") as client:
        def _boom():
            raise RuntimeError("db down")

        monkeypatch.setattr(db_mod, "get_sessionmaker", _boom)
        with caplog.at_level(logging.WARNING, logger="src.api.routes.quota"):
            anon = client.get("/api/quota")
            admin = client.get("/api/quota", headers={"X-Admin-Token": "s3cr3t"})
    assert anon.status_code == 200
    assert anon.json() == {
        "metered": True, "degraded": True,
        "ip_used": None, "ip_limit": None, "global_used": None, "global_limit": None,
        "admin": False,
    }
    assert admin.json()["degraded"] is True
    assert admin.json()["admin"] is True  # admin detection survives the outage
    assert "degrad" in caplog.text

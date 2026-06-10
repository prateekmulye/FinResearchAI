# tests/test_api_library.py
"""WP-5 read endpoints: GET /api/library and GET /api/runs/{run_id}.

Warehouse-backed via the TestClient-safe ``api_sqlite_warehouse`` fixture;
the JSONL fallback and warehouse-disabled (503) paths are covered too.
"""
from __future__ import annotations

from datetime import UTC, datetime

from starlette.testclient import TestClient

from src.api.main import create_app
from src.warehouse.repos import bulk_append_run_events, create_run, finish_run

_METRICS = [
    {"node": "router", "model": "m", "prompt_tokens": 10, "completion_tokens": 5,
     "latency_s": 1.5, "cost_usd": 0.01},
    {"node": "reporter", "model": "m", "prompt_tokens": 20, "completion_tokens": 15,
     "latency_s": 2.5, "cost_usd": 0.02},
]

_EVENTS = [
    {"seq": 0, "event": {"name": "start", "data": {"type": "start", "run_id": "run-aaa"},
                         "ts_ms": 1000}},
    {"seq": 1, "event": {"name": "done", "data": {"type": "done", "run_id": "run-aaa"},
                         "ts_ms": 2000}},
]


def _seed_two_runs(seed) -> None:
    async def _go(session):
        r1 = await create_run(session, "run-aaa", "AAPL", "on")
        await finish_run(
            session, "run-aaa", status="finished",
            final_decision={"action": "BUY", "conviction": 0.8, "score": 80, "rationale": "x"},
            report="# AAPL report", metrics=_METRICS,
        )
        await bulk_append_run_events(session, "run-aaa", _EVENTS)
        r2 = await create_run(session, "run-bbb", "MSFT", "off")
        r1.started_at = datetime(2026, 6, 1, tzinfo=UTC)
        r2.started_at = datetime(2026, 6, 2, tzinfo=UTC)
        await session.flush()

    seed(_go)


# ------------------------------------------------------------------ /api/library


def test_library_lists_runs_newest_first_with_total(api_sqlite_warehouse):
    _seed_two_runs(api_sqlite_warehouse)
    with TestClient(create_app()) as client:
        body = client.get("/api/library").json()
    assert body["total"] == 2
    assert [r["run_id"] for r in body["runs"]] == ["run-bbb", "run-aaa"]
    finished = body["runs"][1]
    assert finished["ticker"] == "AAPL"
    assert finished["debate_mode"] == "on"
    assert finished["status"] == "finished"
    assert finished["started_at"] and finished["finished_at"]
    assert finished["final_decision"]["action"] == "BUY"
    # cost summary derived from the stored per-node metrics
    assert finished["cost"]["cost_usd"] == 0.03
    assert finished["cost"]["latency_s"] == 4.0
    assert finished["cost"]["total_tokens"] == 50
    # the unfinished run has no metrics -> no cost summary
    assert body["runs"][0]["cost"] is None


def test_library_filters_by_ticker_and_status(api_sqlite_warehouse):
    _seed_two_runs(api_sqlite_warehouse)
    with TestClient(create_app()) as client:
        by_ticker = client.get("/api/library", params={"ticker": "aapl"}).json()
        by_status = client.get("/api/library", params={"status": "running"}).json()
        none = client.get("/api/library", params={"ticker": "AAPL", "status": "running"}).json()
    assert [r["run_id"] for r in by_ticker["runs"]] == ["run-aaa"]
    assert by_ticker["total"] == 1
    assert [r["run_id"] for r in by_status["runs"]] == ["run-bbb"]
    assert none["runs"] == [] and none["total"] == 0


def test_library_rejects_unknown_status_with_422(api_sqlite_warehouse):
    with TestClient(create_app()) as client:
        assert client.get("/api/library", params={"status": "bogus"}).status_code == 422


def test_library_empty_warehouse_returns_empty_list(api_sqlite_warehouse):
    with TestClient(create_app()) as client:
        body = client.get("/api/library").json()
    assert body == {"runs": [], "total": 0}


def test_library_clamps_limit_into_1_100(api_sqlite_warehouse):
    _seed_two_runs(api_sqlite_warehouse)
    with TestClient(create_app()) as client:
        low = client.get("/api/library", params={"limit": 0}).json()
        high = client.get("/api/library", params={"limit": 100000}).json()
        offset = client.get("/api/library", params={"limit": 1, "offset": 1}).json()
    assert len(low["runs"]) == 1 and low["total"] == 2  # clamped up to 1
    assert len(high["runs"]) == 2  # clamped down to 100 (only 2 exist)
    assert [r["run_id"] for r in offset["runs"]] == ["run-aaa"]


def test_library_503_when_warehouse_disabled():
    # env_isolation scrubs DATABASE_URL -> warehouse disabled.
    with TestClient(create_app()) as client:
        resp = client.get("/api/library")
    assert resp.status_code == 503
    assert resp.json()["detail"] == "warehouse disabled"


# -------------------------------------------------------------- /api/runs/{id}


def test_run_detail_returns_full_run_with_ordered_events(api_sqlite_warehouse):
    _seed_two_runs(api_sqlite_warehouse)
    with TestClient(create_app()) as client:
        body = client.get("/api/runs/run-aaa").json()
    assert body["run_id"] == "run-aaa"
    assert body["source"] == "warehouse"
    assert body["ticker"] == "AAPL"
    assert body["status"] == "finished"
    assert body["report"] == "# AAPL report"
    assert body["final_decision"]["action"] == "BUY"
    assert body["metrics"] == _METRICS
    # replay payload: ordered run_events with name/data/ts_ms
    assert [e["name"] for e in body["events"]] == ["start", "done"]
    assert [e["ts_ms"] for e in body["events"]] == [1000, 2000]
    assert body["events"][0]["data"]["type"] == "start"


def test_run_detail_falls_back_to_jsonl_when_not_in_db(api_sqlite_warehouse, tmp_path):
    from src.obs.recorder import RunRecorder

    rec = RunRecorder(runs_dir=str(tmp_path))
    rec.record("router", "node_complete", {"resolved_ticker": "AAPL"})
    rec.flush()
    with TestClient(create_app(runs_dir=str(tmp_path))) as client:
        body = client.get(f"/api/runs/{rec.run_id}").json()
    assert body["run_id"] == rec.run_id
    assert body["source"] == "jsonl"
    assert body["events"][0]["node"] == "router"


def test_run_detail_404_when_neither_source_knows_it(api_sqlite_warehouse, tmp_path):
    with TestClient(create_app(runs_dir=str(tmp_path))) as client:
        assert client.get("/api/runs/ghost-run").status_code == 404

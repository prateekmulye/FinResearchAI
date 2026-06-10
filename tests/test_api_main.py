from starlette.testclient import TestClient

from src.api.main import create_app


def test_healthz_stays_at_root():
    with TestClient(create_app()) as client:
        resp = client.get("/healthz")
        assert resp.status_code == 200
        assert resp.json()["status"] == "ok"


def test_analyze_streams_events_ending_in_done(offline_graph, parse_sse):
    with TestClient(create_app()) as client:
        resp = client.post("/api/analyze", json={"ticker": "AAPL", "investor_mode": "Neutral"})
        assert resp.status_code == 200
        assert resp.headers["content-type"].startswith("text/event-stream")
        events = parse_sse(resp.text)
        names = [e[0] for e in events]
        assert names[0] == "start"
        assert names[-1] == "done"
        assert "node_complete" in names
        done = events[-1][1]
        assert done["final_decision"]["action"] in {"BUY", "SELL", "HOLD"}


def test_analyze_rejects_bad_ticker_with_422():
    with TestClient(create_app()) as client:
        for junk in ("; DROP TABLE--", "../etc", "\U0001f680", "A" * 30):
            resp = client.post("/api/analyze", json={"ticker": junk})
            assert resp.status_code == 422, junk


def test_analyze_rejects_bad_enum_fields_with_422():
    with TestClient(create_app()) as client:
        assert (
            client.post(
                "/api/analyze", json={"ticker": "AAPL", "debate_mode": "maybe"}
            ).status_code
            == 422
        )
        assert (
            client.post(
                "/api/analyze", json={"ticker": "AAPL", "investor_mode": "YOLO"}
            ).status_code
            == 422
        )


def test_rate_limit_returns_429_after_cap(offline_graph):
    # cap of 2 requests for the test app
    with TestClient(create_app(rate_limit=2, rate_window_s=3600)) as client:
        body = {"ticker": "AAPL"}
        assert client.post("/api/analyze", json=body).status_code == 200
        assert client.post("/api/analyze", json=body).status_code == 200
        resp = client.post("/api/analyze", json=body)
        assert resp.status_code == 429


def test_runs_endpoint_reads_jsonl_trace_when_warehouse_disabled(tmp_path, monkeypatch):
    # Warehouse disabled (env_isolation scrubs DATABASE_URL): /api/runs/{id}
    # falls back to the JSONL trace RunRecorder wrote — the pre-WP-5 behavior.
    from src.obs.recorder import RunRecorder

    rec = RunRecorder(runs_dir=str(tmp_path))
    rec.record("router", "metric", {"node": "router"})
    rec.flush()
    monkeypatch.setenv("RUNS_DIR", str(tmp_path))
    with TestClient(create_app(runs_dir=str(tmp_path))) as client:
        resp = client.get(f"/api/runs/{rec.run_id}")
        assert resp.status_code == 200
        body = resp.json()
        assert body["run_id"] == rec.run_id
        assert body["source"] == "jsonl"
        assert body["events"][0]["node"] == "router"


def test_runs_endpoint_404_for_unknown_id(tmp_path):
    with TestClient(create_app(runs_dir=str(tmp_path))) as client:
        assert client.get("/api/runs/does-not-exist").status_code == 404


def test_runs_endpoint_422_for_non_token_run_id(tmp_path):
    # run_ids are short [A-Za-z0-9-] tokens; anything else (dotted traversal
    # attempts, over-long ids) is rejected with 422 (same code as ticker_path)
    # before touching the filesystem or the DB.
    with TestClient(create_app(runs_dir=str(tmp_path))) as client:
        assert client.get("/api/runs/..etc").status_code == 422
        assert client.get(f"/api/runs/{'a' * 65}").status_code == 422


def test_cors_headers_present():
    with TestClient(create_app()) as client:
        resp = client.get("/healthz", headers={"Origin": "http://example.com"})
        assert resp.headers.get("access-control-allow-origin") == "*"


# ---------------------------------------------------------------------------
# WP-5 breaking rename: the root routes are GONE — everything lives under /api.
# ---------------------------------------------------------------------------


def test_old_root_analyze_route_removed():
    with TestClient(create_app()) as client:
        resp = client.post("/analyze", json={"ticker": "AAPL"})
        assert resp.status_code in {404, 405}


def test_old_root_runs_route_removed(tmp_path):
    from src.obs.recorder import RunRecorder

    rec = RunRecorder(runs_dir=str(tmp_path))
    rec.record("router", "metric", {})
    rec.flush()
    with TestClient(create_app(runs_dir=str(tmp_path))) as client:
        assert client.get(f"/runs/{rec.run_id}").status_code == 404


def test_create_app_configures_root_logging_for_containers():
    # uvicorn only configures its own loggers; without a root handler the
    # lifespan/collector INFO lines vanish from `docker logs` (WP-11). basicConfig
    # must be applied by create_app — and stay a no-op when handlers exist.
    import logging

    root = logging.getLogger()
    saved_handlers, saved_level = root.handlers[:], root.level
    root.handlers = []
    try:
        create_app()
        assert root.handlers, "create_app must install a root log handler"
        assert root.level <= logging.INFO
    finally:
        root.handlers, root.level = saved_handlers, saved_level

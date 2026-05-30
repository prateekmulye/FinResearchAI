import json

from starlette.testclient import TestClient

from src.api.main import create_app


def _parse_sse(raw: str):
    """Parse an SSE text body into a list of (event, json_payload) tuples.

    sse-starlette emits CRLF line endings and separates frames with a blank line;
    normalize to LF so frame boundaries (``\\n\\n``) are unambiguous.
    """
    raw = raw.replace("\r\n", "\n").replace("\r", "\n")
    events = []
    for block in raw.strip().split("\n\n"):
        ev_name, data_lines = None, []
        for line in block.splitlines():
            if line.startswith("event:"):
                ev_name = line[len("event:"):].strip()
            elif line.startswith("data:"):
                data_lines.append(line[len("data:"):].strip())
        if ev_name and data_lines:
            events.append((ev_name, json.loads("".join(data_lines))))
    return events


def test_healthz():
    with TestClient(create_app()) as client:
        resp = client.get("/healthz")
        assert resp.status_code == 200
        assert resp.json()["status"] == "ok"


def test_analyze_streams_events_ending_in_done(offline_graph):
    with TestClient(create_app()) as client:
        resp = client.post("/analyze", json={"ticker": "AAPL", "investor_mode": "Neutral"})
        assert resp.status_code == 200
        assert resp.headers["content-type"].startswith("text/event-stream")
        events = _parse_sse(resp.text)
        names = [e[0] for e in events]
        assert names[0] == "start"
        assert names[-1] == "done"
        assert "node_complete" in names
        done = events[-1][1]
        assert done["final_decision"]["action"] in {"BUY", "SELL", "HOLD"}


def test_analyze_rejects_bad_ticker_with_422():
    with TestClient(create_app()) as client:
        resp = client.post("/analyze", json={"ticker": "; DROP TABLE--"})
        assert resp.status_code == 422


def test_rate_limit_returns_429_after_cap(offline_graph):
    # cap of 2 requests for the test app
    with TestClient(create_app(rate_limit=2, rate_window_s=3600)) as client:
        body = {"ticker": "AAPL"}
        assert client.post("/analyze", json=body).status_code == 200
        assert client.post("/analyze", json=body).status_code == 200
        resp = client.post("/analyze", json=body)
        assert resp.status_code == 429


def test_runs_endpoint_reads_jsonl_trace(tmp_path, monkeypatch):
    # Write a fake trace where RunRecorder would, then read it back.
    from src.obs.recorder import RunRecorder

    rec = RunRecorder(runs_dir=str(tmp_path))
    rec.record("router", "metric", {"node": "router"})
    rec.flush()
    monkeypatch.setenv("RUNS_DIR", str(tmp_path))
    with TestClient(create_app(runs_dir=str(tmp_path))) as client:
        resp = client.get(f"/runs/{rec.run_id}")
        assert resp.status_code == 200
        body = resp.json()
        assert body["run_id"] == rec.run_id
        assert body["events"][0]["node"] == "router"


def test_runs_endpoint_404_for_unknown_id(tmp_path):
    with TestClient(create_app(runs_dir=str(tmp_path))) as client:
        assert client.get("/runs/does-not-exist").status_code == 404


def test_cors_headers_present():
    with TestClient(create_app()) as client:
        resp = client.get("/healthz", headers={"Origin": "http://example.com"})
        assert resp.headers.get("access-control-allow-origin") == "*"

# tests/test_recorder.py
import json
from src.obs.recorder import RunRecorder


def test_recorder_collects_and_flushes(tmp_path):
    rec = RunRecorder(runs_dir=str(tmp_path))
    rec.record("router", "output", {"resolved_ticker": "AAPL"})
    rec.record("news_analyst", "output", {"summary": "ok"})
    path = rec.flush()
    assert path.exists()
    lines = path.read_text(encoding="utf-8").strip().splitlines()
    assert len(lines) == 2
    first = json.loads(lines[0])
    assert first["node"] == "router"
    assert first["run_id"] == rec.run_id
    assert first["data"]["resolved_ticker"] == "AAPL"


def test_recorder_generates_unique_run_ids():
    assert RunRecorder().run_id != RunRecorder().run_id


def test_recorder_serializes_non_json_values(tmp_path):
    rec = RunRecorder(runs_dir=str(tmp_path))
    rec.record("x", "output", {"obj": object()})  # not JSON-native
    path = rec.flush()  # must not raise
    assert path.exists()

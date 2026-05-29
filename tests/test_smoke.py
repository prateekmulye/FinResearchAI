# tests/test_smoke.py
from scripts.smoke import run_stub


def test_run_stub_returns_report_and_writes_trace(tmp_path):
    result, trace_path = run_stub("AAPL", runs_dir=str(tmp_path))
    assert "final_report" in result
    assert trace_path.exists()
    assert len(trace_path.read_text(encoding="utf-8").strip().splitlines()) == 12

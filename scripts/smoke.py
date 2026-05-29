# scripts/smoke.py
"""Run the stub graph end-to-end and write its run_metrics trace.
Usage: python -m scripts.smoke --ticker AAPL"""
from __future__ import annotations

import argparse

from src.graph import build_graph
from src.obs.recorder import RunRecorder


def run_stub(ticker: str, runs_dir: str = "runs"):
    app = build_graph()
    result = app.invoke({"ticker": ticker, "investor_mode": "Neutral"})
    rec = RunRecorder(runs_dir=runs_dir)
    for metric in result.get("run_metrics", []):
        rec.record(metric["node"], "metric", metric)
    return result, rec.flush()


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--ticker", default="AAPL")
    parser.add_argument("--runs-dir", default="runs")
    args = parser.parse_args()
    result, trace = run_stub(args.ticker, args.runs_dir)
    print(result["final_report"])
    print(f"\n[trace] {trace}  | metrics: {len(result['run_metrics'])} nodes")


if __name__ == "__main__":
    main()

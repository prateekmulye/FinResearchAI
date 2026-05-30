"""CLI: debate A/B eval over a curated ticker set.

Usage:
    python -m src.eval.run --tickers evals/tickers.json --label demo

Loads tickers, runs build_graph("on") vs build_graph("off") per ticker, judges
each pair with the deep model, and writes evals/report-<label>.{md,json}.
The quality number is a PROXY (judge preference + score/cost/latency deltas), not
realized P&L — see src/eval/report.PROXY_DISCLAIMER."""
from __future__ import annotations

import argparse
import asyncio
import json
from pathlib import Path

from src.eval.harness import PairedResult, run_ab
from src.eval.judge import JudgeVerdict, judge_decision
from src.eval.report import write_report


def load_tickers(path: str) -> list[str]:
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    return [row["ticker"] for row in data["tickers"]]


def _context_for(pair: PairedResult) -> str:
    """Compact shared context handed to the judge. Both pipelines analyzed the
    same ticker; we summarize the two rationales as the referee's evidence base."""
    on_r = pair.decision_on.get("rationale", "")
    off_r = pair.decision_off.get("rationale", "")
    return f"Pipeline-A rationale: {on_r}\nPipeline-B rationale: {off_r}"


async def _judge_all(pairs: list[PairedResult], concurrency: int) -> dict[str, JudgeVerdict]:
    sem = asyncio.Semaphore(concurrency)

    async def _one(p: PairedResult) -> tuple[str, JudgeVerdict]:
        async with sem:
            v = await judge_decision(
                ticker=p.ticker,
                context=_context_for(p),
                decision_on=p.decision_on,
                decision_off=p.decision_off,
            )
        return p.ticker, v

    results = await asyncio.gather(*(_one(p) for p in pairs))
    return dict(results)


async def run_eval(tickers_path: str, label: str, concurrency: int, out_dir: str) -> Path:
    tickers = load_tickers(tickers_path)
    pairs = await run_ab(tickers, concurrency=concurrency)
    verdicts = await _judge_all(pairs, concurrency=concurrency)
    md_path, json_path = write_report(pairs, verdicts, label=label, out_dir=out_dir)
    print(f"[eval] wrote {md_path} and {json_path}")
    return md_path


def main() -> None:
    parser = argparse.ArgumentParser(description="Debate A/B evaluation harness")
    parser.add_argument("--tickers", default="evals/tickers.json")
    parser.add_argument("--label", required=True, help="report filename label (no wall-clock)")
    parser.add_argument("--concurrency", type=int, default=3)
    parser.add_argument("--out-dir", default="evals")
    args = parser.parse_args()
    asyncio.run(run_eval(args.tickers, args.label, args.concurrency, args.out_dir))


if __name__ == "__main__":
    main()

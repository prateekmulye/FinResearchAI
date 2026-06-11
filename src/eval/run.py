"""CLI: debate A/B eval over a curated ticker set.

Usage:
    python -m src.eval.run --tickers evals/tickers.json --label demo

Loads tickers, runs build_graph("on") vs build_graph("off") per ticker, judges
each pair with the deep model, and writes evals/report-<label>.{md,json}.
When the warehouse is enabled the same result (label + summary + per-ticker
rows) is also persisted to ``eval_results`` for GET /api/eval/results (WP-10);
persistence never raises, so file outputs are unaffected either way.
The quality number is a PROXY (judge preference + score/cost/latency deltas), not
realized P&L — see src/eval/report.PROXY_DISCLAIMER."""
from __future__ import annotations

import argparse
import asyncio
import json
import logging
from pathlib import Path

from src.eval.harness import PairedResult, run_ab
from src.eval.judge import JudgeVerdict, judge_decision
from src.eval.report import _per_ticker_rows, aggregate, write_report
from src.llm.cost import CostTracker
from src.warehouse.ingest import record_eval_result

_LOG = logging.getLogger(__name__)


def load_tickers(path: str) -> list[str]:
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    return [row["ticker"] for row in data["tickers"]]


def _context_for(pair: PairedResult) -> str:
    """Compact shared context handed to the judge. Both pipelines analyzed the
    same ticker; we summarize the two rationales as the referee's evidence base."""
    on_r = pair.decision_on.get("rationale", "")
    off_r = pair.decision_off.get("rationale", "")
    return f"Pipeline-A rationale: {on_r}\nPipeline-B rationale: {off_r}"


async def _judge_all(
    pairs: list[PairedResult], concurrency: int
) -> tuple[dict[str, JudgeVerdict], dict]:
    """Judge every pair (bounded concurrency). Returns (verdicts, judge_totals)
    where judge_totals is the shared CostTracker.totals() across all judge calls."""
    sem = asyncio.Semaphore(concurrency)
    tracker = CostTracker("eval_judge")

    async def _one(p: PairedResult) -> tuple[str, JudgeVerdict | None]:
        async with sem:
            try:
                v = await judge_decision(
                    ticker=p.ticker,
                    context=_context_for(p),
                    decision_on=p.decision_on,
                    decision_off=p.decision_off,
                    tracker=tracker,
                )
            except Exception:
                # One judge failure must not kill the batch: leave the ticker
                # unjudged — aggregate()'s n_judged machinery tolerates missing
                # verdicts — and let the report land for everything else.
                _LOG.warning("eval judge failed for %s; leaving unjudged", p.ticker, exc_info=True)
                return p.ticker, None
        return p.ticker, v

    results = await asyncio.gather(*(_one(p) for p in pairs))
    verdicts = {ticker: verdict for ticker, verdict in results if verdict is not None}
    return verdicts, tracker.totals()


async def run_eval(tickers_path: str, label: str, concurrency: int, out_dir: str) -> Path:
    tickers = load_tickers(tickers_path)
    pairs = await run_ab(tickers, concurrency=concurrency)
    verdicts, judge_totals = await _judge_all(pairs, concurrency=concurrency)
    md_path, json_path = write_report(
        pairs, verdicts, label=label, out_dir=out_dir, judge_totals=judge_totals
    )
    print(f"[eval] wrote {md_path} and {json_path}")
    # WP-10: persist the same summary + per-ticker rows the JSON report carries
    # so GET /api/eval/results serves real data. Runs AFTER the file writes and
    # never raises (warehouse disabled -> no-op False), so the eval's file
    # outputs are identical with or without a warehouse.
    if await record_eval_result(
        label, aggregate(pairs, verdicts, judge_totals), _per_ticker_rows(pairs, verdicts)
    ):
        print(f"[eval] persisted eval result label={label!r} to warehouse")
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

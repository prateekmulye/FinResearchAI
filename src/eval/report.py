"""Pure, deterministic aggregation of debate A/B results into markdown + JSON.

Honesty contract (paper-analysis critiques #2 and #3): the quality signal here is
a PROXY — deep-judge reasoning-preference + on/off action agreement + score
distribution — combined with measured cost/latency/token deltas. It is explicitly
NOT realized profit-and-loss; this harness runs no backtest. Every report embeds
PROXY_DISCLAIMER so the framing is never lost.

No wall-clock is used in filenames or logic: the caller passes a `label`."""
from __future__ import annotations

import json
import statistics
from pathlib import Path

from src.eval.harness import PairedResult
from src.eval.judge import JudgeVerdict

PROXY_DISCLAIMER = (
    "QUALITY SIGNAL IS A PROXY, NOT REALIZED P&L. This harness measures whether the "
    "debate pipeline produces better-reasoned and/or different decisions than a "
    "single-pass baseline, at what cost/latency. It runs NO backtest and reports NO "
    "realized returns. Higher judge-preference or score deltas do not imply trading "
    "profit. Regime coverage is limited to the curated ticker snapshot (see "
    "evals/tickers.json _note). The referee sees the two verdicts in a fixed A/B "
    "position (A=debate-on), so a small LLM positional bias toward the first option "
    "may inflate the debate-on preference rate."
)


def _round(x: float, n: int = 4) -> float:
    return round(float(x), n)


def _judge_cost_fields(judge_totals: dict | None) -> dict:
    """Normalize CostTracker.totals() into the summary's judge-cost keys.

    The judge's own LLM spend is part of the eval's true cost (paper critique #3),
    so it is surfaced explicitly rather than folded into the pipeline deltas."""
    totals = judge_totals or {}
    tokens = int(totals.get("prompt_tokens", 0) or 0) + int(
        totals.get("completion_tokens", 0) or 0
    )
    return {
        "judge_cost_usd": _round(float(totals.get("cost_usd", 0.0) or 0.0), 6),
        "judge_tokens": tokens,
    }


def aggregate(
    pairs: list[PairedResult],
    verdicts: dict[str, JudgeVerdict],
    judge_totals: dict | None = None,
) -> dict:
    """Compute paired on-vs-off summary statistics. Deterministic.

    ``judge_totals`` is the batch judge's CostTracker.totals(); its cost/tokens
    land in the summary as judge_cost_usd/judge_tokens (zeros when absent)."""
    n = len(pairs)
    if n == 0:
        return {
            "n_tickers": 0,
            "n_judged": 0,
            "action_agreement_rate": 0.0,
            "judge_prefers_on_rate": 0.0,
            "judge_agreement_rate": 0.0,
            "mean_score_delta_on_minus_off": 0.0,
            "score_delta_stdev": 0.0,
            "mean_cost_delta_on_minus_off": 0.0,
            "mean_latency_delta_on_minus_off": 0.0,
            "mean_token_delta_on_minus_off": 0.0,
            **_judge_cost_fields(judge_totals),
        }

    score_deltas = [p.score_on - p.score_off for p in pairs]
    cost_deltas = [p.cost_on - p.cost_off for p in pairs]
    latency_deltas = [p.latency_on - p.latency_off for p in pairs]
    token_deltas = [p.tokens_on - p.tokens_off for p in pairs]

    action_matches = sum(1 for p in pairs if p.action_on == p.action_off)
    # Judge rates are over the pairs that were ACTUALLY judged, not all tickers —
    # a missing verdict must not deflate the rate as if the judge said "no".
    judged = [p for p in pairs if verdicts.get(p.ticker)]
    n_judged = len(judged)
    prefers_on = sum(1 for p in judged if verdicts[p.ticker].preferred == "on")
    judge_agree = sum(1 for p in judged if verdicts[p.ticker].agreement)

    return {
        "n_tickers": n,
        "n_judged": n_judged,
        "action_agreement_rate": _round(action_matches / n),
        "judge_prefers_on_rate": _round(prefers_on / n_judged) if n_judged else 0.0,
        "judge_agreement_rate": _round(judge_agree / n_judged) if n_judged else 0.0,
        "mean_score_delta_on_minus_off": _round(statistics.fmean(score_deltas)),
        "score_delta_stdev": _round(statistics.pstdev(score_deltas)) if n > 1 else 0.0,
        # Cost is the headline (paper critique #3); keep 6 dp to match per-ticker rows.
        "mean_cost_delta_on_minus_off": _round(statistics.fmean(cost_deltas), 6),
        "mean_latency_delta_on_minus_off": _round(statistics.fmean(latency_deltas)),
        "mean_token_delta_on_minus_off": _round(statistics.fmean(token_deltas)),
        **_judge_cost_fields(judge_totals),
    }


def _per_ticker_rows(pairs: list[PairedResult], verdicts: dict[str, JudgeVerdict]) -> list[dict]:
    rows = []
    for p in pairs:
        v = verdicts.get(p.ticker)
        rows.append({
            "ticker": p.ticker,
            "action_on": p.action_on,
            "action_off": p.action_off,
            "actions_agree": p.action_on == p.action_off,
            "score_on": p.score_on,
            "score_off": p.score_off,
            "score_delta": p.score_on - p.score_off,
            "cost_on": _round(p.cost_on, 6),
            "cost_off": _round(p.cost_off, 6),
            "latency_on": _round(p.latency_on),
            "latency_off": _round(p.latency_off),
            "tokens_on": p.tokens_on,
            "tokens_off": p.tokens_off,
            "judge_preferred": v.preferred if v else None,
            "judge_agreement": v.agreement if v else None,
            "judge_confidence": v.confidence if v else None,
        })
    return rows


def render_markdown(
    summary: dict,
    pairs: list[PairedResult],
    verdicts: dict[str, JudgeVerdict],
    label: str,
) -> str:
    rows = _per_ticker_rows(pairs, verdicts)
    lines: list[str] = []
    lines.append(f"# Debate A/B Evaluation — `{label}`")
    lines.append("")
    lines.append(f"> {PROXY_DISCLAIMER}")
    lines.append("")
    lines.append("## Summary (debate-on minus debate-off)")
    lines.append("")
    lines.append("| Metric | Value |")
    lines.append("|---|---|")
    lines.append(f"| Tickers | {summary['n_tickers']} |")
    lines.append(f"| Action-agreement rate (on vs off) | {summary['action_agreement_rate']:.2%} |")
    lines.append(f"| Judge prefers debate-on rate | {summary['judge_prefers_on_rate']:.2%} |")
    lines.append(f"| Judge action-agreement rate | {summary['judge_agreement_rate']:.2%} |")
    lines.append(f"| Mean score delta (on - off) | {summary['mean_score_delta_on_minus_off']} |")
    lines.append(f"| Score delta spread (pop. stdev) | ± {summary['score_delta_stdev']} |")
    lines.append(f"| Mean cost delta USD (on - off) | {summary['mean_cost_delta_on_minus_off']} |")
    lines.append(f"| Mean latency delta s (on - off) | {summary['mean_latency_delta_on_minus_off']} |")
    lines.append(f"| Mean token delta (on - off) | {summary['mean_token_delta_on_minus_off']} |")
    lines.append(
        f"| Judge cost USD (tokens) | {summary.get('judge_cost_usd', 0.0)} "
        f"({summary.get('judge_tokens', 0)}) |"
    )
    lines.append("")
    lines.append("## Per-ticker")
    lines.append("")
    lines.append("| Ticker | Act on | Act off | Agree | Score on | Score off | ΔScore | "
                 "Cost on | Cost off | Lat on | Lat off | Judge pref | Judge conf |")
    lines.append("|---|---|---|---|---|---|---|---|---|---|---|---|---|")
    for r in rows:
        lines.append(
            f"| {r['ticker']} | {r['action_on']} | {r['action_off']} | "
            f"{'yes' if r['actions_agree'] else 'no'} | {r['score_on']} | {r['score_off']} | "
            f"{r['score_delta']} | {r['cost_on']} | {r['cost_off']} | {r['latency_on']} | "
            f"{r['latency_off']} | {r['judge_preferred']} | {r['judge_confidence']} |"
        )
    lines.append("")
    return "\n".join(lines)


def write_report(
    pairs: list[PairedResult],
    verdicts: dict[str, JudgeVerdict],
    label: str,
    out_dir: str = "evals",
    judge_totals: dict | None = None,
) -> tuple[Path, Path]:
    """Write report-<label>.md and report-<label>.json. No wall-clock in names."""
    summary = aggregate(pairs, verdicts, judge_totals)
    md = render_markdown(summary, pairs, verdicts, label)
    payload = {
        "label": label,
        "disclaimer": PROXY_DISCLAIMER,
        "summary": summary,
        "per_ticker": _per_ticker_rows(pairs, verdicts),
    }
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    md_path = out / f"report-{label}.md"
    json_path = out / f"report-{label}.json"
    md_path.write_text(md, encoding="utf-8")
    json_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    return md_path, json_path

"""Debate A/B harness: run build_graph("on") vs build_graph("off") on the same
inputs and capture paired decisions + cost/latency totals.

This module ONLY calls build_graph(debate_mode) — the on/off toggle is owned by
WP-D (COORDINATION.md §4). In unit tests, build_graph is monkeypatched on this
module to return canned graph fakes, so no network or real graph is exercised."""
from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass
from typing import Any

from src.graph import build_graph  # WP-D evolves this to accept debate_mode

_LOG = logging.getLogger(__name__)


@dataclass
class PairedResult:
    """One ticker's debate-on vs debate-off outcome, with cost/latency totals."""

    ticker: str
    decision_on: dict
    decision_off: dict
    metrics_on: list[dict]
    metrics_off: list[dict]

    @property
    def score_on(self) -> int:
        return int(self.decision_on.get("score", 0))

    @property
    def score_off(self) -> int:
        return int(self.decision_off.get("score", 0))

    @property
    def action_on(self) -> str:
        return str(self.decision_on.get("action", ""))

    @property
    def action_off(self) -> str:
        return str(self.decision_off.get("action", ""))

    @property
    def cost_on(self) -> float:
        return _sum_metric(self.metrics_on, "cost_usd")

    @property
    def cost_off(self) -> float:
        return _sum_metric(self.metrics_off, "cost_usd")

    @property
    def latency_on(self) -> float:
        return _sum_metric(self.metrics_on, "latency_s")

    @property
    def latency_off(self) -> float:
        return _sum_metric(self.metrics_off, "latency_s")

    @property
    def tokens_on(self) -> int:
        return _sum_tokens(self.metrics_on)

    @property
    def tokens_off(self) -> int:
        return _sum_tokens(self.metrics_off)


def _sum_metric(metrics: list[dict], key: str) -> float:
    return float(sum(float(m.get(key, 0.0) or 0.0) for m in (metrics or [])))


def _sum_tokens(metrics: list[dict]) -> int:
    return int(
        sum(
            int(m.get("prompt_tokens", 0) or 0) + int(m.get("completion_tokens", 0) or 0)
            for m in (metrics or [])
        )
    )


async def _run_one_mode(ticker: str, mode: str, investor_mode: str) -> dict[str, Any]:
    app = build_graph(mode)
    return await app.ainvoke({"ticker": ticker, "investor_mode": investor_mode})


async def _run_pair(
    ticker: str, investor_mode: str, sem: asyncio.Semaphore
) -> PairedResult | None:
    """Run the on/off pair for one ticker. Returns None (logged) on failure so a
    single bad ticker can't abort the whole batch and discard completed results."""
    try:
        async with sem:
            # Run the two graphs for this ticker concurrently; the semaphore bounds
            # how many *pairs* are in flight at once.
            state_on, state_off = await asyncio.gather(
                _run_one_mode(ticker, "on", investor_mode),
                _run_one_mode(ticker, "off", investor_mode),
            )
    except Exception as exc:
        _LOG.warning("eval: ticker %s failed (%s); dropping from results", ticker, exc)
        return None
    return PairedResult(
        ticker=ticker,
        decision_on=state_on.get("final_decision", {}) or {},
        decision_off=state_off.get("final_decision", {}) or {},
        metrics_on=state_on.get("run_metrics", []) or [],
        metrics_off=state_off.get("run_metrics", []) or [],
    )


async def run_ab(
    tickers: list[str],
    *,
    investor_mode: str = "Neutral",
    concurrency: int = 3,
) -> list[PairedResult]:
    """For each ticker, run debate-on and debate-off graphs and pair the results.

    Bounded by `concurrency` pairs in flight via asyncio.Semaphore. Order follows
    `tickers` (asyncio.gather preserves order). Tickers that raise are logged and
    dropped, so partial results survive a flaky run."""
    sem = asyncio.Semaphore(concurrency)
    results = await asyncio.gather(*(_run_pair(t, investor_mode, sem) for t in tickers))
    return [r for r in results if r is not None]

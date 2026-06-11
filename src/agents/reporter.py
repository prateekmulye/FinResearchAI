"""WP-F Reporter node. Assembles a markdown investment report directly from the
typed AgentState (no vector store) and a structured financial_data dict for the UI.

One LLM call (quick tier) produces the narrative sections AND the radar inputs as a
nested Pydantic model; the verdict header and the cost/observability footer are
rendered deterministically in pure Python.
"""
from __future__ import annotations

import json
import logging

from pydantic import BaseModel, Field, field_validator

from src.agents._metrics import zero_metrics
from src.llm.cost import CostTracker
from src.llm.factory import STRUCT_METHOD, get_llm
from src.config.settings import get_settings

_LOG = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Local Pydantic models — NOT added to the frozen src/llm/schemas.py
# ---------------------------------------------------------------------------


class MetricCard(BaseModel):
    """A single labeled metric for the UI metric-card row."""

    label: str
    value: str


class FinancialData(BaseModel):
    """Radar-chart axes (0..100) + metric cards consumed by the UI (WP-G).

    Each axis is a normalized 0..100 health score derived from analyst data:
    higher is more favorable (for `risk`, higher = better risk profile)."""

    valuation: float = Field(description="Valuation attractiveness 0..100 (higher = cheaper/fairer)")
    growth: float = Field(description="Growth strength 0..100")
    profitability: float = Field(description="Profitability/margins 0..100")
    momentum: float = Field(description="Technical momentum 0..100")
    sentiment: float = Field(description="News/market sentiment 0..100")
    risk: float = Field(description="Risk profile 0..100 (higher = safer)")
    metric_cards: list[MetricCard] = Field(default_factory=list)

    @field_validator("valuation", "growth", "profitability", "momentum", "sentiment", "risk")
    @classmethod
    def _clamp_0_100(cls, v: float) -> float:
        return max(0.0, min(100.0, float(v)))


class ReportSection(BaseModel):
    """One markdown section of the narrative report."""

    heading: str
    body: str


class ReportPayload(BaseModel):
    """The single structured LLM output: narrative sections + radar/metric inputs."""

    sections: list[ReportSection] = Field(default_factory=list)
    financial_data: FinancialData


# ---------------------------------------------------------------------------
# Metrics aggregation + footer renderer (pure Python, no LLM)
# ---------------------------------------------------------------------------


def aggregate_metrics(run_metrics: list[dict] | None) -> dict:
    """Sum per-node metric records into run totals. Tolerant of missing keys.

    ``node_count`` counts DISTINCT node labels: debate sub-turn records all share
    one label (research_debate/risk_debate), so raw record count would inflate
    'Nodes executed' with per-LLM-call lines."""
    records = run_metrics or []
    prompt = sum(int(r.get("prompt_tokens", 0) or 0) for r in records)
    completion = sum(int(r.get("completion_tokens", 0) or 0) for r in records)
    latency = sum(float(r.get("latency_s", 0.0) or 0.0) for r in records)
    cost = sum(float(r.get("cost_usd", 0.0) or 0.0) for r in records)
    return {
        "prompt_tokens": prompt,
        "completion_tokens": completion,
        "total_tokens": prompt + completion,
        "latency_s": round(latency, 4),
        "cost_usd": round(cost, 6),
        "node_count": len({r.get("node") for r in records}),
    }


def render_metrics_footer(
    run_metrics: list[dict] | None, debate_mode: str, *, cache_hit: bool = False
) -> str:
    """Render the transparent cost/observability footer from run_metrics."""
    agg = aggregate_metrics(run_metrics)
    cache_row = "| Served from verdict cache | yes |\n" if cache_hit else ""
    return (
        "\n---\n\n"
        "### Run Transparency\n\n"
        "| Metric | Value |\n"
        "|---|---|\n"
        f"| Estimated cost | ${agg['cost_usd']:.3f} |\n"
        f"| Total latency | {agg['latency_s']:.1f}s |\n"
        f"| Tokens (prompt / completion / total) | "
        f"{agg['prompt_tokens']} / {agg['completion_tokens']} / {agg['total_tokens']} |\n"
        f"| Nodes executed | {agg['node_count']} |\n"
        f"| Debate mode | {debate_mode} |\n"
        f"{cache_row}"
        "\n_Costs and latency are measured per-node via CostTracker callbacks "
        "and aggregated here for full transparency._\n"
    )


# ---------------------------------------------------------------------------
# Verdict header renderer (pure Python, deterministic — never hallucinated)
# ---------------------------------------------------------------------------


def render_verdict_header(
    *,
    ticker: str,
    resolved_ticker: str,
    investor_mode: str,
    final_decision: dict,
    trade_proposal: dict,
) -> str:
    """Render the prominent verdict header deterministically from final_decision.

    The pre-risk trade_proposal is shown for transparency when it differs."""
    fd = final_decision or {}
    tp = trade_proposal or {}
    action = str(fd.get("action", "HOLD"))
    conviction = float(fd.get("conviction", 0.0) or 0.0)
    score = int(fd.get("score", 0) or 0)
    rationale = str(fd.get("rationale", "No rationale provided.")).strip()
    symbol = resolved_ticker or ticker

    lines = [
        f"# Investment Research Report — {symbol}",
        "",
        f"**Verdict: {action}**  ·  Score: **{score}/100**  ·  "
        f"Conviction: **{conviction:.2f}**  ·  Investor mode: {investor_mode or 'Neutral'}",
        "",
        f"> {rationale}",
        "",
    ]

    tp_action = tp.get("action")
    if tp_action is not None and (
        tp_action != action or int(tp.get("score", -1) or -1) != score
    ):
        tp_score = int(tp.get("score", 0) or 0)
        tp_conv = float(tp.get("conviction", 0.0) or 0.0)
        lines.append(
            f"_Pre-risk-adjustment proposal: {tp_action} "
            f"(score {tp_score}/100, conviction {tp_conv:.2f}) — "
            f"adjusted to {action} by the risk arbiter._"
        )
        lines.append("")

    return "\n".join(lines)


# ---------------------------------------------------------------------------
# System prompt + message builder for the structured LLM call
# ---------------------------------------------------------------------------

REPORTER_SYSTEM_PROMPT = (
    "You are the Reporter agent in a multi-agent equity research system. "
    "Write a concise, professional investment research narrative for the given stock, "
    "using ONLY the analyst, debate, and decision data provided. Do not invent facts, "
    "prices, or citations. Do not restate a verdict line or any cost/latency numbers — "
    "those are rendered separately by the system.\n\n"
    "Return structured output with two parts:\n"
    "1. `sections`: an ordered list of markdown report sections. Recommended sections: "
    "Executive Summary, Bull vs. Bear, Fundamentals, Technicals, News & Sentiment, "
    "Risk Assessment, Bottom Line. Each section has a short `heading` (no leading '#') "
    "and a `body` of 1-3 tight paragraphs or bullet lists in GitHub-flavored markdown.\n"
    "2. `financial_data`: six normalized 0..100 health scores for a radar chart "
    "(valuation, growth, profitability, momentum, sentiment, risk; for `risk`, higher "
    "means a SAFER profile), each grounded in the analyst data, plus a `metric_cards` "
    "list of {label, value} pairs surfacing the most decision-relevant numbers "
    "(e.g. P/E, RSI, conviction). Use neutral 50 when a dimension is unsupported by data."
)


def _compact(value, limit: int = 1200) -> str:
    """JSON-serialize a state value compactly for the prompt (truncated, JSON-safe)."""
    try:
        text = json.dumps(value, default=str, ensure_ascii=False)
    except (TypeError, ValueError):
        text = str(value)
    return text if len(text) <= limit else text[:limit] + "…"


def build_report_messages(state: dict) -> list[dict]:
    """Build [system, user] messages serializing the consumed state fields."""
    symbol = state.get("resolved_ticker") or state.get("ticker", "")
    human = (
        f"Ticker: {symbol}\n"
        f"Investor mode: {state.get('investor_mode', 'Neutral')}\n\n"
        f"ANALYST REPORTS:\n{_compact(state.get('analyst_reports', {}), 2000)}\n\n"
        f"RESEARCH DEBATE (bull/bear/facilitator):\n"
        f"{_compact(state.get('research_debate', {}), 1500)}\n\n"
        f"TRADE PROPOSAL (pre-risk):\n{_compact(state.get('trade_proposal', {}))}\n\n"
        f"RISK DEBATE:\n{_compact(state.get('risk_debate', {}), 1500)}\n\n"
        f"FINAL DECISION:\n{_compact(state.get('final_decision', {}))}\n\n"
        "Write the report sections and the financial_data radar inputs now."
    )
    return [
        {"role": "system", "content": REPORTER_SYSTEM_PROMPT},
        {"role": "user", "content": human},
    ]


# ---------------------------------------------------------------------------
# Async reporter node helpers
# ---------------------------------------------------------------------------


def _render_sections(sections: list[ReportSection]) -> str:
    parts: list[str] = []
    for sec in sections:
        parts.append(f"## {sec.heading}\n\n{sec.body}")
    return "\n\n".join(parts)


def _minimal_fallback_report(
    state: dict,
    error: Exception,
    debate_mode: str,
    this_node_metrics: list[dict],
) -> dict:
    """Produce a minimal markdown report from pure state when the LLM call fails."""
    fd_default = FinancialData(
        valuation=50.0, growth=50.0, profitability=50.0,
        momentum=50.0, sentiment=50.0, risk=50.0,
    )
    header = render_verdict_header(
        ticker=state.get("ticker", ""),
        resolved_ticker=state.get("resolved_ticker", ""),
        investor_mode=state.get("investor_mode", "Neutral"),
        final_decision=state.get("final_decision", {}),
        trade_proposal=state.get("trade_proposal", {}),
    )
    all_metrics = list(state.get("run_metrics", [])) + this_node_metrics
    footer = render_metrics_footer(all_metrics, debate_mode=debate_mode)
    body = (
        "## Report\n\n"
        "_The narrative sections could not be generated due to an LLM error. "
        f"The structured verdict above is deterministic._\n\n"
        f"**Error:** `{type(error).__name__}: {error}`\n"
    )
    return {
        "final_report": f"{header}\n{body}\n{footer}",
        "financial_data": fd_default.model_dump(),
        "run_metrics": this_node_metrics,
    }


def _cached_verdict_report(state: dict, debate_mode: str) -> dict:
    """Render the cache-hit short-circuit report deterministically — no LLM call.

    The router found a fresh cached FinalDecision and the graph skipped straight
    to the reporter, so there are no analyst reports to narrate. The verdict
    header is rendered from the cached decision and the body says so."""
    header = render_verdict_header(
        ticker=state.get("ticker", ""),
        resolved_ticker=state.get("resolved_ticker", ""),
        investor_mode=state.get("investor_mode", "Neutral"),
        final_decision=state.get("final_decision", {}),
        trade_proposal={},  # no trader ran on the short-circuit path
    )
    body = (
        "## Report\n\n"
        "_This verdict was served from the verdict cache: a recent prior analysis "
        "of this ticker produced the decision above, so the full analyst pipeline "
        "was skipped. Re-run after the cache expires for a fresh analysis._\n"
    )
    this_node_metrics = zero_metrics("reporter")
    all_metrics = list(state.get("run_metrics", [])) + this_node_metrics
    footer = render_metrics_footer(all_metrics, debate_mode=debate_mode, cache_hit=True)
    fd_default = FinancialData(
        valuation=50.0, growth=50.0, profitability=50.0,
        momentum=50.0, sentiment=50.0, risk=50.0,
    )
    return {
        "final_report": f"{header}\n{body}\n{footer}",
        "financial_data": fd_default.model_dump(),
        "run_metrics": this_node_metrics,
    }


# ---------------------------------------------------------------------------
# The async reporter node
# ---------------------------------------------------------------------------


async def reporter(state: dict, *, debate_mode: str | None = None) -> dict:
    """Terminal node: assemble the markdown report + financial_data from typed state.

    Reads analyst_reports, research_debate, trade_proposal, risk_debate,
    final_decision, run_metrics. Writes final_report, financial_data, run_metrics.

    ``debate_mode`` is bound per-run by build_graph (the mode the graph was
    actually compiled with); the settings default is only a fallback for direct
    calls so the footer never reports a mode the run didn't use."""
    tracker = CostTracker("reporter")
    if debate_mode is None:
        debate_mode = getattr(get_settings(), "debate_mode", "on")

    if (state.get("model_plan") or {}).get("cache_hit"):
        # Verdict-cache short-circuit (router -> reporter): render deterministically.
        return _cached_verdict_report(state, debate_mode)

    try:
        llm = get_llm("quick").with_structured_output(ReportPayload, method=STRUCT_METHOD)
        messages = build_report_messages(state)
        payload: ReportPayload = await llm.ainvoke(messages, config={"callbacks": [tracker]})
    except Exception as exc:  # noqa: BLE001
        _LOG.warning("reporter: LLM call failed (%s); falling back to minimal report", exc)
        # The failed ainvoke raised before on_llm_end fired, so per_node is empty;
        # fall back to a zero-cost record so the reporter still emits its trace line.
        this_node_metrics = tracker.totals()["per_node"] or zero_metrics("reporter")
        return _minimal_fallback_report(state, exc, debate_mode, this_node_metrics)

    header = render_verdict_header(
        ticker=state.get("ticker", ""),
        resolved_ticker=state.get("resolved_ticker", ""),
        investor_mode=state.get("investor_mode", "Neutral"),
        final_decision=state.get("final_decision", {}),
        trade_proposal=state.get("trade_proposal", {}),
    )
    body = _render_sections(payload.sections)

    # Footer aggregates ALL upstream metrics PLUS this node's own call.
    # We read this_node_metrics AFTER the ainvoke so the tracker has recorded the call.
    # Guarantee one record even if the callback didn't fire (e.g. structured-output
    # bypasses on_llm_end), matching every other node's per-node-line contract.
    this_node_metrics = tracker.totals()["per_node"] or zero_metrics("reporter")
    all_metrics = list(state.get("run_metrics", [])) + this_node_metrics
    footer = render_metrics_footer(all_metrics, debate_mode=debate_mode)

    final_report = f"{header}\n{body}\n{footer}"

    return {
        "final_report": final_report,
        "financial_data": payload.financial_data.model_dump(),
        "run_metrics": this_node_metrics,
    }

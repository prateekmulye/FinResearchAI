# src/graph.py
"""build_graph — owned by WP-D. Wires the full FinResearchAI pipeline with guarded
imports so each WP's real node auto-activates when its module lands on the branch,
and falls back to an inline stub otherwise.

Topology:
  "on"  (default) : router → 3 analysts → bull + bear (parallel) → facilitator
                    → trader → risk_conservative + risk_aggressive → risk_arbiter → reporter
  "off"           : router → 3 analysts → research_synthesis
                    → trader → risk_conservative + risk_aggressive → risk_arbiter → reporter
"""
from __future__ import annotations

import logging

from langgraph.graph import END, START, StateGraph

from src.config.settings import get_settings
from src.state import AgentState

_LOG = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------------------

def _metric(node: str) -> list[dict]:
    return [{"node": node, "model": "", "prompt_tokens": 0, "completion_tokens": 0,
             "latency_s": 0.0, "cost_usd": 0.0}]


# ---------------------------------------------------------------------------
# Inline stubs — kept as fallbacks when a WP module is not yet merged.
# These are intentionally simple synchronous functions (no LLM calls).
# ---------------------------------------------------------------------------

# WP-B stubs
def _stub_router(state: AgentState) -> dict:
    return {
        "resolved_ticker": state.get("ticker", ""),
        "screener": "america",
        "exchange": "NASDAQ",
        "model_plan": {"analysts": "quick", "debate": "deep", "verdict": "deep"},
        "run_metrics": _metric("router"),
    }


def _stub_analyst(name: str):
    def node(state: AgentState) -> dict:
        return {
            "analyst_reports": {name: {"summary": f"stub {name} report", "confidence": 0.5}},
            "run_metrics": _metric(f"{name}_analyst"),
        }
    return node


# WP-D stubs (bull/bear/facilitator/synthesis)
def _stub_bull(state: AgentState) -> dict:
    return {"research_debate": {"bull_thesis": "stub bull"}, "run_metrics": _metric("bull")}


def _stub_bear(state: AgentState) -> dict:
    return {"research_debate": {"bear_thesis": "stub bear"}, "run_metrics": _metric("bear")}


def _stub_facilitator(state: AgentState) -> dict:
    return {
        "research_debate": {"facilitator_verdict": "stub lean-neutral"},
        "run_metrics": _metric("facilitator"),
    }


def _stub_research_synthesis(state: AgentState) -> dict:
    return {
        "research_debate": {"rounds": [], "bull_thesis": "", "bear_thesis": "",
                            "facilitator_verdict": "stub single-pass verdict"},
        "run_metrics": _metric("research_synthesis"),
    }


# WP-E stubs
def _stub_trader(state: AgentState) -> dict:
    return {
        "trade_proposal": {"action": "HOLD", "conviction": 0.5, "score": 50, "rationale": "stub"},
        "run_metrics": _metric("trader"),
    }


def _stub_risk_conservative(state: AgentState) -> dict:
    return {"risk_debate": {"conservative": "stub careful"}, "run_metrics": _metric("risk_conservative")}


def _stub_risk_aggressive(state: AgentState) -> dict:
    return {"risk_debate": {"aggressive": "stub bold"}, "run_metrics": _metric("risk_aggressive")}


def _stub_risk_arbiter(state: AgentState) -> dict:
    proposal = state.get("trade_proposal", {})
    return {
        "final_decision": {
            "action": proposal.get("action", "HOLD"),
            "conviction": proposal.get("conviction", 0.5),
            "score": proposal.get("score", 50),
            "rationale": "stub arbiter decision",
        },
        "run_metrics": _metric("risk_arbiter"),
    }


# WP-F stub
def _stub_reporter(state: AgentState) -> dict:
    return {"final_report": "# Stub Report\n\nReplace in WP-F.", "run_metrics": _metric("reporter")}


# ---------------------------------------------------------------------------
# Guarded real-module imports — each WP's callable activates when merged.
# ---------------------------------------------------------------------------

# WP-B
try:
    from src.agents.router import router
except ImportError:
    _LOG.debug("WP-B router not merged; using stub")
    router = _stub_router  # type: ignore[assignment]

try:
    from src.agents.analysts.news import news_analyst
    from src.agents.analysts.fundamentals import fundamentals_analyst
    from src.agents.analysts.technicals import technicals_analyst
    _ANALYSTS_REAL = {
        "news": news_analyst,
        "fundamentals": fundamentals_analyst,
        "technicals": technicals_analyst,
    }
except ImportError:
    _LOG.debug("WP-B analysts not merged; using stubs")
    _ANALYSTS_REAL = {}

# WP-D (owned here — always present after this WP merges)
try:
    from src.agents.research.bull import bull
except ImportError:
    _LOG.debug("WP-D bull not merged; using stub")
    bull = _stub_bull  # type: ignore[assignment]

try:
    from src.agents.research.bear import bear
except ImportError:
    _LOG.debug("WP-D bear not merged; using stub")
    bear = _stub_bear  # type: ignore[assignment]

try:
    from src.agents.research.facilitator import facilitator
except ImportError:
    _LOG.debug("WP-D facilitator not merged; using stub")
    facilitator = _stub_facilitator  # type: ignore[assignment]

try:
    from src.agents.research.synthesis import research_synthesis
except ImportError:
    _LOG.debug("WP-D research_synthesis not merged; using stub")
    research_synthesis = _stub_research_synthesis  # type: ignore[assignment]

# WP-E
try:
    from src.agents.trader import trader
except ImportError:
    _LOG.debug("WP-E trader not merged; using stub")
    trader = _stub_trader  # type: ignore[assignment]

try:
    from src.agents.risk.conservative import risk_conservative
except ImportError:
    _LOG.debug("WP-E risk_conservative not merged; using stub")
    risk_conservative = _stub_risk_conservative  # type: ignore[assignment]

try:
    from src.agents.risk.aggressive import risk_aggressive
except ImportError:
    _LOG.debug("WP-E risk_aggressive not merged; using stub")
    risk_aggressive = _stub_risk_aggressive  # type: ignore[assignment]

try:
    from src.agents.risk.arbiter import risk_arbiter
except ImportError:
    _LOG.debug("WP-E risk_arbiter not merged; using stub")
    risk_arbiter = _stub_risk_arbiter  # type: ignore[assignment]

# WP-F
try:
    from src.agents.reporter import reporter
except ImportError:
    _LOG.debug("WP-F reporter not merged; using stub")
    reporter = _stub_reporter  # type: ignore[assignment]


# ---------------------------------------------------------------------------
# Analyst node factory — uses real callable if available, else stub.
# ---------------------------------------------------------------------------

_ANALYST_NAMES = ["news", "fundamentals", "technicals"]


def _analyst_node(name: str):
    """Return the real analyst callable if WP-B is merged, else the stub."""
    if name in _ANALYSTS_REAL:
        return _ANALYSTS_REAL[name]
    return _stub_analyst(name)


# ---------------------------------------------------------------------------
# build_graph — the public interface (WP-D owns this).
# ---------------------------------------------------------------------------

def build_graph(debate_mode: str | None = None):
    """Compile the research pipeline.

    debate_mode:
        None (default) -> reads settings.debate_mode.
        "on"           -> full M2 debate: router -> analysts -> bull + bear -> facilitator
                          -> trader -> risk -> arbiter -> reporter  (12 nodes, 12 run_metrics).
        "off"          -> single-pass baseline: router -> analysts -> research_synthesis
                          -> trader -> risk -> arbiter -> reporter  (10 nodes, 10 run_metrics).

    Guarded imports ensure each WP's real callable is used when merged and the
    inline stub fallback is used otherwise — no graph.py edits needed when later WPs land.
    """
    if debate_mode is None:
        debate_mode = get_settings().debate_mode

    g = StateGraph(AgentState)

    # Always-present nodes (every topology)
    g.add_node("router", router)
    for name in _ANALYST_NAMES:
        g.add_node(f"{name}_analyst", _analyst_node(name))
    g.add_node("trader", trader)
    g.add_node("risk_conservative", risk_conservative)
    g.add_node("risk_aggressive", risk_aggressive)
    g.add_node("risk_arbiter", risk_arbiter)
    g.add_node("reporter", reporter)

    # Edges: start -> router -> 3 analysts (parallel fan-out)
    g.add_edge(START, "router")
    for name in _ANALYST_NAMES:
        g.add_edge("router", f"{name}_analyst")

    if debate_mode == "off":
        # Single-pass baseline: analysts -> research_synthesis -> trader
        g.add_node("research_synthesis", research_synthesis)
        for name in _ANALYST_NAMES:
            g.add_edge(f"{name}_analyst", "research_synthesis")
        g.add_edge("research_synthesis", "trader")
    else:
        # Full debate: analysts -> bull + bear (parallel) -> facilitator -> trader
        g.add_node("bull", bull)
        g.add_node("bear", bear)
        g.add_node("facilitator", facilitator)
        for name in _ANALYST_NAMES:
            g.add_edge(f"{name}_analyst", "bull")
            g.add_edge(f"{name}_analyst", "bear")
        g.add_edge("bull", "facilitator")
        g.add_edge("bear", "facilitator")
        g.add_edge("facilitator", "trader")

    # Risk fan-out and join
    g.add_edge("trader", "risk_conservative")
    g.add_edge("trader", "risk_aggressive")
    g.add_edge("risk_conservative", "risk_arbiter")
    g.add_edge("risk_aggressive", "risk_arbiter")
    g.add_edge("risk_arbiter", "reporter")
    g.add_edge("reporter", END)

    return g.compile()

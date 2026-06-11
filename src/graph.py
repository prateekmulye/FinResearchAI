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

import functools
import importlib
import importlib.util
import logging

from langgraph.graph import END, START, StateGraph

from src.agents._metrics import zero_metrics
from src.config.settings import get_settings
from src.state import AgentState

_LOG = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------------------

def _resolve(module_path: str, attr: str, fallback):
    """Return the real callable from module_path.attr when the module EXISTS on disk
    and exports the expected attr.

    Falls back to ``fallback`` only when the module is genuinely absent:
      - find_spec returns None (module file not on sys.path), or
      - find_spec raises ModuleNotFoundError (parent package absent), or
      - the module exists but does not yet export ``attr`` (WP not yet implemented).

    A module that IS present and exports ``attr`` but fails to import (broken
    internal code) propagates loudly rather than being silently swapped for the
    stub — that is the core of the F2 fix.
    """
    try:
        spec = importlib.util.find_spec(module_path)
    except ModuleNotFoundError:
        # Parent package does not exist — module is genuinely absent.
        _LOG.debug("%s parent not found; using stub for %s", module_path, attr)
        return fallback
    if spec is None:
        _LOG.debug("%s not found; using stub for %s", module_path, attr)
        return fallback
    mod = importlib.import_module(module_path)  # ImportError from broken code → raises
    if not hasattr(mod, attr):
        _LOG.debug("%s.%s not defined; using stub (WP not yet implemented)", module_path, attr)
        return fallback
    return getattr(mod, attr)


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
        "run_metrics": zero_metrics("router"),
    }


def _stub_analyst(name: str):
    def node(state: AgentState) -> dict:
        return {
            "analyst_reports": {name: {"summary": f"stub {name} report", "confidence": 0.5}},
            "run_metrics": zero_metrics(f"{name}_analyst"),
        }
    return node


# WP-D stubs (bull/bear/facilitator/synthesis)
def _stub_bull(state: AgentState) -> dict:
    return {"research_debate": {"bull_thesis": "stub bull"}, "run_metrics": zero_metrics("bull")}


def _stub_bear(state: AgentState) -> dict:
    return {"research_debate": {"bear_thesis": "stub bear"}, "run_metrics": zero_metrics("bear")}


def _stub_facilitator(state: AgentState) -> dict:
    return {
        "research_debate": {"facilitator_verdict": "stub lean-neutral"},
        "run_metrics": zero_metrics("facilitator"),
    }


def _stub_research_synthesis(state: AgentState) -> dict:
    return {
        "research_debate": {"rounds": [], "bull_thesis": "", "bear_thesis": "",
                            "facilitator_verdict": "stub single-pass verdict"},
        "run_metrics": zero_metrics("research_synthesis"),
    }


# WP-E stubs
def _stub_trader(state: AgentState) -> dict:
    return {
        "trade_proposal": {"action": "HOLD", "conviction": 0.5, "score": 50, "rationale": "stub"},
        "run_metrics": zero_metrics("trader"),
    }


def _stub_risk_conservative(state: AgentState) -> dict:
    return {"risk_debate": {"conservative": "stub careful"}, "run_metrics": zero_metrics("risk_conservative")}


def _stub_risk_aggressive(state: AgentState) -> dict:
    return {"risk_debate": {"aggressive": "stub bold"}, "run_metrics": zero_metrics("risk_aggressive")}


def _stub_risk_arbiter(state: AgentState) -> dict:
    proposal = state.get("trade_proposal", {})
    return {
        "final_decision": {
            "action": proposal.get("action", "HOLD"),
            "conviction": proposal.get("conviction", 0.5),
            "score": proposal.get("score", 50),
            "rationale": "stub arbiter decision",
        },
        "run_metrics": zero_metrics("risk_arbiter"),
    }


# WP-F stub
def _stub_reporter(state: AgentState, *, debate_mode: str | None = None) -> dict:
    return {"final_report": "# Stub Report\n\nReplace in WP-F.", "run_metrics": zero_metrics("reporter")}


# ---------------------------------------------------------------------------
# Guarded real-module resolution — uses find_spec so only a GENUINELY ABSENT
# module triggers the stub fallback; a broken-but-present module raises loudly.
# ---------------------------------------------------------------------------

# WP-B
router = _resolve("src.agents.router", "router", _stub_router)

_news_analyst = _resolve("src.agents.analysts.news", "news_analyst", None)
_fundamentals_analyst = _resolve("src.agents.analysts.fundamentals", "fundamentals_analyst", None)
_technicals_analyst = _resolve("src.agents.analysts.technicals", "technicals_analyst", None)
if all(v is not None for v in [_news_analyst, _fundamentals_analyst, _technicals_analyst]):
    _ANALYSTS_REAL = {
        "news": _news_analyst,
        "fundamentals": _fundamentals_analyst,
        "technicals": _technicals_analyst,
    }
else:
    _ANALYSTS_REAL = {}

# WP-D (owned here — always present after this WP merges)
bull = _resolve("src.agents.research.bull", "bull", _stub_bull)
bear = _resolve("src.agents.research.bear", "bear", _stub_bear)
facilitator = _resolve("src.agents.research.facilitator", "facilitator", _stub_facilitator)
research_synthesis = _resolve(
    "src.agents.research.synthesis", "research_synthesis", _stub_research_synthesis
)

# WP-E
trader = _resolve("src.agents.trader", "trader", _stub_trader)
risk_conservative = _resolve(
    "src.agents.risk.conservative", "risk_conservative", _stub_risk_conservative
)
risk_aggressive = _resolve(
    "src.agents.risk.aggressive", "risk_aggressive", _stub_risk_aggressive
)
risk_arbiter = _resolve("src.agents.risk.arbiter", "risk_arbiter", _stub_risk_arbiter)

# WP-F
reporter = _resolve("src.agents.reporter", "reporter", _stub_reporter)


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

def _route_after_router(state: AgentState) -> str | list[str]:
    """Conditional edge after the router: verdict-cache short-circuit.

    When the router attached a fresh cached verdict (model_plan.cache_hit), the
    full pipeline is skipped and the reporter renders straight from the cached
    final_decision. Otherwise: the normal parallel analyst fan-out."""
    if (state.get("model_plan") or {}).get("cache_hit"):
        return "reporter"
    return [f"{name}_analyst" for name in _ANALYST_NAMES]


def build_graph(debate_mode: str | None = None):
    """Compile the research pipeline.

    debate_mode:
        None (default) -> reads settings.debate_mode.
        "on"           -> full M2 debate: router -> analysts -> bull + bear -> facilitator
                          -> trader -> risk -> arbiter -> reporter  (12 nodes, 12 run_metrics).
        "off"          -> single-pass baseline: router -> analysts -> research_synthesis
                          -> trader -> risk -> arbiter -> reporter  (10 nodes, 10 run_metrics).

    A conditional edge after the router short-circuits BOTH topologies to the
    reporter when a fresh cached verdict exists (node counts above describe
    non-cached runs). The resolved debate_mode is bound into the reporter so the
    report footer states the mode this graph actually ran, not the settings default.

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
    # Bind the per-run mode into the reporter so its footer can't drift from
    # the topology actually compiled (settings.debate_mode is only a default).
    g.add_node("reporter", functools.partial(reporter, debate_mode=debate_mode))

    # Edges: start -> router -> 3 analysts (parallel fan-out), unless a fresh
    # cached verdict short-circuits the run straight to the reporter.
    g.add_edge(START, "router")
    g.add_conditional_edges(
        "router",
        _route_after_router,
        [f"{name}_analyst" for name in _ANALYST_NAMES] + ["reporter"],
    )

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

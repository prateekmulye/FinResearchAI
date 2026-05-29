# src/graph.py
"""12-node stub topology for FinResearchAI. Nodes return contract-shaped stub data.
Real implementations are provided by the work-package plans; this file only freezes
the graph wiring and the state contract."""
from __future__ import annotations

from langgraph.graph import END, START, StateGraph

from src.state import AgentState


def _metric(node: str) -> list[dict]:
    return [{"node": node, "prompt_tokens": 0, "completion_tokens": 0, "latency_s": 0.0, "cost_usd": 0.0}]


def router(state: AgentState) -> dict:
    return {
        "resolved_ticker": state.get("ticker", ""),
        "screener": "america",
        "exchange": "NASDAQ",
        "model_plan": {"analysts": "quick", "debate": "deep", "verdict": "deep"},
        "run_metrics": _metric("router"),
    }


def _analyst(name: str):
    def node(state: AgentState) -> dict:
        return {
            "analyst_reports": {name: {"summary": f"stub {name} report", "confidence": 0.5}},
            "run_metrics": _metric(f"{name}_analyst"),
        }
    return node


def bull(state: AgentState) -> dict:
    return {"research_debate": {"bull_thesis": "stub bull"}, "run_metrics": _metric("bull")}


def bear(state: AgentState) -> dict:
    return {"research_debate": {"bear_thesis": "stub bear"}, "run_metrics": _metric("bear")}


def facilitator(state: AgentState) -> dict:
    return {"research_debate": {"facilitator_verdict": "stub lean-neutral"}, "run_metrics": _metric("facilitator")}


def trader(state: AgentState) -> dict:
    return {
        "trade_proposal": {"action": "HOLD", "conviction": 0.5, "score": 50, "rationale": "stub"},
        "run_metrics": _metric("trader"),
    }


def risk_conservative(state: AgentState) -> dict:
    return {"risk_debate": {"conservative": "stub careful"}, "run_metrics": _metric("risk_conservative")}


def risk_aggressive(state: AgentState) -> dict:
    return {"risk_debate": {"aggressive": "stub bold"}, "run_metrics": _metric("risk_aggressive")}


def risk_arbiter(state: AgentState) -> dict:
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


def reporter(state: AgentState) -> dict:
    return {"final_report": "# Stub Report\n\nReplace in WP-F.", "run_metrics": _metric("reporter")}


_ANALYSTS = ["news", "fundamentals", "technicals"]


def build_graph():
    g = StateGraph(AgentState)

    g.add_node("router", router)
    for name in _ANALYSTS:
        g.add_node(f"{name}_analyst", _analyst(name))
    g.add_node("bull", bull)
    g.add_node("bear", bear)
    g.add_node("facilitator", facilitator)
    g.add_node("trader", trader)
    g.add_node("risk_conservative", risk_conservative)
    g.add_node("risk_aggressive", risk_aggressive)
    g.add_node("risk_arbiter", risk_arbiter)
    g.add_node("reporter", reporter)

    g.add_edge(START, "router")

    # Router fans out to the three analysts (parallel).
    for name in _ANALYSTS:
        g.add_edge("router", f"{name}_analyst")

    # All analysts must finish before the bull/bear debate (join via multiple in-edges).
    for name in _ANALYSTS:
        g.add_edge(f"{name}_analyst", "bull")
        g.add_edge(f"{name}_analyst", "bear")

    # Bull + bear both feed the facilitator (join).
    g.add_edge("bull", "facilitator")
    g.add_edge("bear", "facilitator")

    g.add_edge("facilitator", "trader")

    # Trader fans out to the two risk personas.
    g.add_edge("trader", "risk_conservative")
    g.add_edge("trader", "risk_aggressive")

    # Both risk personas feed the arbiter (join).
    g.add_edge("risk_conservative", "risk_arbiter")
    g.add_edge("risk_aggressive", "risk_arbiter")

    g.add_edge("risk_arbiter", "reporter")
    g.add_edge("reporter", END)

    return g.compile()

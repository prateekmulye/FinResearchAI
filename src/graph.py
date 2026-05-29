"""
This module defines the StateGraph for the Financial Research AI Agent.
It orchestrates the flow between the Manager, Researchers (Tavily, YFinance, TradingView),
Analyst, and Reporter agents.
"""

from langgraph.graph import StateGraph, END
from .state import AgentState
from .agents.manager import manager_node
from .agents.researchers.tavily import tavily_node
from .agents.researchers.yfinance_agent import yfinance_node
from .agents.researchers.tradingview import tradingview_node
from .agents.analyst import analyst_node
from .agents.reporter import reporter_node


def route_research(state: AgentState):
    """
    Determines the next step based on the Manager's decision.
    Routes to selected researchers or skips directly to Analyst if cache is valid.
    """
    agents = state.get("agents_to_run", [])
    if not agents:
        return ["analyst"]

    # LangGraph conditional edge with a list of strings will trigger parallel nodes
    # if those nodes are defined in the mapping.
    return agents


def create_graph():
    """
    Constructs and compiles the StateGraph workflow.
    """

    workflow = StateGraph(AgentState)

    # Nodes
    workflow.add_node("manager", manager_node)
    workflow.add_node("tavily_researcher", tavily_node)
    workflow.add_node("yfinance_researcher", yfinance_node)
    workflow.add_node("tradingview_researcher", tradingview_node)
    workflow.add_node("analyst", analyst_node)
    workflow.add_node("reporter", reporter_node)

    # Edges
    workflow.set_entry_point("manager")

    workflow.add_conditional_edges(
        "manager",
        route_research,
        {
            "tavily_researcher": "tavily_researcher",
            "yfinance_researcher": "yfinance_researcher",
            "tradingview_researcher": "tradingview_researcher",
            "analyst": "analyst",
        },
    )

    workflow.add_edge("tavily_researcher", "analyst")
    workflow.add_edge("yfinance_researcher", "analyst")
    workflow.add_edge("tradingview_researcher", "analyst")
    workflow.add_edge("analyst", "reporter")
    workflow.add_edge("reporter", END)

    return workflow.compile()

"""
This module defines the AgentState TypedDict, which serves as the shared memory
structure passed between nodes in the LangGraph workflow.
"""

from typing import TypedDict, Annotated, List
import operator
from langchain_core.messages import BaseMessage


class AgentState(TypedDict):
    """
    Shared state for the FinResearch AI graph.
    Attributes:
        messages: History of messages (not heavily used in this specific flow but standard for LangGraph).
        ticker: The stock ticker symbol being analyzed.
        dataset: (Optional) Intermediate data store.
        research_summary: Aggregated text from researchers.
        financial_data: Structured JSON data (Chart, Metrics) from Reporter.
        analyst_verdict: Structured judgment (Score, Rec, Reason) from Analyst.
        final_report: The final markdown report.
        investor_mode: User preference (Bullish/Bearish/Neutral).
        agents_to_run: List of agents selected by Manager.
    """

    messages: Annotated[List[BaseMessage], operator.add]
    ticker: str
    resolved_ticker: str
    screener: str
    exchange: str
    research_summary: str
    financial_data: dict
    analyst_verdict: dict
    final_report: str
    investor_mode: str
    next_step: str
    agents_to_run: List[str]

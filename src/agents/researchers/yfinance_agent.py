"""
This module contains the YFinanceAgent, which retrieves fundamental financial data
(valuation, margins, price history) using the yfinance library.
"""

import yfinance as yf
import json
from langchain_core.messages import HumanMessage
from langchain_core.documents import Document
from ...memory import VectorMemory
from ...state import AgentState


class YFinanceAgent:
    """
    Retrieves and analyzes fundamental stock data using YFinance.
    Optimized: No longer uses LLM for self-summary; passes raw JSON to Analyst.
    """

    def __init__(self):
        self.memory = VectorMemory()

    def run(self, state: AgentState):
        """
        Executes data retrieval and storage.
        """
        ticker = state.get("ticker")
        resolved_ticker = state.get("resolved_ticker", ticker)

        # 1. Fetch Data
        stock = yf.Ticker(resolved_ticker)

        try:
            info = stock.info
            # Extract key metrics to minimize token usage / noise
            metrics = {
                "currentPrice": info.get("currentPrice"),
                "marketCap": info.get("marketCap"),
                "trailingPE": info.get("trailingPE"),
                "forwardPE": info.get("forwardPE"),
                "fiftyTwoWeekHigh": info.get("fiftyTwoWeekHigh"),
                "fiftyTwoWeekLow": info.get("fiftyTwoWeekLow"),
                "dividendYield": info.get("dividendYield"),
                "sector": info.get("sector"),
                "recommendationKey": info.get("recommendationKey"),
                "targetMeanPrice": info.get("targetMeanPrice"),
            }
            metrics_json = json.dumps(metrics, indent=2)
        except Exception as e:
            # We explicitly store an error indicator for the Analyst
            metrics_ref = {
                "error": f"YFinance fetch failed: {str(e)}",
                "status": "failed",
            }
            metrics_json = json.dumps(metrics_ref, indent=2)

        # 2. Store in Pinecone
        # Store raw data for Analyst to use precisely
        doc_raw = Document(
            page_content=f"Raw Financial Metrics:\n{metrics_json}",
            metadata={
                "source": "YFinance_Data",
                "ticker": ticker,
                "type": "raw_metrics",
            },
        )

        # We no longer store "YFinance_Commentary" as it was redundant
        self.memory.add_documents([doc_raw], source="YFinance")

        return {
            "messages": [
                HumanMessage(content=f"YFinance Agent finished research for {ticker}.")
            ]
        }


def yfinance_node(state: AgentState):
    agent = YFinanceAgent()
    return agent.run(state)

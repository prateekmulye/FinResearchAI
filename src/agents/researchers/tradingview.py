"""
This module contains the TradingViewAgent, which retrieves technical analysis indicators
(RSI, MACD, Moving Averages) using the tradingview-ta library.
"""

import json
from tradingview_ta import TA_Handler, Interval
from langchain_core.messages import HumanMessage
from langchain_core.documents import Document
from ...memory import VectorMemory
from ...state import AgentState


class TradingViewAgent:
    """
    Retrieves and analyzes technical indicators using TradingView TA.
    Optimized: No longer uses LLM for self-summary; passes raw JSON to Analyst.
    """

    def __init__(self):
        self.memory = VectorMemory()

    def run(self, state: AgentState):
        """
        Executes technical analysis retrieval and storage.
        """
        ticker = state.get("ticker")
        screener = state.get("screener", "america")
        exchange = state.get("exchange", "NASDAQ")

        # 1. Fetch Technicals
        technicals = {}
        try:
            handler = TA_Handler(
                symbol=ticker,
                screener=screener,
                exchange=exchange,
                interval=Interval.INTERVAL_1_DAY,
            )
            analysis = handler.get_analysis()

            technicals = {
                "summary": analysis.summary,
                "indicators": {
                    "RSI": analysis.indicators.get("RSI"),
                    "MACD": analysis.indicators.get("MACD.macd"),
                    "SMA20": analysis.indicators.get("SMA20"),
                    "EMA20": analysis.indicators.get("EMA20"),
                    "Open": analysis.indicators.get("open"),
                    "Close": analysis.indicators.get("close"),
                },
                "exchange": exchange,
                "screener": screener,
            }
        except Exception as e:
            # Fallback for resiliency if manager was slightly off
            if exchange != "NASDAQ":
                try:
                    handler = TA_Handler(
                        symbol=ticker,
                        screener="america",
                        exchange="NASDAQ",
                        interval=Interval.INTERVAL_1_DAY,
                    )
                    analysis = handler.get_analysis()
                    technicals = {
                        "summary": analysis.summary,
                        "indicators": {"RSI": analysis.indicators.get("RSI")},
                    }
                except Exception:
                    technicals = {
                        "error": f"Technical analysis failed for {ticker}: {str(e)}"
                    }
            else:
                technicals = {"error": f"Technical analysis failed: {str(e)}"}

        technicals_json = json.dumps(technicals, indent=2)

        # 2. Store in Pinecone
        doc_raw = Document(
            page_content=f"Raw Technicals:\n{technicals_json}",
            metadata={
                "source": "TradingView_Technicals",
                "ticker": ticker,
                "type": "raw_technicals",
            },
        )

        # We no longer store "TradingView_Analysis" as it was redundant
        self.memory.add_documents([doc_raw], source="TradingView")

        return {
            "messages": [
                HumanMessage(
                    content=f"TradingView Agent finished research for {ticker}."
                )
            ]
        }


def tradingview_node(state: AgentState):
    agent = TradingViewAgent()
    return agent.run(state)

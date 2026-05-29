"""
This module contains the ManagerAgent, which acts as the orchestrator of the system.
It checks for cached data and determines which research sub-agents to activate.
"""

import time
import json
from langchain_core.messages import HumanMessage
from langchain_openai import ChatOpenAI
from langchain_core.prompts import ChatPromptTemplate
from ..state import AgentState
from ..memory import VectorMemory

# Thresholds for cache freshness in minutes
FRESH_THRESHOLD_MINS = 5
STALE_THRESHOLD_MINS = 60


class ManagerAgent:
    """
    The Manager Agent decides the execution plan based on cache freshness and user intent.
    """

    def __init__(self):
        self.llm = ChatOpenAI(model="gpt-4o-mini")
        self.memory = VectorMemory()

    def _get_recency(self, ticker: str, data_type: str):
        """Helper to check recency of a specific data type, picking the most recent version."""
        filter_dict = {"ticker": ticker, "type": data_type}
        # Fetch multiple to avoid picking up corrupt/old entries without timestamps
        results = self.memory.similarity_search(
            f"{data_type} for {ticker}", k=5, filter=filter_dict
        )

        timestamps = []
        for r in results:
            ts = r.metadata.get("timestamp")
            if ts is not None:
                try:
                    timestamps.append(float(ts))
                except (ValueError, TypeError):
                    continue

        if timestamps:
            max_ts = max(timestamps)
            diff_mins = (time.time() - max_ts) / 60
            return diff_mins
        return None

    def run(self, state: AgentState):
        """
        Orchestrates research by inventorying existing data and deciding which agents to run.
        """
        ticker = state.get("ticker")
        mode = state.get("investor_mode", "Neutral")

        print(f"--- Manager Agent: Competent Orchestration for {ticker} ---")

        # 1. Audit Cache Inventory
        inventory = {
            "final_verdict": self._get_recency(ticker, "final_verdict"),
            "news_analysis": self._get_recency(ticker, "news_analysis"),
            "financials": self._get_recency(ticker, "financials"),
            "technicals": self._get_recency(ticker, "technicals"),
        }

        # Immediate shortcut: If full verdict is fresh, skip all.
        if (
            inventory["final_verdict"] is not None
            and inventory["final_verdict"] < FRESH_THRESHOLD_MINS
        ):
            print("Fresh final verdict found. Skipping all research.")
            return {
                "messages": [HumanMessage(content="Using fresh cached research.")],
                "agents_to_run": [],
            }

        # 2. Build Inventory Context for LLM
        def format_status(mins):
            if mins is None:
                return "MISSING"
            if mins < FRESH_THRESHOLD_MINS:
                return f"FRESH ({mins:.1f}m old)"
            if mins < STALE_THRESHOLD_MINS:
                return f"STALE ({mins:.1f}m old)"
            return f"EXPIRED ({mins/60:.1f}h old)"

        audit_log = "\n".join(
            [f"- {k}: {format_status(v)}" for k, v in inventory.items()]
        )
        print(f"Cache Inventory:\n{audit_log}")

        # 3. Competent Decision Logic
        system_prompt = """You are an Expert Research Manager.
        Determine which researchers to activate for {ticker} based on the Cache Inventory.
        
        Available Agents:
        - 'tavily_researcher': Latest News & Sentiment.
        - 'yfinance_researcher': Fundamentals (P/E, Growth, Dividends).
        - 'tradingview_researcher': Technical Indicators (RSI, MACD).
        
        Rules:
        1. Only run an agent if its data is MISSING, STALE (> {FRESH_THRESHOLD_MINS}m), or EXPIRED.
        2. If multiple data types are needed for a comprehensive analysis, enable all necessary agents.
        3. Be efficient: Do not run agents for data that is already FRESH.
        
        Cache Inventory:
        {audit_log}
        
        User Tone/Mode: {mode}
        
        Output strictly JSON:
        {{
            "plan": "Short strategic explanation of why specific agents were chosen.",
            "agents_to_run": ["agent_name1", "agent_name2"]
        }}
        """

        prompt = ChatPromptTemplate.from_messages(
            [("system", system_prompt), ("user", f"Orchestrate research for {ticker}.")]
        )

        chain = prompt | self.llm
        response = chain.invoke(
            {
                "ticker": ticker,
                "mode": mode,
                "audit_log": audit_log,
                "FRESH_THRESHOLD_MINS": FRESH_THRESHOLD_MINS,
            }
        )

        try:
            content = response.content.replace("```json", "").replace("```", "").strip()
            decision = json.loads(content)
            plan_text = decision.get("plan", "Proceeding with tailored research.")
            agents_to_run = decision.get("agents_to_run", [])
        except Exception as e:
            print(f"Error parsing Manager JSON: {e}")
            plan_text = "Error in decision logic, falling back to full run."
            agents_to_run = [
                "tavily_researcher",
                "yfinance_researcher",
                "tradingview_researcher",
            ]

        print(f"Manager Decision: Run {agents_to_run}")

        # 4. Resolve Ticker & Exchange Metadata
        # We use the LLM to help resolve the best screener/exchange for TradingView and suffix for YFinance
        resolution_prompt = """You are a Financial Data Router.
        Resolve the correct metadata for the ticker: {ticker}
        
        Exchanges to prioritize:
        - USA: NASDAQ, NYSE, AMEX (Screener: 'america')
        - India: NSE, BSE (Screener: 'india', YFinance Suffix: '.NS', '.BO')
        - Japan: TSE (Screener: 'japan', YFinance Suffix: '.T')
        - China: SSE, SZSE (Screener: 'china', YFinance Suffix: '.SS', '.SZ')
        - Hong Kong: HKEX (Screener: 'hongkong', YFinance Suffix: '.HK')
        
        Output strictly JSON:
        {{
            "resolved_ticker": "Ticker with suffix if needed",
            "screener": "tradingview_screener_name",
            "exchange": "tradingview_exchange_name"
        }}
        """

        res_chain = ChatPromptTemplate.from_template(resolution_prompt) | self.llm
        res_resp = res_chain.invoke({"ticker": ticker})

        try:
            res_content = (
                res_resp.content.replace("```json", "").replace("```", "").strip()
            )
            meta = json.loads(res_content)
            resolved_ticker = meta.get("resolved_ticker", ticker)
            screener = meta.get("screener", "america")
            exchange = meta.get("exchange", "NASDAQ")
        except Exception:
            resolved_ticker = ticker
            screener = "america"
            exchange = "NASDAQ"

        print(f"Resolved: {resolved_ticker} on {exchange} ({screener})")

        return {
            "messages": [HumanMessage(content=f"Manager Plan: {plan_text}")],
            "agents_to_run": agents_to_run,
            "resolved_ticker": resolved_ticker,
            "screener": screener,
            "exchange": exchange,
        }


def manager_node(state: AgentState):
    agent = ManagerAgent()
    return agent.run(state)

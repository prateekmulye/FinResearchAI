"""
This module contains the TavilyAgent, which performs web searches to find
recent news and market sentiment data.
"""

import json
from langchain_openai import ChatOpenAI
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.messages import HumanMessage
from langchain_core.documents import Document
from langchain_tavily import TavilySearch
from ...memory import VectorMemory
from ...state import AgentState


class TavilyAgent:
    """
    Performs web search using Tavily API to gather news and sentiment.
    """

    def __init__(self):
        self.memory = VectorMemory()
        self.llm = ChatOpenAI(model="gpt-4o-mini")
        self.tool = TavilySearch(max_results=5)

    def run(self, state: AgentState):
        """
        Executes the search, analysis, and storage of news data.
        """
        ticker = state.get("ticker")

        # 1. Search
        try:
            # Removed the specific 'past 24 hours' promise from query string
            results = self.tool.invoke(
                f"latest company news and stock market sentiment for {ticker}"
            )
        except Exception:
            results = []

        # Handle parsed output
        if isinstance(results, str):
            try:
                parsed = json.loads(results)
                if isinstance(parsed, list):
                    results = parsed
                else:
                    results = [{"url": "tavily_search", "content": results}]
            except Exception:
                results = [{"url": "tavily_search", "content": results}]
        elif isinstance(results, dict):
            if "results" in results:
                results = results["results"]
            else:
                results = [{"url": "tavily_search", "content": str(results)}]

        # 2. Summarize & Sentiment with LLM
        raw_text = "\n\n".join(
            [
                f"Source: {r.get('url', 'unknown')}\nContent: {r.get('content', '')}"
                for r in results
            ]
        )

        system_prompt = """You are an Expert Financial News Researcher.
        Analyze the provided search results for {ticker}.
        
        Output a concise summary focusing on:
        1. Key recent events (earnings, product launches, regulatory).
        2. Market sentiment (Bullish/Bearish/Neutral).
        3. Potential risks.
        
        Be strictly factual and concise.
        """

        prompt = ChatPromptTemplate.from_messages(
            [("system", system_prompt), ("user", "News Data:\n{news}")]
        )

        chain = prompt | self.llm
        analysis = chain.invoke({"ticker": ticker, "news": raw_text})

        # 3. Store in Pinecone
        doc_raw_news = Document(
            page_content=f"Raw News Results for {ticker}:\n{raw_text}",
            metadata={
                "source": "Tavily_News_Raw",
                "ticker": ticker,
                "type": "raw_news",
            },
        )
        doc_news_analysis = Document(
            page_content=analysis.content,
            metadata={
                "source": "Tavily_News_Analysis",
                "ticker": ticker,
                "type": "news_analysis",
            },
        )

        self.memory.add_documents(
            [doc_raw_news, doc_news_analysis], source="Tavily_News"
        )

        return {
            "messages": [
                HumanMessage(content=f"Tavily Agent finished research for {ticker}.")
            ]
        }


def tavily_node(state: AgentState):
    agent = TavilyAgent()
    return agent.run(state)

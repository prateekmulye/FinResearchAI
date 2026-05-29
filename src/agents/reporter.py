"""
This module contains the ReportingAgent, which is responsible for synthesizing the final
analysis into a readable Markdown report and generating structured data for UI visualizations.
"""

import json
import re
from langchain_core.messages import HumanMessage
from langchain_openai import ChatOpenAI
from langchain_core.prompts import ChatPromptTemplate
from ..memory import VectorMemory
from ..state import AgentState


class ReportingAgent:
    """
    Generates the final financial report and data for charts.
    """

    def __init__(self):
        self.memory = VectorMemory()
        self.llm = ChatOpenAI(model="gpt-4o-mini")

    def run(self, state: AgentState):
        """
        Executes the reporting phase:
        1. Fetches all relevant context from memory.
        2. Prompts the LLM to write a MD report and JSON data.
        3. Extracts JSON for the frontend.
        """
        print("--- Reporting Agent: Synthesizing Output ---")
        ticker = state.get("ticker")
        mode = state.get("investor_mode", "Neutral")

        # 1. Retrieve Context
        results = self.memory.similarity_search(
            f"Analyst Verdict and full research for {ticker}", k=10
        )

        context_text = ""
        for doc in results:
            source = doc.metadata.get("source", "unknown")
            context_text += f"-- Source: {source} --\n{doc.page_content}\n\n"

        # 2. Generate Report & Graph Data
        system_prompt = """You are a professional Financial Reporter.
        Based on the provided research context (especially the Analyst Verdict) for {ticker} ({mode} mode).
        
        Task 1: Write a professional Markdown Report.
        Structure:
        # Financial Report: {ticker}
        ## 1. Executive Summary (≤150 words)
        ## 2. Analyst Verdict (Score & Rec)
        ## 3. Company Snapshot
        ## 4. Key Financial Indicators 
        ## 5. Technical Signals
        ## 6. Recent News & Sentiment
        ## 7. Risks & Opportunities
        ## 8. Final Perspective
        
        Task 2: Generate JSON Data for Visualization.
        At the VERY END of your response, strictly inside a single ```json``` block, provide data for the UI.
        Structure:
        ```json
        {{
            "metrics": [
                {{ "Metric": "Market Cap", "Value": "2.5T" }},
                {{ "Metric": "P/E Ratio", "Value": "35.5" }},
                {{ "Metric": "Revenue Growth", "Value": "+15%" }},
                {{ "Metric": "Profit Margin", "Value": "25%" }}
            ], # STRICTLY PROVIDE TOP 4 METRICS ONLY
            "chart": {{
                "type": "radar",
                "title": "Financial Health Radar",
                "data": {{
                    "Valuation": 7,
                    "Growth": 6,
                    "Profitability": 8,
                    "Price Action": 5,
                    "Sentiment": 9
                }}
            }}
        }}
        ```
        """

        prompt = ChatPromptTemplate.from_messages(
            [("system", system_prompt), ("user", "Context Data:\n{context}")]
        )

        chain = prompt | self.llm
        full_output = chain.invoke(
            {"ticker": ticker, "mode": mode, "context": context_text}
        ).content

        # 3. Extract JSON Graph Data
        graph_data = {}
        json_match = re.search(r"```json\n(.*?)\n```", full_output, re.DOTALL)
        if json_match:
            try:
                graph_data = json.loads(json_match.group(1))
                # Remove the JSON block from the readable report
                report_content = full_output.replace(json_match.group(0), "").strip()
            except Exception as e:
                print(f"Failed to parse graph JSON: {e}")
                report_content = full_output
        else:
            report_content = full_output

        # Add Humorous Watermark
        watermark = "\n\n---\n*Dashboard certified: 100% Organic Alpha. Strictly Non-Advisory. Jerome Powell was not consulted during this research.* 🕵️‍♂️📈"
        report_content += watermark

        return {
            "final_report": report_content,
            "financial_data": graph_data,
            "messages": [HumanMessage(content=f"Report generated for {ticker}.")],
        }


def reporter_node(state: AgentState):
    agent = ReportingAgent()
    return agent.run(state)

"""
This module contains the AnalystAgent, which is responsible for aggregating research data,
performing quality control, and generating a quantitative score and recommendation.
"""

import json
import logging
from langchain_openai import ChatOpenAI
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.messages import HumanMessage
from langchain_core.documents import Document
from ..memory import VectorMemory
from ..state import AgentState

logger = logging.getLogger("FinResearchAI.Analyst")


class AnalystAgent:
    """
    Acts as the Lead Analyst.
    Aggregates data from shared memory (Pinecone), performs QC, and scores the asset.
    """

    def __init__(self):
        self.memory = VectorMemory()
        self.llm = ChatOpenAI(model="gpt-4o-mini")

    def run(self, state: AgentState):
        """
        Executes the analysis logic:
        1. Retrieve context from memory.
        2. Synthesize, QC, and Score in a single LLM call for maximum performance.
        3. Store result back to memory.
        """
        logger.info("--- Analyst Agent (Aggregation & Scoring) ---")
        ticker = state.get("ticker")
        mode = state.get("investor_mode", "Neutral")

        # 1. Retrieve Context
        results = self.memory.similarity_search(
            f"financial data, news, and technicals for {ticker}", k=15
        )

        context_data = ""
        for doc in results:
            source = doc.metadata.get("source", "unknown")
            context_data += f"-- Source: {source} --\n{doc.page_content}\n\n"

        if not context_data:
            context_data = "No data available."

        # 2. Unified Aggregation, QC, and Scoring
        system_prompt = """You are an Expert Senior Lead Financial Analyst.
        Review the gathered research data for {ticker} and the requested investor mode: {mode}.
        
        Input Context:
        - RAW JSON from 'YFinance' (Fundamentals) and 'TradingView' (Technicals).
        - Unstructured text from 'Tavily' (News).
        
        Your Goal: 
        1. Sanity Check: Identify any conflicting data points.
        2. Aggregation: Synthesize a coherent narrative.
        3. Quantitative Verdict: Score the asset (0-100) and provide a recommendation.
        
        Execution:
        Provide a concise 'Aggregated_View' narrative and a structured 'Verdict'.
        
        Output format must be strictly JSON:
        {{
            "aggregated_view": "Coherent synthesis and sanity check results (2-3 paragraphs).",
            "verdict": {{
                "score": <0-100 integer>,
                "recommendation": "<Buy|Sell|Hold>",
                "reasoning": "<Concise 2-sentence explanation>"
            }}
        }}
        """

        prompt = ChatPromptTemplate.from_messages(
            [("system", system_prompt), ("user", "Research Data:\n{data}")]
        )

        chain = prompt | self.llm
        response = chain.invoke(
            {"ticker": ticker, "mode": mode, "data": context_data}
        ).content

        # Parse JSON output
        verdict_data = {}
        aggregated_view = "No aggregated view generated."
        try:
            clean_response = response.replace("```json", "").replace("```", "").strip()
            parsed = json.loads(clean_response)
            verdict_data = parsed.get("verdict", {})
            aggregated_view = parsed.get("aggregated_view", "Analysis completed.")

            # Validate verdict has required fields
            if not verdict_data.get("score"):
                logger.warning(f"No score in verdict, using default. Verdict: {verdict_data}")
                verdict_data["score"] = 50  # Default neutral score

            if not verdict_data.get("recommendation"):
                logger.warning("No recommendation in verdict, using 'Hold'")
                verdict_data["recommendation"] = "Hold"

            if not verdict_data.get("reasoning"):
                logger.warning("No reasoning in verdict, using default text")
                verdict_data["reasoning"] = "Unable to extract reasoning from analysis."

            logger.info(f"Successfully parsed analyst verdict: score={verdict_data.get('score')}, rec={verdict_data.get('recommendation')}")

        except Exception as e:
            logger.error(f"Error parsing Analyst JSON: {e}")
            logger.debug(f"Raw response: {response[:500]}...")  # Log first 500 chars for debugging
            # Fallback: Create default verdict
            aggregated_view = response[:500] if len(response) > 500 else response
            verdict_data = {
                "score": 50,
                "recommendation": "Hold",
                "reasoning": "JSON parsing failed, defaulting to neutral verdict."
            }
            logger.warning("Using fallback verdict with score=50")

        # 3. Store Verdict
        doc_verdict = Document(
            page_content=f"Analyst Verdict:\n{json.dumps(verdict_data, indent=2)}\n\nAggregated View:\n{aggregated_view}",
            metadata={
                "source": "Analyst_Verdict",
                "ticker": ticker,
                "type": "final_verdict",
            },
        )
        self.memory.add_documents([doc_verdict], source="Analyst")

        return {
            "analyst_verdict": verdict_data,
            "messages": [
                HumanMessage(content=f"Analyst Verdict: {json.dumps(verdict_data)}")
            ],
        }


def analyst_node(state: AgentState):
    agent = AnalystAgent()
    return agent.run(state)

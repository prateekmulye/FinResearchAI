import os
import sys
import argparse
from dotenv import load_dotenv

# Add src to python path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.graph import create_graph
from src.memory import VectorMemory

load_dotenv()


def test_flow(ticker="MSFT"):
    print(f"--- Running Verification Test for {ticker} ---")

    # 1. Run Graph
    app = create_graph()
    initial_state = {
        "ticker": ticker,
        "messages": [],
        "research_summary": "",
        "financial_data": {},
        "final_report": "",
        "next_step": "",
    }

    print("Invoking Graph...")
    # Invoke runs until end
    final_output = app.invoke(initial_state)

    print("\n--- Graph Execution Completed ---")

    # 2. Verify Report
    report = final_output.get("final_report", "")
    if report and len(report) > 100:
        print("✅ Final Report Generated Successfully")
        print(f"Report length: {len(report)} chars")
        print("\n--- Report Tail (Watermark Check) ---")
        print(report[-300:])
    else:
        print("❌ Final Report MISSING or too short")

    # 3. Verify Pinecone Content (Still good to check)
    memory = VectorMemory()
    print("\nVerifying Pinecone Content...")

    query = f"financial info for {ticker}"
    results = memory.similarity_search(query, k=5)

    found_news = False
    found_financials = False

    print(f"Query Results for '{query}':")
    for doc in results:
        meta = doc.metadata
        source = meta.get("source", "unknown")

        print(f"- [Source: {source}] Text snippet: {doc.page_content[:50]}...")

        if source == "researcher_agent_summary" or source == "tavily_search":
            found_news = True
        if source == "analyst_agent" or source == "yfinance":
            found_financials = True

    if found_news:
        print("✅ Found News/Summary Documents")
    else:
        print("⚠️ No News/Summary Documents found in top 5 results.")

    if found_financials:
        print("✅ Found Financial Analysis Documents")
    else:
        print("⚠️ No Financial Analysis Documents found in top 5 results.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--ticker", type=str, default="MSFT")
    args = parser.parse_args()
    test_flow(args.ticker)

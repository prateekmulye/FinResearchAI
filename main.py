import argparse
import sys
import os

# Add src to python path to ensure imports work correctly when running from any location
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from src.graph import create_graph


def main():
    parser = argparse.ArgumentParser(description="FinResearch AI")
    parser.add_argument(
        "--ticker", type=str, required=True, help="Stock ticker to research (e.g. AAPL)"
    )
    args = parser.parse_args()

    ticker = args.ticker

    app = create_graph()

    initial_state = {
        "ticker": ticker,
        "messages": [],
        "research_summary": "",
        "financial_data": {},
        "next_step": "",
    }

    # Run the graph
    final_state = {}
    for output in app.stream(initial_state):
        for key, value in output.items():
            # The streaming output contains the state update from that node
            # We want to capture the accumulated state, which isn't directly returned in simple stream mode
            # But the value returned IS the update.
            # Ideally we'd use app.invoke for a single final result, but stream gives us progress.
            # For simplicity in this demo, let's just use the last output chunk's update
            # assuming the reporter is the last one and returns 'final_report'
            if "final_report" in value:
                final_state.update(value)

    # Print Final Report
    final_report = final_state.get("final_report", "No report generated. check logs.")
    print(final_report)


if __name__ == "__main__":
    main()

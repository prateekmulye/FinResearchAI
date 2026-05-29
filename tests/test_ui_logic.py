import sys
import os

# Add src to path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app import run_research


def test_ui_logic():
    print("--- Testing UI Logic Headless ---")
    ticker = "MSFT"
    mode = "Bullish"

    # Run logic
    print(f"Invoking run_research({ticker}, {mode})...")

    md_file = None
    json_file = None

    try:
        # Mocking gr.Request as None for headless test
        outputs = run_research(ticker, mode, None)

        # Unpack outputs (note: matching the 10 outputs of the refactored app.py)
        (
            report,
            summary,
            snapshot,
            news,
            risks,
            md_file,
            json_file,
            viz,
            metrics,
            verdict,
        ) = outputs

        print("\n--- Verification ---")

        # 1. Check Report Content
        if len(report) > 100:
            print("✅ Report generated")
        else:
            print("❌ Report generation failed or empty")

        # 2. Check Parsing (Sections)
        if summary != "No summary available.":
            print("✅ 'Executive Summary' parsed")
        else:
            print("⚠️ 'Executive Summary' NOT parsed")

        # 3. Check Files
        if os.path.exists(md_file):
            print(f"✅ Markdown file created: {md_file}")
        else:
            print(f"❌ Markdown file missing: {md_file}")

        if os.path.exists(json_file):
            print(f"✅ JSON file created: {json_file}")
        else:
            print(f"❌ JSON file missing: {json_file}")

    finally:
        # cleanup
        if md_file and os.path.exists(md_file):
            os.remove(md_file)
        if json_file and os.path.exists(json_file):
            os.remove(json_file)


if __name__ == "__main__":
    test_ui_logic()

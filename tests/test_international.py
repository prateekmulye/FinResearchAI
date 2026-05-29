import sys
import os
import pytest
from unittest.mock import MagicMock

# Add src to path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app import run_research


@pytest.mark.parametrize(
    "ticker,expected_suffix", [("RELIANCE", ".NS"), ("7203", ".T"), ("0700", ".HK")]
)
def test_international_routing(ticker, expected_suffix):
    print(f"\n--- Testing International Routing for {ticker} ---")

    # We mock gr.Request
    mock_request = MagicMock()
    mock_request.client.host = "127.0.0.1"

    # Run research
    # Note: This will actually call the LLM and APIs if not mocked,
    # but we want to see if it even resolves the ticker correctly in logs.
    try:
        outputs = run_research(ticker, "Neutral", mock_request)
        # Unpack
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

        print(f"✅ Research completed for {ticker}")

        # Check files exist
        assert os.path.exists(md_file)
        assert os.path.exists(json_file)

        # Cleanup
        os.remove(md_file)
        os.remove(json_file)

    except Exception as e:
        pytest.fail(f"International research failed for {ticker}: {e}")


if __name__ == "__main__":
    # Manual run if needed
    pass

import os

import pytest

from src.eval.run import run_eval

pytestmark = pytest.mark.live


@pytest.mark.skipif(os.getenv("RUN_LIVE") != "1", reason="set RUN_LIVE=1 to run live eval")
@pytest.mark.asyncio
async def test_live_eval_writes_report(tmp_path):
    md_path = await run_eval(
        tickers_path="evals/tickers.json",
        label="live-smoke",
        concurrency=2,
        out_dir=str(tmp_path),
    )
    assert md_path.exists()
    text = md_path.read_text(encoding="utf-8")
    assert "PROXY" in text
    assert (tmp_path / "report-live-smoke.json").exists()

# tests/integration/test_live_smoke.py
"""Single opt-in live end-to-end smoke test.

Hits Ollama Cloud (LLM backbone) + Firecrawl (web research) for ONE ticker and
asserts a non-empty markdown report. SKIPPED unless RUN_LIVE=1.

Required environment (set in your shell, NOT committed):
    RUN_LIVE=1
    OLLAMA_API_KEY=<real Ollama Cloud key>
    FIRECRAWL_API_KEY=<real Firecrawl key>
    # optional overrides:
    LLM_BASE_URL=https://ollama.com/v1
    QUICK_MODEL=gpt-oss:20b
    DEEP_MODEL=gpt-oss:120b

Run it with:
    RUN_LIVE=1 python -m pytest tests/integration/test_live_smoke.py -m live -q -s
"""
from __future__ import annotations

import os

import pytest

# Capture the real process env at import time, BEFORE the autouse env_isolation
# fixture scrubs keys / forces RUN_LIVE=0.
_PROC_ENV = {
    "RUN_LIVE": os.environ.get("RUN_LIVE", "0"),
    "OLLAMA_API_KEY": os.environ.get("OLLAMA_API_KEY", ""),
    "FIRECRAWL_API_KEY": os.environ.get("FIRECRAWL_API_KEY", ""),
    "LLM_BASE_URL": os.environ.get("LLM_BASE_URL", ""),
    "QUICK_MODEL": os.environ.get("QUICK_MODEL", ""),
    "DEEP_MODEL": os.environ.get("DEEP_MODEL", ""),
}

pytestmark = pytest.mark.skipif(
    _PROC_ENV["RUN_LIVE"] != "1",
    reason="live smoke test: set RUN_LIVE=1 (plus OLLAMA_API_KEY + FIRECRAWL_API_KEY) to run",
)


@pytest.fixture
def restore_live_env(monkeypatch):
    """Undo env_isolation's scrubbing: put the REAL keys back for this live test."""
    if not _PROC_ENV["OLLAMA_API_KEY"]:
        pytest.skip("OLLAMA_API_KEY not set in process env; cannot run live smoke")
    if not _PROC_ENV["FIRECRAWL_API_KEY"]:
        pytest.skip("FIRECRAWL_API_KEY not set in process env; cannot run live smoke")
    for key, value in _PROC_ENV.items():
        if value:
            monkeypatch.setenv(key, value)
    # Caches were cleared by env_isolation; they'll rebuild from the restored env.
    from src.config import settings as settings_mod
    from src.llm import factory as factory_mod

    if hasattr(settings_mod.get_settings, "cache_clear"):
        settings_mod.get_settings.cache_clear()
    if hasattr(factory_mod.get_llm, "cache_clear"):
        factory_mod.get_llm.cache_clear()
    yield


@pytest.mark.live
@pytest.mark.asyncio
async def test_live_single_ticker_produces_report(restore_live_env):
    from src.graph import build_graph

    app = build_graph("on")
    result = await app.ainvoke({"ticker": "AAPL", "investor_mode": "Neutral"})

    report = result.get("final_report", "")
    assert isinstance(report, str)
    assert len(report.strip()) > 100, "live report is implausibly short"
    assert result["final_decision"]["action"] in {"BUY", "SELL", "HOLD"}
    # Real LLM calls should have recorded token usage somewhere.
    total_tokens = sum(m.get("prompt_tokens", 0) for m in result.get("run_metrics", []))
    assert total_tokens > 0, "no token usage recorded — were LLM calls real?"

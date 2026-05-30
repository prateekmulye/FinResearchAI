"""Live probe for structured-output method support on the quick-tier model.

Run once locally (requires OLLAMA_API_KEY in .env):
    RUN_LIVE=1 python -m pytest tests/agents/test_struct_method_live.py -v -m live

If this test fails with a tool-calling/400 error, change STRUCT_METHOD to
"json_schema" in src/llm/factory.py (one place, propagates to all nodes).

Decision recorded: function_calling (STRUCT_METHOD default in factory.py).
Update this comment if the probe forces a fallback.
"""
import os

import pytest
from langchain_core.messages import HumanMessage

from src.agents.router import TickerResolution
from src.llm.factory import get_llm


@pytest.mark.live
@pytest.mark.skipif(os.getenv("RUN_LIVE") != "1", reason="set RUN_LIVE=1 for live LLM")
async def test_quick_model_supports_function_calling():
    """Verify the quick tier handles with_structured_output(method='function_calling').
    If this raises a 'tool calling not supported' / 400 error, change STRUCT_METHOD
    to 'json_schema' in src/llm/factory.py and re-run."""
    llm = get_llm("quick").with_structured_output(TickerResolution, method="function_calling")
    result = await llm.ainvoke([HumanMessage(content="Resolve the ticker for Apple Inc.")])
    assert isinstance(result, TickerResolution)
    assert result.resolved_ticker

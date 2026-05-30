# tests/agents/conftest.py
"""Shared fakes for WP-E node tests. No network: every LLM is a FakeStructuredLLM
that returns a pre-seeded Pydantic instance from .ainvoke, mirroring the real
get_llm(...).with_structured_output(Model).ainvoke(...) contract."""
from __future__ import annotations

import pytest


class FakeStructuredLLM:
    """Stands in for the runnable returned by with_structured_output(Model).

    .ainvoke(messages, config=...) returns the seeded model instance and records
    the messages + config it was called with for assertions.
    """

    def __init__(self, result):
        self._result = result
        self.calls: list[dict] = []

    async def ainvoke(self, messages, config=None):
        self.calls.append({"messages": messages, "config": config})
        return self._result


class FakeBaseLLM:
    """Stands in for get_llm('deep'). .with_structured_output(...) returns a
    FakeStructuredLLM seeded with the next queued result."""

    def __init__(self, results: list):
        self._results = list(results)
        self.structured: list[FakeStructuredLLM] = []
        self.structured_args: list[dict] = []

    def with_structured_output(self, schema, method="function_calling"):
        self.structured_args.append({"schema": schema, "method": method})
        result = self._results.pop(0)
        fake = FakeStructuredLLM(result)
        self.structured.append(fake)
        return fake


@pytest.fixture
def make_fake_llm():
    """Returns a factory: make_fake_llm([result1, result2, ...]) -> FakeBaseLLM."""
    def _factory(results):
        return FakeBaseLLM(results)
    return _factory

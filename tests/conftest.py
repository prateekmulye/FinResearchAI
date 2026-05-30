# tests/conftest.py
"""Shared test fixtures for WP-D (and downstream WPs).

``make_structured_llm`` produces a scripted fake LLM whose
``.with_structured_output(...).ainvoke(...)`` yields prepared Pydantic objects in
order and fires LangChain callbacks so CostTracker records one entry per call.

``fake_llm_factory`` is a pytest fixture that installs such an LLM via monkeypatch.
"""
from __future__ import annotations

import importlib
from types import SimpleNamespace
from typing import Any

import pytest

from src.llm.schemas import AnalystReport, DebateTurn

# ---------------------------------------------------------------------------
# Schema registry — only schemas listed here are accepted by the fake LLM.
# Adding a new schema to production code requires registering it here too;
# an unregistered schema raises KeyError loudly so missing mappings are caught
# immediately rather than silently returning None or a wrong default.
# ---------------------------------------------------------------------------
_KNOWN_SCHEMAS: frozenset = frozenset({
    DebateTurn,
    AnalystReport,
})


def make_structured_llm(outputs: list[Any]):
    """Return a fake LLM whose .with_structured_output(...).ainvoke(...) yields
    the prepared outputs in order. Each ainvoke fires the CostTracker callbacks
    so per-node metrics are recorded with realistic token counts.
    """
    queue = list(outputs)
    call_counter = [0]

    class _Structured:
        async def ainvoke(self, messages, config=None, **kwargs):
            call_counter[0] += 1
            rid = f"run-{call_counter[0]}"
            callbacks = (config or {}).get("callbacks", []) or []
            for cb in callbacks:
                if hasattr(cb, "on_llm_start"):
                    cb.on_llm_start({}, ["<prompt>"], run_id=rid)
            result = queue.pop(0)
            response = SimpleNamespace(
                llm_output={
                    "token_usage": {"prompt_tokens": 10, "completion_tokens": 5},
                    "model_name": "fake-deep",
                }
            )
            # Simulate a tiny delay so latency_s > 0 doesn't confuse assertions.
            for cb in callbacks:
                if hasattr(cb, "on_llm_end"):
                    cb.on_llm_end(response, run_id=rid)
            return result

    class _LLM:
        def with_structured_output(self, schema, method="function_calling"):
            # F6: raise loudly for schemas not in the registry so missing
            # mappings fail immediately rather than silently returning wrong data.
            if schema not in _KNOWN_SCHEMAS:
                raise KeyError(
                    f"conftest: no canned instance registered for {schema}"
                )
            return _Structured()

    return _LLM()


@pytest.fixture
def fake_llm_factory(monkeypatch):
    """Patch get_llm everywhere it is imported so nodes receive a scripted LLM.

    Usage::

        fake_llm_factory([turn1, turn2, ...], ["src.agents.debate", "src.agents.research.bull"])

    Patches ``src.llm.factory.get_llm`` and each named module's ``get_llm`` attribute.
    """

    def _install(outputs: list[Any], modules: list[str]) -> Any:
        llm = make_structured_llm(outputs)
        import src.llm.factory as factory_mod

        monkeypatch.setattr(factory_mod, "get_llm", lambda tier: llm)
        for mod_path in modules:
            mod = importlib.import_module(mod_path)
            if hasattr(mod, "get_llm"):
                monkeypatch.setattr(mod, "get_llm", lambda tier, _llm=llm: _llm)
        return llm

    return _install

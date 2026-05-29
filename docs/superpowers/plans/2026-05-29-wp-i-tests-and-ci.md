# WP-I: Integration Tests, CI & Legacy Cleanup Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Close the "has tests but hollow" + "no CI" + "dependency hygiene" defects from the codebase assessment. Provide shared test fixtures, a real "the whole system composes" mocked end-to-end integration test for both debate modes, a single opt-in live smoke test, a CI pipeline (lint + type-check + mocked tests on a py3.11/py3.13 matrix), finalized pinned dependency groups, and the guarded deletion of every legacy module once its replacement has merged.

**Architecture:** Integration tests drive the *real* compiled `build_graph("on")` / `build_graph("off")` topology with ALL LLM calls mocked through a single `fake_llm` factory fixture that patches `src.llm.factory.get_llm`, and all tool SDKs monkeypatched at their seams. This proves composition without any network. A `live` pytest marker (registered in `pyproject.toml`, deselected by default via `-m "not live"`) gates the one real-network smoke test behind `RUN_LIVE=1`. CI runs `ruff check`, `mypy src` (lenient), and `pytest -q -m "not live"`. Legacy removal is a single guarded task that runs only after all node-owning WPs (B–H) have merged their replacements, verified by a regression test (`tests/test_legacy_removed.py`) that asserts the old modules no longer exist or import.

**Tech Stack:** Python 3.11 + 3.13 (CI matrix), `pytest==8.4.2`, `pytest-asyncio>=0.24`, `respx>=0.21`, `ruff>=0.6`, `mypy>=1.11`, `pytest-cov>=5.0` (optional gate), GitHub Actions (`actions/checkout@v6`, `actions/setup-python@v6` with `cache: pip`).

---

## Context for the implementer

This is the final work package in the agentic re-architecture. It owns the cross-cutting test harness, CI, dependency finalization, and legacy deletion. It codes ONLY against the frozen contract from `2026-05-29-foundation-and-state-contract.md` and the ownership map in `docs/superpowers/plans/COORDINATION.md` §3. Read both before starting.

Important environment facts (verified at planning time):
- The active dir `FinResearchAI/` is **not yet a git repo of its own** — the Foundation plan's Task 1 is expected to `git init` it (or it is initialized as part of the repo root). All `git rm` / `git add` commands below assume git is initialized and the Foundation + WP branches have merged. If git is not yet initialized when you reach the legacy-removal task, run `git init` first and `git add -A` the new tree before the removals.
- The legacy modules to remove are: `src/agents/manager.py`, `src/agents/analyst.py`, `src/agents/reporter.py`, `src/agents/researchers/{tavily,yfinance_agent,tradingview}.py`, `src/memory.py` (the OLD Pinecone one), `tests/test_flow.py`, `tests/test_international.py`, `tests/test_ui_logic.py`, `main.py`, `app.py`, and the unpinned `requirements.txt` (lists deprecated `pinecone-client`).
- The NEW replacements (per ownership map) are: `src/agents/router.py`, `src/agents/analysts/*`, `src/tools/*` (WP-B); `src/memory/*` (WP-C); `src/agents/research/*` + `src/agents/debate.py` (WP-D); `src/agents/{trader.py}` + `src/agents/risk/*` (WP-E); `src/agents/reporter.py` (WP-F, NEW path overwrites old); `src/api/*` + `web/*` (WP-G, the new entry point replacing `app.py`/`main.py`).

**No network in any test except the one `@pytest.mark.live` smoke.** The fake_llm fixture and tool monkeypatching are the backbone — get them right in Task 2 and everything else follows.

## File Structure

| File | Responsibility |
|---|---|
| `pyproject.toml` | Finalize optional-dependency groups (pinned), register the `live` marker, set `-m "not live"` default deselect, optional coverage config |
| `tests/conftest.py` | Shared fixtures: `fake_llm` factory (patches `get_llm`), `frozen_state` builder, env isolation autouse fixture |
| `tests/integration/__init__.py` | Package marker for the integration test package |
| `tests/integration/test_full_graph_mocked.py` | Real `build_graph("on")` + `build_graph("off")` end-to-end, all LLM + tool SDKs mocked; asserts coherent report/decision + metric counts |
| `tests/integration/test_live_smoke.py` | Single `@pytest.mark.live` real-network test (Ollama Cloud + Firecrawl), skipped unless `RUN_LIVE=1` |
| `tests/test_legacy_removed.py` | Guards the cleanup: asserts legacy modules are deleted / non-importable |
| `tests/test_coverage_gate.py` | Optional sanity check that `pytest-cov` is configured (coverage threshold note) |
| `.github/workflows/ci.yml` | GitHub Actions: py3.11 + py3.13 matrix, install `.[all]`, `ruff check`, `mypy src`, `pytest -q -m "not live"`, pip cache |
| `requirements.txt` | **DELETED** in the cleanup task (replaced by pinned pyproject groups) |
| Legacy `src/agents/*`, `src/memory.py`, `main.py`, `app.py`, old `tests/test_*` | **DELETED** in the guarded cleanup task |

---

### Task 1: Finalize dependency groups + register the `live` marker

The Foundation `pyproject.toml` left optional-dependency groups commented out and added the `dev` group. WP-I finalizes ALL groups (pinned, verified against the versions other WPs declared), adds an aggregate `all` group for CI, registers the `live` pytest marker (so `-m "not live"` produces no `PytestUnknownMarkWarning`), makes `-m "not live"` the default deselect, and adds the optional coverage config.

**Files:**
- Modify: `pyproject.toml`

- [ ] **Step 1: Read the current `pyproject.toml`**

Run: `python -c "import tomllib,sys; print(tomllib.load(open('pyproject.toml','rb')).keys())"`
Expected: prints the top-level tables (`project`, `tool`, ...). Confirms Foundation Task 1 merged. If this fails with `FileNotFoundError`, the Foundation plan has not merged — STOP and resolve the dependency (see `## Dependencies`).

- [ ] **Step 2: Replace `[project.optional-dependencies]` with the finalized, pinned groups**

Replace the entire `[project.optional-dependencies]` block (the one with the commented-out `# memory = ...` lines plus the `dev` group) with this. Each group's versions match what the owning WP declared in its plan's first task; the `all` group is the union CI installs.

```toml
[project.optional-dependencies]
memory = [
    "chromadb>=0.5,<0.6",
    "fastembed>=0.4,<0.5",
]
web = [
    "firecrawl-py>=1.6,<2.0",
]
data = [
    "yfinance==0.2.66",
    "tradingview-ta==3.3.0",
    "pandas>=2.2,<3.0",
]
api = [
    "fastapi>=0.115,<1.0",
    "uvicorn>=0.30,<1.0",
    "sse-starlette>=2.1,<3.0",
    "httpx>=0.27,<1.0",
]
dev = [
    "pytest==8.4.2",
    "pytest-asyncio>=0.24,<1.0",
    "pytest-cov>=5.0,<7.0",
    "respx>=0.21,<1.0",
    "ruff>=0.6,<1.0",
    "mypy>=1.11,<2.0",
]
# Aggregate group CI installs so lint/type-check/tests see every import path.
all = [
    "finresearchai[memory]",
    "finresearchai[web]",
    "finresearchai[data]",
    "finresearchai[api]",
    "finresearchai[dev]",
]
```

> Note: the `finresearchai[...]` self-references in the `all` group are recursive optional-dependency references — supported by pip's PEP 508 extras resolution. `finresearchai` must match the `[project] name` set by the Foundation plan (it does: `name = "finresearchai"`).

- [ ] **Step 3: Replace `[tool.pytest.ini_options]` to register the marker and deselect live by default**

Replace the Foundation's `[tool.pytest.ini_options]` block with:

```toml
[tool.pytest.ini_options]
testpaths = ["tests"]
# Deselect the live (network) test by default; CI and local runs stay offline.
# --strict-markers turns any unregistered marker into an error (catches typos).
addopts = "-v -m \"not live\" --strict-markers"
asyncio_mode = "auto"
markers = [
    "live: real-network end-to-end test; requires RUN_LIVE=1 (deselect with '-m \"not live\"')",
]
```

- [ ] **Step 4: Add a lenient mypy config block** (append after the `[tool.ruff]` block)

```toml
[tool.mypy]
python_version = "3.11"
ignore_missing_imports = true
follow_imports = "silent"
warn_unused_ignores = false
disallow_untyped_defs = false
check_untyped_defs = false
# Lenient: we type-check that imports resolve and obvious mistakes, not strict typing.
```

- [ ] **Step 5: Add an optional coverage config block** (append at end of file)

```toml
[tool.coverage.run]
source = ["src"]
omit = ["tests/*"]

[tool.coverage.report]
# Coverage threshold is OPT-IN: enable by running `pytest --cov=src --cov-fail-under=60`.
# Not enforced by default CI to avoid blocking on integration-test coverage gaps.
show_missing = true
```

- [ ] **Step 6: Verify pyproject parses and the dev group installs**

```bash
python -c "import tomllib; d=tomllib.load(open('pyproject.toml','rb')); print('groups:', list(d['project']['optional-dependencies'])); print('markers:', d['tool']['pytest']['ini_options']['markers'])"
pip install -e ".[dev]"
python -m pytest --markers | grep -q "@pytest.mark.live" && echo "LIVE-MARKER-REGISTERED"
```
Expected: prints the five+`all` groups, the `live` marker string, then `LIVE-MARKER-REGISTERED`. The `--strict-markers` addopt means an unregistered `live` marker would error — registration confirms it.

- [ ] **Step 7: Confirm the existing suite still deselects cleanly**

Run: `python -m pytest -q`
Expected: existing Foundation tests PASS; pytest header shows `deselected` count of 0 so far (no live tests yet). No `PytestUnknownMarkWarning`.

- [ ] **Step 8: Commit**

```bash
git add pyproject.toml
git commit -m "build(deps): finalize pinned optional groups, register live marker, lenient mypy/coverage"
```

---

### Task 2: Shared fixtures — `fake_llm`, `frozen_state`, env isolation

This is the backbone of WP-I. The `fake_llm` fixture is a *factory*: tests call `fake_llm(SchemaInstance)` to get a fake LLM whose `.with_structured_output(Schema).ainvoke(...)` returns that exact Pydantic instance. It patches `src.llm.factory.get_llm` so any node calling `get_llm("quick"|"deep")` transparently receives the fake. Because the contract (COORDINATION.md §2) says every node uses `await llm.ainvoke(..., config={"callbacks":[tracker]})` and `with_structured_output(Schema)` returns the model directly, the fake mirrors that exactly.

**Files:**
- Create: `tests/conftest.py`
- Test: (this task is fixtures only; exercised by Task 3. We add a tiny self-test of the fixtures here so it fails first.)
- Create: `tests/test_conftest_fixtures.py`

- [ ] **Step 1: Write the failing fixture self-test**

```python
# tests/test_conftest_fixtures.py
import os

import pytest

from src.llm.factory import get_llm
from src.llm.schemas import TradeProposal


def test_env_isolation_clears_keys_and_disables_live():
    # The autouse env-isolation fixture must clear provider keys and force RUN_LIVE off.
    assert os.environ.get("RUN_LIVE", "0") == "0"
    assert os.environ.get("OLLAMA_API_KEY", "") == ""
    assert os.environ.get("FIRECRAWL_API_KEY", "") == ""


def test_frozen_state_is_fully_populated(frozen_state):
    s = frozen_state()
    assert s["ticker"]
    assert s["resolved_ticker"]
    assert set(s["analyst_reports"]) == {"news", "fundamentals", "technicals"}
    assert s["trade_proposal"]["action"] in {"BUY", "SELL", "HOLD"}
    assert s["final_decision"]["score"] == 50
    assert isinstance(s["run_metrics"], list)


@pytest.mark.asyncio
async def test_fake_llm_returns_supplied_pydantic_instance(fake_llm):
    proposal = TradeProposal(action="BUY", conviction=0.8, score=72, rationale="mocked")
    fake_llm(proposal)  # patches get_llm globally for this test
    llm = get_llm("deep").with_structured_output(TradeProposal, method="function_calling")
    result = await llm.ainvoke([{"role": "user", "content": "x"}], config={"callbacks": []})
    assert result is proposal
    assert result.action == "BUY"


@pytest.mark.asyncio
async def test_fake_llm_routes_by_schema(fake_llm):
    # Register multiple schema->instance mappings; the fake returns the right one per schema.
    from src.llm.schemas import AnalystReport

    report = AnalystReport(summary="news summary", confidence=0.7)
    proposal = TradeProposal(action="HOLD", conviction=0.5, score=50, rationale="r")
    fake_llm({AnalystReport: report, TradeProposal: proposal})

    a = await get_llm("quick").with_structured_output(AnalystReport).ainvoke("p")
    p = await get_llm("deep").with_structured_output(TradeProposal).ainvoke("p")
    assert a is report
    assert p is proposal
```

- [ ] **Step 2: Run to verify it fails**

Run: `python -m pytest tests/test_conftest_fixtures.py -q`
Expected: FAIL with `fixture 'frozen_state' not found` / `fixture 'fake_llm' not found`.

- [ ] **Step 3: Write `tests/conftest.py`**

```python
# tests/conftest.py
"""Shared fixtures for the WP-I test suite.

Three fixtures:
- env_isolation (autouse): scrub provider keys + force RUN_LIVE off so no test
  accidentally hits the network or reads a real .env.
- fake_llm: factory that patches src.llm.factory.get_llm to return a fake whose
  .with_structured_output(Schema).ainvoke(...) yields a caller-supplied Pydantic instance.
- frozen_state: builder producing a fully-populated AgentState dict.
"""
from __future__ import annotations

import os
from typing import Any

import pytest

from src.config import settings as settings_mod
from src.llm import factory as factory_mod


@pytest.fixture(autouse=True)
def env_isolation(monkeypatch):
    """Clear provider keys and the live switch; clear cached singletons.

    Runs for EVERY test (autouse). Ensures unit/integration tests never read a
    real .env or reach a live provider, and that get_settings()/get_llm() caches
    don't leak a real key between tests.
    """
    for key in ("OLLAMA_API_KEY", "FIRECRAWL_API_KEY", "LLM_BASE_URL", "LANGSMITH_API_KEY"):
        monkeypatch.delenv(key, raising=False)
    monkeypatch.setenv("RUN_LIVE", "0")
    # Construct Settings without reading the on-disk .env in tests.
    monkeypatch.setattr(
        settings_mod.Settings,
        "model_config",
        {**settings_mod.Settings.model_config, "env_file": None},
        raising=False,
    )
    settings_mod.get_settings.cache_clear()
    factory_mod.get_llm.cache_clear()
    yield
    settings_mod.get_settings.cache_clear()
    factory_mod.get_llm.cache_clear()


class _FakeStructured:
    """Stand-in for llm.with_structured_output(Schema): its ainvoke returns a fixed instance."""

    def __init__(self, instance: Any) -> None:
        self._instance = instance

    async def ainvoke(self, *args, **kwargs) -> Any:
        return self._instance

    def invoke(self, *args, **kwargs) -> Any:
        return self._instance


class _FakeLLM:
    """Stand-in for a ChatOpenAI. with_structured_output(Schema) -> _FakeStructured.

    `mapping` is either a single Pydantic instance (returned for any schema) or a
    dict {SchemaClass: instance} routed by the schema passed to with_structured_output.
    """

    def __init__(self, mapping: Any) -> None:
        self._mapping = mapping

    def with_structured_output(self, schema=None, **kwargs) -> _FakeStructured:
        if isinstance(self._mapping, dict):
            if schema not in self._mapping:
                raise KeyError(
                    f"fake_llm has no registered instance for schema {schema!r}; "
                    f"registered: {list(self._mapping)}"
                )
            return _FakeStructured(self._mapping[schema])
        return _FakeStructured(self._mapping)

    async def ainvoke(self, *args, **kwargs) -> Any:
        # For nodes that call the raw LLM without structured output (e.g. research_synthesis).
        if isinstance(self._mapping, dict):
            # Return the first registered instance as a best-effort default.
            return next(iter(self._mapping.values()))
        return self._mapping


@pytest.fixture
def fake_llm(monkeypatch):
    """Factory fixture. Call fake_llm(instance) or fake_llm({Schema: instance, ...}).

    Patches src.llm.factory.get_llm so every tier returns the same _FakeLLM.
    Returns the configured _FakeLLM in case the test wants to inspect it.
    """

    def _install(mapping: Any) -> _FakeLLM:
        fake = _FakeLLM(mapping)
        monkeypatch.setattr(factory_mod, "get_llm", lambda tier: fake)
        # Also patch the symbol where nodes import it, if they did `from src.llm.factory import get_llm`.
        # Nodes per COORDINATION.md import the module-level name, so patching the source is enough
        # only if they call factory.get_llm; to be safe we patch the attribute on the module object.
        return fake

    return _install


@pytest.fixture
def frozen_state():
    """Builder fixture: returns a callable producing a fully-populated AgentState dict.

    Defaults model a completed run for 'AAPL'; pass overrides to vary fields.
    """

    def _build(**overrides: Any) -> dict:
        state: dict[str, Any] = {
            "ticker": "AAPL",
            "resolved_ticker": "AAPL",
            "screener": "america",
            "exchange": "NASDAQ",
            "investor_mode": "Neutral",
            "model_plan": {"analysts": "quick", "debate": "deep", "verdict": "deep"},
            "analyst_reports": {
                "news": {"summary": "news ok", "key_points": ["a"], "confidence": 0.6, "citations": ["http://x"]},
                "fundamentals": {"summary": "fundies ok", "key_points": ["b"], "confidence": 0.7, "citations": []},
                "technicals": {"summary": "tech ok", "key_points": ["c"], "confidence": 0.5, "citations": []},
            },
            "research_debate": {
                "bull_thesis": "upside",
                "bear_thesis": "downside",
                "facilitator_verdict": "lean neutral",
            },
            "trade_proposal": {"action": "HOLD", "conviction": 0.5, "score": 50, "rationale": "mixed"},
            "risk_debate": {
                "conservative": "be careful",
                "aggressive": "be bold",
                "arbiter_decision": "hold",
                "adjustments": [],
            },
            "final_decision": {"action": "HOLD", "conviction": 0.5, "score": 50, "rationale": "final"},
            "final_report": "# AAPL Report\n\nStub body.",
            "run_metrics": [],
            "run_id": "test-run-0001",
        }
        state.update(overrides)
        return state

    return _build
```

- [ ] **Step 4: Run to verify it passes**

Run: `python -m pytest tests/test_conftest_fixtures.py -q`
Expected: PASS (4 tests). If `test_fake_llm_routes_by_schema` fails on schema identity, confirm nodes pass the schema CLASS (not an instance) to `with_structured_output` — the contract does.

- [ ] **Step 5: Commit**

```bash
git add tests/conftest.py tests/test_conftest_fixtures.py
git commit -m "test: add shared fake_llm factory, frozen_state builder, env-isolation fixtures"
```

---

### Task 3: Full-graph mocked integration test (the "whole system composes" test)

This is the keystone. It runs the REAL compiled graph for both debate modes with every LLM call mocked via `fake_llm` and every tool SDK monkeypatched, then asserts a coherent `final_report` + `final_decision` and the expected number of `run_metrics` records. It is the test that proves WP-B…F actually wire together.

> **Node-count expectation.** Per the frozen contract the "on" topology has 12 nodes, each appending exactly one metric record → `len(run_metrics) == 12`. The "off" topology (WP-D) bypasses `bull`/`bear`/`facilitator` with a single `research_synthesis` node → 12 − 3 + 1 = **10** nodes. If WP-D's actual off-mode node count differs, this test must be updated in lockstep (that is a coordination event — see COORDINATION.md §0). The test reads the count from a module-level constant so the expectation is explicit and easy to adjust.

**Files:**
- Create: `tests/integration/__init__.py`
- Create: `tests/integration/test_full_graph_mocked.py`

- [ ] **Step 1: Create the package marker**

```python
# tests/integration/__init__.py
```

- [ ] **Step 2: Write the failing integration test**

```python
# tests/integration/test_full_graph_mocked.py
"""End-to-end composition test: the REAL compiled graph for both debate modes,
with every LLM call mocked via fake_llm and every tool SDK monkeypatched.

This is the 'does the whole system compose' test. It does NOT assert on the
*content quality* of nodes (that is each WP's unit-test job) — it asserts the
graph runs to completion, every contract field is present and shaped correctly,
and metrics accumulate one-per-node.
"""
from __future__ import annotations

import pytest

from src.graph import build_graph
from src.llm.schemas import (
    AnalystReport,
    FinalDecision,
    ResearchDebate,
    RiskDebate,
    TradeProposal,
)

# Expected per-mode node counts (see the note in the plan; update on WP-D changes).
EXPECTED_METRIC_COUNT = {"on": 12, "off": 10}


def _all_schema_mapping():
    """Map every structured-output schema a node may request to a valid instance.

    The fake_llm routes by schema class, so we register one instance per schema.
    """
    return {
        AnalystReport: AnalystReport(
            summary="mocked analyst summary",
            key_points=["k1", "k2"],
            data={"pe": 30.0},
            confidence=0.6,
            citations=["https://example.com/a"],
        ),
        ResearchDebate: ResearchDebate(
            rounds=[],
            bull_thesis="mocked bull",
            bear_thesis="mocked bear",
            facilitator_verdict="mocked lean neutral",
        ),
        TradeProposal: TradeProposal(
            action="BUY", conviction=0.7, score=68, rationale="mocked trade rationale"
        ),
        RiskDebate: RiskDebate(
            rounds=[],
            conservative="mocked careful",
            aggressive="mocked bold",
            arbiter_decision="proceed with reduced size",
            adjustments=["trim 20%"],
        ),
        FinalDecision: FinalDecision(
            action="BUY", conviction=0.65, score=66, rationale="mocked final decision"
        ),
    }


@pytest.fixture
def mock_all_tools(monkeypatch):
    """Monkeypatch every external tool SDK seam so no network call happens.

    Patches the tool wrapper functions (src/tools/*) at the names the analysts
    import. If a tool module is not present yet (WP-B not merged), the patch is
    skipped — the analyst node then relies on fake_llm alone.
    """
    # Firecrawl web search/scrape (WP-B: src/tools/firecrawl.py)
    try:
        from src.tools import firecrawl as fc

        monkeypatch.setattr(
            fc, "search_news",
            lambda *a, **k: [{"title": "Mock headline", "url": "https://x", "snippet": "mock"}],
            raising=False,
        )
        monkeypatch.setattr(
            fc, "scrape", lambda *a, **k: "# Mock page\n\nmock markdown body", raising=False
        )
    except ImportError:
        pass

    # yfinance fundamentals (WP-B: src/tools/yfinance.py)
    try:
        from src.tools import yfinance as yf

        monkeypatch.setattr(
            yf, "get_fundamentals",
            lambda *a, **k: {"trailingPE": 30.0, "revenueGrowth": 0.08, "dividendYield": 0.005},
            raising=False,
        )
    except ImportError:
        pass

    # tradingview technicals (WP-B: src/tools/tradingview.py)
    try:
        from src.tools import tradingview as tv

        monkeypatch.setattr(
            tv, "get_technicals",
            lambda *a, **k: {"RSI": 55.0, "MACD": 0.4, "recommendation": "BUY"},
            raising=False,
        )
    except ImportError:
        pass

    # Memory cache (WP-C: src/memory/cache.py) — force a cache MISS so the full graph runs.
    try:
        from src.memory import cache as mem_cache

        monkeypatch.setattr(mem_cache, "get_cached_verdict", lambda *a, **k: None, raising=False)
        monkeypatch.setattr(mem_cache, "store_verdict", lambda *a, **k: None, raising=False)
    except ImportError:
        pass


@pytest.mark.asyncio
@pytest.mark.parametrize("mode", ["on", "off"])
async def test_full_graph_composes_for_both_modes(mode, fake_llm, mock_all_tools):
    fake_llm(_all_schema_mapping())
    app = build_graph(mode)

    result = await app.ainvoke({"ticker": "AAPL", "investor_mode": "Neutral"})

    # Router ran and resolved the ticker.
    assert result.get("resolved_ticker"), "router did not run / resolve ticker"

    # All three analysts wrote reports, merged by name.
    assert set(result["analyst_reports"]) == {"news", "fundamentals", "technicals"}

    # Research debate produced a facilitator verdict in BOTH modes.
    assert result["research_debate"]["facilitator_verdict"], "no facilitator verdict"

    # Trader + risk arbiter produced a coherent final decision.
    fd = result["final_decision"]
    assert fd["action"] in {"BUY", "SELL", "HOLD"}
    assert 0 <= fd["score"] <= 100
    assert 0.0 <= fd["conviction"] <= 1.0

    # Reporter produced a non-empty markdown report.
    assert isinstance(result["final_report"], str)
    assert result["final_report"].strip(), "empty final_report"
    assert result["final_report"].lstrip().startswith("#"), "report is not markdown"

    # Metrics accumulated one record per executed node.
    assert len(result["run_metrics"]) == EXPECTED_METRIC_COUNT[mode], (
        f"expected {EXPECTED_METRIC_COUNT[mode]} metric records in {mode!r} mode, "
        f"got {len(result['run_metrics'])}"
    )
    # Every metric record has the contract shape.
    for m in result["run_metrics"]:
        assert {"node", "prompt_tokens", "completion_tokens", "latency_s", "cost_usd"} <= set(m)


@pytest.mark.asyncio
async def test_on_and_off_modes_differ_in_node_count(fake_llm, mock_all_tools):
    fake_llm(_all_schema_mapping())
    on = await build_graph("on").ainvoke({"ticker": "AAPL", "investor_mode": "Neutral"})
    off = await build_graph("off").ainvoke({"ticker": "AAPL", "investor_mode": "Neutral"})
    assert len(on["run_metrics"]) > len(off["run_metrics"]), (
        "off-mode (research_synthesis bypass) should run fewer nodes than on-mode"
    )
```

- [ ] **Step 3: Run to verify it fails (and HOW it fails tells you which WPs are pending)**

Run: `python -m pytest tests/integration/test_full_graph_mocked.py -q`
Expected outcomes by integration state:
- If only the Foundation stub graph is merged: `build_graph("on")` works (returns 12 metrics, stub content) but `build_graph("off")` raises `TypeError` (stub `build_graph()` takes no args) → FAIL. This is the correct red state proving WP-D is not yet integrated.
- If WP-D's `build_graph(debate_mode)` is merged but real nodes call `get_llm` without our fake correctly patched, assertions on content presence may fail → indicates a fixture/seam gap to fix.

- [ ] **Step 4: Make it pass — precondition**

This test goes GREEN only once WP-B (analysts+tools), WP-D (`build_graph(debate_mode)` + research_synthesis), WP-E (trader+risk), and WP-F (reporter) are merged. Until then, mark the test `xfail` with a tracked reason so CI stays green during incremental integration:

```python
# Temporary, REMOVE once WP-B/D/E/F are merged. Tracked by COORDINATION.md §3.
pytestmark = pytest.mark.xfail(reason="awaiting WP-B/D/E/F real-node integration", strict=False)
```

Add that `pytestmark` line at module top *only* while those WPs are unmerged. Once they merge, delete the line and confirm the test passes for real:

Run: `python -m pytest tests/integration/test_full_graph_mocked.py -q`
Expected (post-integration): PASS (3 cases — `mode=on`, `mode=off`, `differ`).

- [ ] **Step 5: Commit**

```bash
git add tests/integration/__init__.py tests/integration/test_full_graph_mocked.py
git commit -m "test(integration): add full-graph mocked composition test for on/off debate modes"
```

---

### Task 4: Live smoke test (opt-in, single ticker, real network)

One honest end-to-end test that hits Ollama Cloud + Firecrawl for a single ticker. Skipped unless `RUN_LIVE=1` (the env-isolation fixture sets `RUN_LIVE=0`, so this fixture must check the value BEFORE that autouse fixture forces it off — we read it at collection time via an env check that the live runner sets explicitly, and the autouse fixture's `monkeypatch.setenv("RUN_LIVE","0")` is overridden inside this test's own setup).

> **Design decision:** the autouse `env_isolation` fixture forces `RUN_LIVE=0` AND clears the provider keys for every test. The live smoke test must opt OUT of that isolation. We do this with a module-scoped skip guard that reads the *process* environment at import time (before pytest fixtures run), and by NOT depending on `env_isolation` clearing keys — the live test re-reads keys from the real `.env`/process env explicitly. The autouse fixture still runs (it's autouse), so inside the test we re-set the real values from the captured process env.

**Files:**
- Create: `tests/integration/test_live_smoke.py`

- [ ] **Step 1: Write the live smoke test**

```python
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

    settings_mod.get_settings.cache_clear()
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
```

- [ ] **Step 2: Verify it is collected but SKIPPED by default**

Run: `python -m pytest tests/integration/test_live_smoke.py -q`
Expected: `1 skipped` (because `RUN_LIVE` defaults to `0` and `-m "not live"` would also deselect it). Confirms it never runs in normal/CI runs.

- [ ] **Step 3: (Optional, requires real keys) Verify it runs live**

Run: `RUN_LIVE=1 OLLAMA_API_KEY=$OLLAMA_API_KEY FIRECRAWL_API_KEY=$FIRECRAWL_API_KEY python -m pytest tests/integration/test_live_smoke.py -m live -q -s`
Expected: PASS (1 test) after real LLM + Firecrawl round-trips. Skip this step if you don't have live keys; CI never runs it.

- [ ] **Step 4: Commit**

```bash
git add tests/integration/test_live_smoke.py
git commit -m "test(integration): add opt-in live smoke test (RUN_LIVE=1, marked live)"
```

---

### Task 5: GitHub Actions CI workflow

CI runs on a py3.11 + py3.13 matrix, installs the aggregate `.[all]` group (so every import path lint/type-check/test exercises is present), runs `ruff check`, `mypy src` (lenient), and `pytest -q -m "not live"`. Pip is cached via `actions/setup-python@v6`'s built-in `cache: pip`, keyed on `pyproject.toml` (the unpinned `requirements.txt` is being deleted in Task 6, so the cache key must point at `pyproject.toml`).

**Files:**
- Create: `.github/workflows/ci.yml`

- [ ] **Step 1: Write the workflow**

```yaml
# .github/workflows/ci.yml
name: CI

on:
  push:
    branches: [main]
  pull_request:

permissions:
  contents: read

concurrency:
  group: ci-${{ github.ref }}
  cancel-in-progress: true

jobs:
  test:
    name: lint + types + tests (py${{ matrix.python-version }})
    runs-on: ubuntu-latest
    strategy:
      fail-fast: false
      matrix:
        python-version: ["3.11", "3.13"]

    steps:
      - name: Checkout
        uses: actions/checkout@v6

      - name: Set up Python ${{ matrix.python-version }}
        uses: actions/setup-python@v6
        with:
          python-version: ${{ matrix.python-version }}
          cache: pip
          cache-dependency-path: pyproject.toml

      - name: Install project + all optional groups
        run: |
          python -m pip install --upgrade pip
          pip install -e ".[all]"

      - name: Lint (ruff)
        run: ruff check .

      - name: Type-check (mypy, lenient)
        run: mypy src

      - name: Tests (offline; live deselected)
        env:
          # No real keys in CI; the env-isolation fixture also scrubs these.
          RUN_LIVE: "0"
        run: pytest -q -m "not live"
```

- [ ] **Step 2: Validate the workflow YAML locally**

Run: `python -c "import yaml; yaml.safe_load(open('.github/workflows/ci.yml')); print('YAML-OK')"`
Expected: prints `YAML-OK`. (If `pyyaml` isn't importable in your env, it is in `[dev]`; otherwise trust the structure.)

- [ ] **Step 3: Dry-run the CI commands locally to confirm they pass before pushing**

```bash
pip install -e ".[all]"
ruff check .
mypy src
pytest -q -m "not live"
```
Expected: `ruff check .` clean (fix any findings), `mypy src` clean under lenient config, `pytest` green with the live test deselected (shown as `deselected` in the summary). Fix anything red before committing the workflow.

- [ ] **Step 4: Commit**

```bash
git add .github/workflows/ci.yml
git commit -m "ci: add py3.11/3.13 matrix workflow (ruff + mypy + offline pytest, pip cache)"
```

---

### Task 6: Guarded legacy removal

Delete every legacy module **only after** its replacement has merged. The companion test (`tests/test_legacy_removed.py`, Task 7) is written FIRST in this task's TDD pairing — it is currently expected to FAIL (legacy still present) and will PASS after the `git rm` here. This task and Task 7 are co-dependent: write the test (Task 7 Step 1), confirm it fails, then run the removals here, then confirm it passes.

> **HARD PRECONDITION (WP-merge gate).** Do NOT run the `git rm` commands until ALL of these replacement sets exist and the full mocked integration test (Task 3) passes WITHOUT its `xfail` marker:
> - WP-B merged → `src/agents/router.py`, `src/agents/analysts/{news,fundamentals,technicals}.py`, `src/tools/{firecrawl,yfinance,tradingview}.py`
> - WP-C merged → `src/memory/{store,embeddings,cache}.py`
> - WP-D merged → `src/agents/research/{bull,bear,facilitator}.py`, `src/agents/debate.py`, `build_graph(debate_mode)`
> - WP-E merged → `src/agents/trader.py`, `src/agents/risk/{conservative,aggressive,arbiter}.py`
> - WP-F merged → `src/agents/reporter.py` (NEW content)
> - WP-G merged → `src/api/*` + `web/*` (the new entry point replacing `app.py`/`main.py`)
>
> Verify the gate before deleting:
> ```bash
> test -f src/agents/router.py && test -d src/agents/analysts && test -d src/tools && \
> test -d src/memory && test -d src/agents/research && test -f src/agents/debate.py && \
> test -f src/agents/trader.py && test -d src/agents/risk && test -d src/api && \
> echo "GATE-OPEN: all replacements present" || echo "GATE-CLOSED: do NOT delete legacy yet"
> ```
> Expected: `GATE-OPEN: all replacements present`. If `GATE-CLOSED`, STOP.

**Files:**
- Delete (legacy): `src/agents/manager.py`, `src/agents/analyst.py`, the OLD `src/agents/reporter.py` (already overwritten by WP-F — see note), `src/agents/researchers/tavily.py`, `src/agents/researchers/tradingview.py`, `src/agents/researchers/yfinance_agent.py`, `src/memory.py`, `tests/test_flow.py`, `tests/test_international.py`, `tests/test_ui_logic.py`, `main.py`, `app.py`, `requirements.txt`

> Note on `src/agents/reporter.py`: WP-F OWNS this exact path and OVERWRITES it with the new implementation. So it is NOT a `git rm` target — it is already the new file by the time the gate opens. Do NOT delete it. The legacy reporter logic is gone because WP-F replaced the file content. The same is true for `src/state.py` and `src/graph.py` (overwritten by Foundation). Only the modules with NO new file at the same path are `git rm`'d below.

- [ ] **Step 1: Remove the legacy researcher package and standalone agents**

```bash
git rm src/agents/manager.py
git rm src/agents/analyst.py
git rm src/agents/researchers/tavily.py
git rm src/agents/researchers/tradingview.py
git rm src/agents/researchers/yfinance_agent.py
git rm -r --ignore-unmatch src/agents/researchers
```

- [ ] **Step 2: Remove the legacy Pinecone memory module**

```bash
git rm src/memory.py
```
> If WP-C created a `src/memory/` PACKAGE, the old `src/memory.py` FILE and the new `src/memory/` DIRECTORY cannot coexist (name clash) — WP-C's merge would already have removed the file. In that case `git rm src/memory.py` reports "did not match any files"; that is fine, proceed.

- [ ] **Step 3: Remove the legacy entry points**

```bash
git rm main.py
git rm app.py
```

- [ ] **Step 4: Remove the dead tests and the unpinned requirements**

```bash
git rm tests/test_flow.py
git rm tests/test_international.py
git rm tests/test_ui_logic.py
git rm requirements.txt
```

- [ ] **Step 5: Clean up any now-empty legacy dirs and stale bytecode**

```bash
find src -name "__pycache__" -type d -prune -exec rm -rf {} + 2>/dev/null || true
test -d src/agents && ls src/agents
```
Expected: `src/agents` now contains only NEW files/dirs (`router.py`, `analysts/`, `research/`, `risk/`, `trader.py`, `reporter.py`, `debate.py`). No `manager.py`/`analyst.py`/`researchers/`.

- [ ] **Step 6: Run the full offline suite to confirm nothing imported the deleted modules**

Run: `python -m pytest -q -m "not live"`
Expected: GREEN. Any `ModuleNotFoundError` for `src.agents.manager` / `src.memory` / etc. means a NEW module still imports legacy — fix the offending new module (coordinate with its owning WP) before continuing.

- [ ] **Step 7: Commit**

```bash
git add -A
git commit -m "chore: remove legacy agents, Pinecone memory, dead tests, entry points, unpinned requirements"
```

---

### Task 7: Legacy-removal guard test

Asserts the legacy modules are gone and non-importable, so a future accidental re-add fails CI. Written first (red), passes after Task 6's removals.

**Files:**
- Create: `tests/test_legacy_removed.py`

- [ ] **Step 1: Write the test (BEFORE running Task 6's `git rm`)**

```python
# tests/test_legacy_removed.py
"""Guards the legacy cleanup (WP-I Task 6). These modules were the old
Pinecone-as-message-bus architecture; they must NOT exist or import.

If any of these pass-imports succeed, the legacy code was re-introduced —
fail loudly so CI catches it.
"""
import importlib
import importlib.util
from pathlib import Path

import pytest

_REPO_ROOT = Path(__file__).resolve().parents[1]

# Module import paths that must NO LONGER resolve.
LEGACY_MODULES = [
    "src.agents.manager",
    "src.agents.analyst",
    "src.agents.researchers.tavily",
    "src.agents.researchers.tradingview",
    "src.agents.researchers.yfinance_agent",
    "src.memory",  # old single-file Pinecone module (new code is the src/memory/ PACKAGE)
]

# Files/dirs that must NO LONGER exist on disk.
LEGACY_PATHS = [
    "src/agents/manager.py",
    "src/agents/analyst.py",
    "src/agents/researchers",
    "main.py",
    "app.py",
    "requirements.txt",
    "tests/test_flow.py",
    "tests/test_international.py",
    "tests/test_ui_logic.py",
]


@pytest.mark.parametrize("path", LEGACY_PATHS)
def test_legacy_path_deleted(path):
    assert not (_REPO_ROOT / path).exists(), f"legacy path still present: {path}"


@pytest.mark.parametrize("mod", LEGACY_MODULES)
def test_legacy_module_not_importable(mod):
    # src.memory becomes a PACKAGE in the new architecture; only the OLD single-file
    # module is forbidden. A package directory is allowed — distinguish by checking
    # that no MODULE file (src/memory.py) exists for the single-file legacy ones.
    if mod == "src.memory":
        assert not (_REPO_ROOT / "src" / "memory.py").exists(), (
            "legacy src/memory.py file still present (new code must be the src/memory/ package)"
        )
        return
    spec = importlib.util.find_spec(mod) if _can_find(mod) else None
    assert spec is None, f"legacy module still importable: {mod}"


def _can_find(mod: str) -> bool:
    """find_spec raises ModuleNotFoundError if a PARENT package is missing; treat as 'not found'."""
    try:
        return importlib.util.find_spec(mod) is not None
    except ModuleNotFoundError:
        return False
```

- [ ] **Step 2: Run BEFORE Task 6 to confirm it fails (red)**

Run: `python -m pytest tests/test_legacy_removed.py -q`
Expected (pre-cleanup): FAIL — legacy paths/modules still present. This proves the guard is meaningful.

- [ ] **Step 3: Run AFTER Task 6 to confirm it passes (green)**

Run: `python -m pytest tests/test_legacy_removed.py -q`
Expected (post-cleanup): PASS (all parametrized cases).

- [ ] **Step 4: Commit**

```bash
git add tests/test_legacy_removed.py
git commit -m "test: guard legacy module/path removal so re-adds fail CI"
```

---

### Task 8: Optional coverage gate

Coverage is OPT-IN (documented, not enforced by default CI) to avoid blocking incremental integration on integration-test coverage gaps. This task adds a tiny test that asserts the coverage tooling is configured correctly, plus the documented opt-in command.

**Files:**
- Create: `tests/test_coverage_gate.py`

- [ ] **Step 1: Write the test**

```python
# tests/test_coverage_gate.py
"""Coverage is OPT-IN. This test only verifies pytest-cov is installed and the
[tool.coverage.run] config targets src/. To ENFORCE a threshold, run:

    pytest --cov=src --cov-report=term-missing --cov-fail-under=60 -m "not live"

That command is intentionally NOT part of default CI (Task 5) so incremental
integration isn't blocked by coverage; flip it on once all WPs are merged.
"""
import tomllib
from pathlib import Path


def test_pytest_cov_is_installed():
    import importlib.util

    assert importlib.util.find_spec("pytest_cov") is not None, "pytest-cov not installed (in [dev])"


def test_coverage_config_targets_src():
    root = Path(__file__).resolve().parents[1]
    data = tomllib.load(open(root / "pyproject.toml", "rb"))
    assert data["tool"]["coverage"]["run"]["source"] == ["src"]
```

- [ ] **Step 2: Run to verify it passes**

Run: `python -m pytest tests/test_coverage_gate.py -q`
Expected: PASS (2 tests). Requires Task 1's coverage config + `pytest-cov` in `[dev]`.

- [ ] **Step 3: (Optional) Try the opt-in coverage gate**

Run: `python -m pytest --cov=src --cov-report=term-missing --cov-fail-under=60 -m "not live" -q`
Expected: prints a per-file coverage table; passes if `src/` coverage ≥ 60% (post full integration). Not run in CI by default.

- [ ] **Step 4: Commit**

```bash
git add tests/test_coverage_gate.py
git commit -m "test: add opt-in coverage gate config check"
```

---

## Dependencies

This WP is the cross-cutting closer. Order matters:

- **Foundation (`2026-05-29-foundation-and-state-contract.md`) MUST be merged first.** Tasks 1–4 depend on `pyproject.toml`, `src.llm.factory.get_llm`, `src.llm.schemas`, `src.state.AgentState`, and `build_graph()` existing.
- **Land early (no WP dependency):** Task 1 (deps/marker), Task 2 (conftest fixtures), Task 4 (live smoke — collected+skipped), Task 5 (CI), Task 8 (coverage check). These only need the Foundation and can merge while WP-B…H are in flight. CI immediately protects every subsequent WP merge.
- **Task 3 (full-graph mocked test)** lands early too, but carries a temporary `pytestmark = pytest.mark.xfail(...)` until WP-B, WP-D, WP-E, WP-F are merged. Remove the xfail and the off-mode count adjusts once WP-D's `build_graph(debate_mode)` and `research_synthesis` are real. The off-mode metric count (`EXPECTED_METRIC_COUNT["off"]`) is owned jointly with WP-D — if WP-D changes the off topology, update the constant (coordination event).
- **Tasks 6 + 7 (legacy removal + guard) MUST be LAST.** Hard precondition: ALL node-owning WPs merged (B, C, D, E, F) AND WP-G's new entry point merged (replacing `app.py`/`main.py`). Verify with the `GATE-OPEN` check in Task 6 Step 0. Removing legacy before its replacement merges will break imports in newly-merged WP modules that (incorrectly) still reference them — the Task 6 Step 6 full-suite run catches that.
- **Parallel development without the gate open:** Tasks 3's tool-mock fixture (`mock_all_tools`) uses `try/except ImportError` + `raising=False` so it no-ops cleanly against modules that don't exist yet — the test can be authored and partially exercised before WP-B/C land.

## Definition of Done

- [ ] `pyproject.toml` has five pinned optional groups (`memory`, `web`, `data`, `api`, `dev`) plus an aggregate `all`; the unpinned `requirements.txt` is deleted; no `pinecone-client` reference remains anywhere.
- [ ] `tests/conftest.py` provides `fake_llm` (schema-routed factory patching `src.llm.factory.get_llm`), `frozen_state` (fully-populated `AgentState` builder), and an autouse `env_isolation` fixture (clears `OLLAMA_API_KEY`/`FIRECRAWL_API_KEY`, forces `RUN_LIVE=0`, clears settings/factory caches).
- [ ] `tests/integration/test_full_graph_mocked.py` drives the REAL `build_graph("on")` and `build_graph("off")` to completion with all LLM + tool SDKs mocked, asserting a coherent `final_report` + `final_decision` and `run_metrics` counts (12 on / 10 off). Passes with no `xfail` once WP-B/D/E/F are merged.
- [ ] `tests/integration/test_live_smoke.py` is collected but skipped by default; runs and asserts a non-empty report only under `RUN_LIVE=1` with real `OLLAMA_API_KEY` + `FIRECRAWL_API_KEY`; required env documented in its docstring.
- [ ] The `live` marker is registered in `[tool.pytest.ini_options].markers`; `addopts` deselects it via `-m "not live"` and `--strict-markers` is on (no `PytestUnknownMarkWarning`).
- [ ] `.github/workflows/ci.yml` runs a py3.11 + py3.13 matrix on `actions/setup-python@v6` with `cache: pip` (keyed on `pyproject.toml`), installs `.[all]`, and runs `ruff check .`, `mypy src`, `pytest -q -m "not live"` — all green.
- [ ] `tests/test_legacy_removed.py` passes: all legacy modules/paths are gone and non-importable; `requirements.txt`, `main.py`, `app.py`, and the three dead test files are deleted.
- [ ] Legacy removal (Task 6) was performed ONLY after the `GATE-OPEN` precondition check confirmed every replacement exists, and `python -m pytest -q -m "not live"` is green afterward.
- [ ] `tests/test_coverage_gate.py` passes; the opt-in `--cov-fail-under=60` command is documented (not enforced by default CI).

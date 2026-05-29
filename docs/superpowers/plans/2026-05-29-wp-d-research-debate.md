# WP-D — Research Debate (Bull / Bear / Facilitator) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Land the headline M2 mechanism from the paper — a bounded bull↔bear researcher debate with a facilitator that selects the prevailing view — plus the **shared `run_debate` runner** (reused by WP-E's risk debate) and the **`build_graph(debate_mode)` toggle** that wires the full debate topology (`"on"`) or a single-pass `research_synthesis` baseline (`"off"`) for the WP-H A/B harness.

**Architecture:** `run_debate` is a pure async helper (no graph dependency) that runs `rounds` bounded turns over a list of `(role, system_prompt)` personas, alternating personas each turn, producing one `DebateTurn` per turn via `get_llm(tier).with_structured_output(DebateTurn)` and aggregating per-node `CostTracker` metrics. The graph nodes split responsibility cleanly: **`bull` and `bear` each run once to write their standalone thesis into `research_debate` (parallel, merged by the existing reducer); the `facilitator` then runs the bounded back-and-forth via `run_debate`, selects the prevailing view, and writes the full structured `ResearchDebate` (rounds + verdict).** This design is chosen over "bull/bear ARE the debate loop" because (a) the bounded alternating loop lives in exactly one place (`run_debate`), shared verbatim with WP-E, instead of being duplicated across two nodes that would each need to read the other's partial state across a join; (b) bull/bear stay simple single-LLM-call nodes that parallelize trivially; (c) the facilitator owns round-count and verdict, matching the paper's facilitator role (§3.2). For `debate_mode="off"`, bull/bear/facilitator are **not registered**; a single `research_synthesis` node does one deep pass writing `research_debate.facilitator_verdict` directly. The bounded loop is an in-node Python `for` loop (deterministic count from settings), NOT a cyclic graph edge — verified simpler and recursion-limit-free in LangGraph 1.0.4.

**Tech Stack:** Python 3.13, `langgraph==1.0.4`, `langchain-core==1.2.5`, `langchain-openai==1.1.6`, `pydantic==2.12.5`, `pytest==8.4.2`, `pytest-asyncio>=0.24`. No new runtime dependencies (all already pinned by the Foundation plan's `pyproject.toml`).

---

## Context for the implementer

This WP replaces the `bull`, `bear`, `facilitator` stub nodes from the Foundation graph (`src/graph.py`) and **takes ownership of `build_graph`**. You import the frozen contract — do not redefine it:

- `get_llm(tier)` from `src/llm/factory.py`
- `CostTracker(node)` from `src/llm/cost.py` (`.totals()["per_node"]`)
- `DebateTurn`, `ResearchDebate` from `src/llm/schemas.py`
- `AgentState`, `merge_named_reports` from `src/state.py` (`research_debate` has the `merge_named_reports` reducer — multiple writers to it merge, right-wins on key conflict)
- `get_settings()` from `src/config/settings.py` (`.research_debate_rounds`, `.debate_mode`)

**Conventions (COORDINATION §2), follow exactly:** every node is `async def node(state) -> dict`; LLM calls use `await llm.ainvoke(...)`; structured output via `get_llm(tier).with_structured_output(Model, method="function_calling")` which **returns the Pydantic model instance directly** on `ainvoke`; each node creates one `CostTracker(name)`, passes it as a callback, returns `"run_metrics": tracker.totals()["per_node"]`; absolute imports; no network in unit tests (mock `get_llm`); one opt-in `@pytest.mark.live` test.

**LangGraph 1.0.4 API decisions (verified via Context7):**
1. **Two topologies from one builder:** conditionally call `add_node`/`add_edge` based on `debate_mode` before `compile()`. Nodes not registered do not exist in the compiled graph — this is how `"off"` proves it never registers bull/bear/facilitator.
2. **Parallel fan-out:** multiple `add_edge("router", "bull")` / `add_edge("router", "bear")` (or static edges from a join) run those targets concurrently; concurrent writes to `research_debate` are safe because it carries the `merge_named_reports` reducer.
3. **Bounded debate loop:** an in-node Python `for round in range(1, rounds+1)` loop calling `llm.ainvoke` per turn. NOT a cyclic edge + `recursion_limit` — the round count is deterministic config, so a plain loop is simpler, testable without graph machinery, and has no recursion-limit pitfalls.
4. **`with_structured_output(...).ainvoke(...)` returns the model instance** (e.g. `DebateTurn`), confirmed for the `function_calling` method; store `.model_dump()` into state.

**Tool-calling fallback:** if the configured deep model lacks Ollama Cloud tool-calling, switch `method="function_calling"` → `method="json_schema"` in every `with_structured_output` call here and note it. Verify once via the WP-D live test (Task 12).

**`run_debate` and `build_graph(debate_mode)` are the public interfaces other WPs depend on:**
- **WP-E** imports `run_debate` for the conservative↔aggressive risk debate (same signature) — must merge WP-D first or stub `run_debate` behind this exact signature.
- **WP-H** calls `build_graph("on")` and `build_graph("off")` to run the debate A/B comparison.

## File Structure

| File | Responsibility |
|---|---|
| `src/agents/__init__.py` | Package marker (create if absent) |
| `src/agents/debate.py` | `run_debate(...)` shared bounded-debate runner (COORDINATION §4 signature) |
| `src/agents/research/__init__.py` | Package marker |
| `src/agents/research/bull.py` | `bull` async node — writes `research_debate.bull_thesis` |
| `src/agents/research/bear.py` | `bear` async node — writes `research_debate.bear_thesis` |
| `src/agents/research/facilitator.py` | `facilitator` async node — runs `run_debate`, writes full `ResearchDebate` |
| `src/agents/research/synthesis.py` | `research_synthesis` node — single deep pass for `debate_mode="off"` baseline |
| `src/graph.py` | **(owned by WP-D)** `build_graph(debate_mode)` wires `"on"` vs `"off"` topology |
| `tests/test_debate_runner.py` | `run_debate` round count / alternation / metrics |
| `tests/test_research_nodes.py` | bull / bear / facilitator / synthesis node behavior (mocked LLM) |
| `tests/test_graph_debate_modes.py` | `build_graph("on")` and `build_graph("off")` end-to-end + node registration |
| `tests/conftest.py` | Shared `fake_llm` fixture (mock `get_llm`) — append if exists, else create |

---

### Task 1: Package markers & shared `fake_llm` test fixture

**Files:**
- Create (if absent): `src/agents/__init__.py`, `src/agents/research/__init__.py`
- Create or append: `tests/conftest.py`

- [ ] **Step 1: Create package markers**

```bash
mkdir -p src/agents/research
: > src/agents/__init__.py
: > src/agents/research/__init__.py
```

(If `src/agents/__init__.py` already exists from another WP, leave it; `:` truncates only if you ran it — instead check first: `test -f src/agents/__init__.py || : > src/agents/__init__.py`.)

- [ ] **Step 2: Create/extend `tests/conftest.py` with a reusable structured-output mock**

If `tests/conftest.py` does not exist, create it with the content below. If it exists, append only the `make_structured_llm` factory and `_seq` helper (skip duplicate imports).

```python
# tests/conftest.py
from __future__ import annotations

from types import SimpleNamespace
from typing import Any

import pytest


def make_structured_llm(outputs: list[Any]):
    """Return a fake LLM whose .with_structured_output(...).ainvoke(...) yields
    the prepared outputs in order. Each call to with_structured_output returns
    a fresh structured handle that shares the same output queue, and each
    ainvoke also fires the CostTracker callbacks so per-node metrics are recorded.
    """
    queue = list(outputs)

    class _Structured:
        async def ainvoke(self, messages, config=None, **kwargs):
            callbacks = (config or {}).get("callbacks", []) or []
            rid = f"run-{len(queue)}"
            for cb in callbacks:
                cb.on_llm_start({}, ["prompt"], run_id=rid)
            result = queue.pop(0)
            response = SimpleNamespace(
                llm_output={
                    "token_usage": {"prompt_tokens": 10, "completion_tokens": 5},
                    "model_name": "fake-deep",
                }
            )
            for cb in callbacks:
                cb.on_llm_end(response, run_id=rid)
            return result

    class _LLM:
        def with_structured_output(self, schema, method="function_calling"):
            return _Structured()

    return _LLM()


@pytest.fixture
def fake_llm_factory(monkeypatch):
    """Patch get_llm everywhere it is imported so nodes receive a scripted LLM.

    Usage:
        fake_llm_factory([turn1, turn2, ...])
    Patches both src.llm.factory.get_llm and the per-module imported names.
    """
    def _install(outputs: list[Any], modules: list[str]):
        llm = make_structured_llm(outputs)
        import src.llm.factory as factory_mod
        monkeypatch.setattr(factory_mod, "get_llm", lambda tier: llm)
        for mod_path in modules:
            import importlib
            mod = importlib.import_module(mod_path)
            if hasattr(mod, "get_llm"):
                monkeypatch.setattr(mod, "get_llm", lambda tier: llm)
        return llm

    return _install
```

- [ ] **Step 3: Commit**

```bash
git add src/agents/__init__.py src/agents/research/__init__.py tests/conftest.py
git commit -m "test(wp-d): add agents packages and shared structured-output LLM fixture"
```

---

### Task 2: `run_debate` — failing test for round count & alternation

**Files:**
- Test: `tests/test_debate_runner.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_debate_runner.py
import pytest

from src.llm.schemas import DebateTurn


@pytest.mark.asyncio
async def test_run_debate_respects_round_count(fake_llm_factory):
    # 2 rounds x 2 personas = 4 turns expected
    scripted = [
        DebateTurn(role="bull", round=1, argument="b1"),
        DebateTurn(role="bear", round=1, argument="r1"),
        DebateTurn(role="bull", round=2, argument="b2"),
        DebateTurn(role="bear", round=2, argument="r2"),
    ]
    fake_llm_factory(scripted, ["src.agents.debate"])
    from src.agents.debate import run_debate

    personas = [("bull", "you are bullish"), ("bear", "you are bearish")]
    turns, metrics = await run_debate(
        topic="AAPL", context="reports...", personas=personas, rounds=2, node_label="research_debate"
    )
    assert len(turns) == 4
    assert all(isinstance(t, DebateTurn) for t in turns)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_debate_runner.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'src.agents.debate'`

---

### Task 3: `run_debate` — implementation

**Files:**
- Create: `src/agents/debate.py`

- [ ] **Step 1: Write the implementation**

```python
# src/agents/debate.py
"""Shared bounded-debate runner. Owned by WP-D; reused by WP-E (risk debate).

A debate is `rounds` bounded turns over an ordered list of personas. Personas
alternate by turn index. Each turn produces exactly one DebateTurn via
get_llm(tier).with_structured_output(DebateTurn). Per-node metrics from every
LLM call are aggregated under a single node_label and returned for the caller
to fold into AgentState["run_metrics"].
"""
from __future__ import annotations

from langchain_core.messages import HumanMessage, SystemMessage

from src.llm.cost import CostTracker
from src.llm.factory import get_llm
from src.llm.schemas import DebateTurn


async def run_debate(
    topic: str,
    context: str,
    personas: list[tuple[str, str]],
    rounds: int,
    tier: str = "deep",
    node_label: str = "debate",
) -> tuple[list[DebateTurn], dict]:
    """Run a bounded alternating debate.

    Args:
        topic: short subject line (e.g. the ticker or the trade proposal).
        context: shared context all personas see (analyst reports, prior turns).
        personas: ordered [(role, system_prompt), ...]; turns alternate through them.
        rounds: number of full cycles through every persona (bounded by caller).
        tier: LLM tier ("deep" by default).
        node_label: metrics node name for all calls in this debate.

    Returns:
        (turns, metrics_per_node) where turns is a flat list of DebateTurn in
        speaking order and metrics_per_node is CostTracker.totals()["per_node"].
    """
    tracker = CostTracker(node_label)
    llm = get_llm(tier).with_structured_output(DebateTurn, method="function_calling")

    turns: list[DebateTurn] = []
    transcript: list[str] = []

    for rnd in range(1, max(1, rounds) + 1):
        for role, system_prompt in personas:
            prior = "\n".join(transcript) if transcript else "(no prior arguments yet)"
            human = (
                f"Topic: {topic}\n\n"
                f"Shared context:\n{context}\n\n"
                f"Debate so far:\n{prior}\n\n"
                f"You are the '{role}' debater. This is round {rnd}. "
                f"Make your strongest argument for your stance. "
                f"Set role='{role}' and round={rnd} in your response."
            )
            messages = [SystemMessage(content=system_prompt), HumanMessage(content=human)]
            turn: DebateTurn = await llm.ainvoke(messages, config={"callbacks": [tracker]})
            # Trust the persona's role/round assignment to the loop, not the model.
            turn.role = role  # type: ignore[assignment]
            turn.round = rnd
            turns.append(turn)
            transcript.append(f"[round {rnd}] {role}: {turn.argument}")

    return turns, tracker.totals()["per_node"]
```

- [ ] **Step 2: Run test to verify it passes**

Run: `python -m pytest tests/test_debate_runner.py -v`
Expected: PASS (1 test)

- [ ] **Step 3: Commit**

```bash
git add src/agents/debate.py tests/test_debate_runner.py
git commit -m "feat(wp-d): add shared run_debate bounded-debate runner"
```

---

### Task 4: `run_debate` — alternation order & metrics aggregation tests

**Files:**
- Test: `tests/test_debate_runner.py` (append)

- [ ] **Step 1: Append the failing tests**

```python
# tests/test_debate_runner.py  (append)
@pytest.mark.asyncio
async def test_run_debate_turns_alternate_roles(fake_llm_factory):
    scripted = [
        DebateTurn(role="bull", round=1, argument="x"),
        DebateTurn(role="bear", round=1, argument="x"),
        DebateTurn(role="bull", round=2, argument="x"),
        DebateTurn(role="bear", round=2, argument="x"),
    ]
    fake_llm_factory(scripted, ["src.agents.debate"])
    from src.agents.debate import run_debate

    personas = [("bull", "p1"), ("bear", "p2")]
    turns, _ = await run_debate("AAPL", "ctx", personas, rounds=2, node_label="research_debate")
    assert [t.role for t in turns] == ["bull", "bear", "bull", "bear"]
    assert [t.round for t in turns] == [1, 1, 2, 2]


@pytest.mark.asyncio
async def test_run_debate_aggregates_metrics_under_node_label(fake_llm_factory):
    scripted = [
        DebateTurn(role="bull", round=1, argument="x"),
        DebateTurn(role="bear", round=1, argument="x"),
    ]
    fake_llm_factory(scripted, ["src.agents.debate"])
    from src.agents.debate import run_debate

    personas = [("bull", "p1"), ("bear", "p2")]
    _, metrics = await run_debate("AAPL", "ctx", personas, rounds=1, node_label="research_debate")
    # one metric record per LLM call, all under the same node label
    assert len(metrics) == 2
    assert all(m["node"] == "research_debate" for m in metrics)
    assert sum(m["prompt_tokens"] for m in metrics) == 20


@pytest.mark.asyncio
async def test_run_debate_min_one_round(fake_llm_factory):
    scripted = [
        DebateTurn(role="bull", round=1, argument="x"),
        DebateTurn(role="bear", round=1, argument="x"),
    ]
    fake_llm_factory(scripted, ["src.agents.debate"])
    from src.agents.debate import run_debate

    # rounds=0 is clamped to a single round (never an empty debate)
    turns, _ = await run_debate("AAPL", "ctx", [("bull", "p1"), ("bear", "p2")], rounds=0)
    assert len(turns) == 2
```

- [ ] **Step 2: Run tests to verify they pass**

Run: `python -m pytest tests/test_debate_runner.py -v`
Expected: PASS (4 tests total). The clamp test passes because the impl uses `range(1, max(1, rounds) + 1)`.

- [ ] **Step 3: Commit**

```bash
git add tests/test_debate_runner.py
git commit -m "test(wp-d): cover run_debate alternation, metrics, and round clamp"
```

---

### Task 5: `bull` node — failing test

**Files:**
- Test: `tests/test_research_nodes.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_research_nodes.py
import pytest

from src.llm.schemas import DebateTurn, ResearchDebate


def _synthetic_state():
    # WP-B provides analyst_reports; here we inject synthetic ones.
    return {
        "ticker": "AAPL",
        "resolved_ticker": "AAPL",
        "investor_mode": "Neutral",
        "analyst_reports": {
            "news": {"summary": "positive product cycle", "confidence": 0.7},
            "fundamentals": {"summary": "strong margins, rich valuation", "confidence": 0.6},
            "technicals": {"summary": "RSI 62, uptrend", "confidence": 0.55},
        },
    }


@pytest.mark.asyncio
async def test_bull_writes_thesis_and_metrics(fake_llm_factory):
    fake_llm_factory(
        [DebateTurn(role="bull", round=1, argument="growth runway is underpriced")],
        ["src.agents.research.bull"],
    )
    from src.agents.research.bull import bull

    out = await bull(_synthetic_state())
    assert out["research_debate"]["bull_thesis"] == "growth runway is underpriced"
    assert len(out["run_metrics"]) == 1
    assert out["run_metrics"][0]["node"] == "bull"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_research_nodes.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'src.agents.research.bull'`

---

### Task 6: `bull` node — implementation

**Files:**
- Create: `src/agents/research/bull.py`

- [ ] **Step 1: Write the implementation**

```python
# src/agents/research/bull.py
"""Bull researcher node: produces a single standalone bullish thesis from the
analyst reports. Writes only research_debate.bull_thesis; the merge_named_reports
reducer combines it with the bear's parallel write."""
from __future__ import annotations

import json

from langchain_core.messages import HumanMessage, SystemMessage

from src.llm.cost import CostTracker
from src.llm.factory import get_llm
from src.llm.schemas import DebateTurn
from src.state import AgentState

BULL_SYSTEM = (
    "You are the BULL researcher on an equity research desk. Build the strongest "
    "evidence-based case to BUY the stock, citing the analyst reports. Be specific "
    "and concise. Acknowledge the single biggest risk only to rebut it."
)


def _context(state: AgentState) -> str:
    reports = state.get("analyst_reports", {})
    return json.dumps(reports, default=str)


async def bull(state: AgentState) -> dict:
    tracker = CostTracker("bull")
    llm = get_llm("deep").with_structured_output(DebateTurn, method="function_calling")
    ticker = state.get("resolved_ticker") or state.get("ticker", "")
    human = (
        f"Ticker: {ticker}\n\nAnalyst reports (JSON):\n{_context(state)}\n\n"
        "State your bullish thesis. Set role='bull' and round=1."
    )
    messages = [SystemMessage(content=BULL_SYSTEM), HumanMessage(content=human)]
    turn: DebateTurn = await llm.ainvoke(messages, config={"callbacks": [tracker]})
    return {
        "research_debate": {"bull_thesis": turn.argument},
        "run_metrics": tracker.totals()["per_node"],
    }
```

- [ ] **Step 2: Run test to verify it passes**

Run: `python -m pytest tests/test_research_nodes.py -v`
Expected: PASS (1 test)

- [ ] **Step 3: Commit**

```bash
git add src/agents/research/bull.py tests/test_research_nodes.py
git commit -m "feat(wp-d): add bull researcher node"
```

---

### Task 7: `bear` node — test & implementation

**Files:**
- Test: `tests/test_research_nodes.py` (append)
- Create: `src/agents/research/bear.py`

- [ ] **Step 1: Append the failing test**

```python
# tests/test_research_nodes.py  (append)
@pytest.mark.asyncio
async def test_bear_writes_thesis_and_metrics(fake_llm_factory):
    fake_llm_factory(
        [DebateTurn(role="bear", round=1, argument="valuation leaves no margin of safety")],
        ["src.agents.research.bear"],
    )
    from src.agents.research.bear import bear

    out = await bear(_synthetic_state())
    assert out["research_debate"]["bear_thesis"] == "valuation leaves no margin of safety"
    assert out["run_metrics"][0]["node"] == "bear"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_research_nodes.py::test_bear_writes_thesis_and_metrics -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'src.agents.research.bear'`

- [ ] **Step 3: Write the implementation**

```python
# src/agents/research/bear.py
"""Bear researcher node: produces a single standalone bearish thesis from the
analyst reports. Writes only research_debate.bear_thesis; merged with the bull's
parallel write by merge_named_reports."""
from __future__ import annotations

import json

from langchain_core.messages import HumanMessage, SystemMessage

from src.llm.cost import CostTracker
from src.llm.factory import get_llm
from src.llm.schemas import DebateTurn
from src.state import AgentState

BEAR_SYSTEM = (
    "You are the BEAR researcher on an equity research desk. Build the strongest "
    "evidence-based case to SELL or AVOID the stock, citing the analyst reports. "
    "Be specific and concise. Acknowledge the single biggest bullish point only to rebut it."
)


def _context(state: AgentState) -> str:
    return json.dumps(state.get("analyst_reports", {}), default=str)


async def bear(state: AgentState) -> dict:
    tracker = CostTracker("bear")
    llm = get_llm("deep").with_structured_output(DebateTurn, method="function_calling")
    ticker = state.get("resolved_ticker") or state.get("ticker", "")
    human = (
        f"Ticker: {ticker}\n\nAnalyst reports (JSON):\n{_context(state)}\n\n"
        "State your bearish thesis. Set role='bear' and round=1."
    )
    messages = [SystemMessage(content=BEAR_SYSTEM), HumanMessage(content=human)]
    turn: DebateTurn = await llm.ainvoke(messages, config={"callbacks": [tracker]})
    return {
        "research_debate": {"bear_thesis": turn.argument},
        "run_metrics": tracker.totals()["per_node"],
    }
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_research_nodes.py -v`
Expected: PASS (3 tests so far)

- [ ] **Step 5: Commit**

```bash
git add src/agents/research/bear.py tests/test_research_nodes.py
git commit -m "feat(wp-d): add bear researcher node"
```

---

### Task 8: `facilitator` node — failing test

**Files:**
- Test: `tests/test_research_nodes.py` (append)

The facilitator runs the bounded debate via `run_debate`, then makes one more deep call to select the prevailing view (the verdict). Mock both: `run_debate` LLM turns AND the verdict call. The simplest mock supplies all turns + the verdict turn from one queue, since the facilitator uses `get_llm("deep")` for both the debate (via `run_debate`) and the verdict. We patch `get_llm` in both `src.agents.debate` and `src.agents.research.facilitator`.

- [ ] **Step 1: Append the failing test**

```python
# tests/test_research_nodes.py  (append)
@pytest.mark.asyncio
async def test_facilitator_runs_debate_and_writes_full_research_debate(fake_llm_factory):
    # 1 round x 2 personas = 2 debate turns, then 1 verdict turn.
    fake_llm_factory(
        [
            DebateTurn(role="bull", round=1, argument="bull rebuttal"),
            DebateTurn(role="bear", round=1, argument="bear rebuttal"),
            DebateTurn(role="bull", round=1, argument="On balance, lean BUY: growth outweighs valuation."),
        ],
        ["src.agents.debate", "src.agents.research.facilitator"],
    )
    from src.agents.research.facilitator import facilitator

    state = _synthetic_state()
    # Bull/bear already wrote their theses upstream (merged into research_debate):
    state["research_debate"] = {"bull_thesis": "bull case", "bear_thesis": "bear case"}

    out = await facilitator(state)
    rd = out["research_debate"]
    assert rd["facilitator_verdict"]  # non-empty
    assert len(rd["rounds"]) == 2  # the debate turns
    assert rd["rounds"][0]["role"] == "bull"
    # carried forward from upstream merge (facilitator preserves them)
    assert rd["bull_thesis"] == "bull case"
    assert rd["bear_thesis"] == "bear case"
    # metrics from the debate (node_label="research_debate") + the facilitator verdict call
    nodes = {m["node"] for m in out["run_metrics"]}
    assert "facilitator" in nodes
    assert "research_debate" in nodes
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_research_nodes.py::test_facilitator_runs_debate_and_writes_full_research_debate -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'src.agents.research.facilitator'`

---

### Task 9: `facilitator` node — implementation

**Files:**
- Create: `src/agents/research/facilitator.py`

- [ ] **Step 1: Write the implementation**

```python
# src/agents/research/facilitator.py
"""Research facilitator node: runs the bounded bull<->bear debate via run_debate,
then selects the prevailing view and writes the full ResearchDebate into state.

Reads bull_thesis/bear_thesis already merged into research_debate by the upstream
bull/bear nodes (merge_named_reports reducer). Writes rounds + facilitator_verdict
while preserving the theses. research_debate carries the merge reducer, so the
returned partial dict is merged into existing state."""
from __future__ import annotations

import json

from langchain_core.messages import HumanMessage, SystemMessage

from src.agents.debate import run_debate
from src.config.settings import get_settings
from src.llm.cost import CostTracker
from src.llm.factory import get_llm
from src.llm.schemas import DebateTurn
from src.state import AgentState

FACILITATOR_SYSTEM = (
    "You are the research facilitator. You have moderated a bounded bull vs bear "
    "debate. Weigh both sides and the analyst evidence, then state the prevailing "
    "view as a concise verdict that the trader can act on. Be decisive but honest "
    "about residual uncertainty. Put your verdict in 'argument'; set role='bull' if "
    "the prevailing view is bullish else role='bear', and round=1."
)

BULL_SYSTEM = (
    "You are the BULL debater. Argue to BUY using the analyst reports and rebut the "
    "bear. Be specific and concise."
)
BEAR_SYSTEM = (
    "You are the BEAR debater. Argue to SELL/AVOID using the analyst reports and "
    "rebut the bull. Be specific and concise."
)


async def facilitator(state: AgentState) -> dict:
    settings = get_settings()
    rounds = settings.research_debate_rounds
    ticker = state.get("resolved_ticker") or state.get("ticker", "")
    rd = state.get("research_debate", {})
    bull_thesis = rd.get("bull_thesis", "")
    bear_thesis = rd.get("bear_thesis", "")

    context = (
        f"Analyst reports (JSON):\n{json.dumps(state.get('analyst_reports', {}), default=str)}\n\n"
        f"Bull opening thesis: {bull_thesis}\n"
        f"Bear opening thesis: {bear_thesis}"
    )
    personas = [("bull", BULL_SYSTEM), ("bear", BEAR_SYSTEM)]

    turns, debate_metrics = await run_debate(
        topic=ticker,
        context=context,
        personas=personas,
        rounds=rounds,
        tier="deep",
        node_label="research_debate",
    )

    transcript = "\n".join(f"[round {t.round}] {t.role}: {t.argument}" for t in turns)
    tracker = CostTracker("facilitator")
    verdict_llm = get_llm("deep").with_structured_output(DebateTurn, method="function_calling")
    human = (
        f"Ticker: {ticker}\n\n{context}\n\nFull debate transcript:\n{transcript}\n\n"
        "Now deliver the prevailing-view verdict."
    )
    messages = [SystemMessage(content=FACILITATOR_SYSTEM), HumanMessage(content=human)]
    verdict: DebateTurn = await verdict_llm.ainvoke(messages, config={"callbacks": [tracker]})

    research_debate = {
        "rounds": [t.model_dump() for t in turns],
        "bull_thesis": bull_thesis,
        "bear_thesis": bear_thesis,
        "facilitator_verdict": verdict.argument,
    }
    return {
        "research_debate": research_debate,
        "run_metrics": debate_metrics + tracker.totals()["per_node"],
    }
```

- [ ] **Step 2: Run test to verify it passes**

Run: `python -m pytest tests/test_research_nodes.py -v`
Expected: PASS (4 tests). The `rounds` count comes from `get_settings().research_debate_rounds` (default 1 → 2 turns), matching the test's expectation of `len(rounds) == 2`.

- [ ] **Step 3: Commit**

```bash
git add src/agents/research/facilitator.py tests/test_research_nodes.py
git commit -m "feat(wp-d): add research facilitator node running bounded debate"
```

---

### Task 10: `research_synthesis` baseline node (debate_mode="off")

**Files:**
- Test: `tests/test_research_nodes.py` (append)
- Create: `src/agents/research/synthesis.py`

- [ ] **Step 1: Append the failing test**

```python
# tests/test_research_nodes.py  (append)
@pytest.mark.asyncio
async def test_research_synthesis_writes_verdict_only(fake_llm_factory):
    fake_llm_factory(
        [DebateTurn(role="bull", round=1, argument="Single-pass verdict: lean BUY.")],
        ["src.agents.research.synthesis"],
    )
    from src.agents.research.synthesis import research_synthesis

    out = await research_synthesis(_synthetic_state())
    rd = out["research_debate"]
    assert rd["facilitator_verdict"] == "Single-pass verdict: lean BUY."
    # baseline does NOT manufacture bull/bear theses or rounds
    assert rd.get("bull_thesis", "") == ""
    assert rd.get("bear_thesis", "") == ""
    assert rd.get("rounds", []) == []
    assert out["run_metrics"][0]["node"] == "research_synthesis"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_research_nodes.py::test_research_synthesis_writes_verdict_only -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'src.agents.research.synthesis'`

- [ ] **Step 3: Write the implementation**

```python
# src/agents/research/synthesis.py
"""Single-pass research baseline for debate_mode="off". Does ONE deep LLM pass over
the analyst reports and writes research_debate.facilitator_verdict directly,
bypassing bull/bear/facilitator. This is the A/B baseline WP-H compares against the
full debate path. Intentionally leaves bull_thesis/bear_thesis/rounds empty so the
A/B harness can detect 'no debate happened'."""
from __future__ import annotations

import json

from langchain_core.messages import HumanMessage, SystemMessage

from src.llm.cost import CostTracker
from src.llm.factory import get_llm
from src.llm.schemas import DebateTurn
from src.state import AgentState

SYNTHESIS_SYSTEM = (
    "You are a senior equity analyst. In a SINGLE pass over the analyst reports, "
    "weigh the bullish and bearish evidence yourself and deliver one decisive verdict "
    "the trader can act on. Be concise and honest about uncertainty. Put the verdict "
    "in 'argument'; set role='bull' if net-bullish else role='bear', round=1."
)


async def research_synthesis(state: AgentState) -> dict:
    tracker = CostTracker("research_synthesis")
    llm = get_llm("deep").with_structured_output(DebateTurn, method="function_calling")
    ticker = state.get("resolved_ticker") or state.get("ticker", "")
    human = (
        f"Ticker: {ticker}\n\nAnalyst reports (JSON):\n"
        f"{json.dumps(state.get('analyst_reports', {}), default=str)}\n\n"
        "Deliver the single-pass verdict."
    )
    messages = [SystemMessage(content=SYNTHESIS_SYSTEM), HumanMessage(content=human)]
    verdict: DebateTurn = await llm.ainvoke(messages, config={"callbacks": [tracker]})
    return {
        "research_debate": {
            "rounds": [],
            "bull_thesis": "",
            "bear_thesis": "",
            "facilitator_verdict": verdict.argument,
        },
        "run_metrics": tracker.totals()["per_node"],
    }
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_research_nodes.py -v`
Expected: PASS (5 tests)

- [ ] **Step 5: Commit**

```bash
git add src/agents/research/synthesis.py tests/test_research_nodes.py
git commit -m "feat(wp-d): add single-pass research_synthesis baseline node"
```

---

### Task 11: `build_graph(debate_mode)` toggle — failing tests

**Files:**
- Test: `tests/test_graph_debate_modes.py`

These tests run the graph end-to-end. The real bull/bear/facilitator/synthesis nodes call `get_llm` — we patch it to a scripted fake. Trader/risk/reporter are OTHER WPs; for these tests we keep the Foundation stubs that already live in `src/graph.py` (they require no LLM). The analyst nodes are also still stubs in the Foundation graph and produce `analyst_reports`. We patch `get_llm` in every WP-D research module so the real nodes resolve.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_graph_debate_modes.py
import pytest

from src.llm.schemas import DebateTurn


@pytest.mark.asyncio
async def test_debate_mode_on_produces_full_research_debate(fake_llm_factory):
    # bull(1) + bear(1) + facilitator: debate 1 round x 2 personas (2) + verdict (1) = 5 LLM calls
    scripted = [
        DebateTurn(role="bull", round=1, argument="bull opening"),       # bull node
        DebateTurn(role="bear", round=1, argument="bear opening"),       # bear node
        DebateTurn(role="bull", round=1, argument="bull rebuttal"),      # facilitator debate
        DebateTurn(role="bear", round=1, argument="bear rebuttal"),      # facilitator debate
        DebateTurn(role="bull", round=1, argument="lean BUY verdict"),   # facilitator verdict
    ]
    fake_llm_factory(
        scripted,
        [
            "src.agents.debate",
            "src.agents.research.bull",
            "src.agents.research.bear",
            "src.agents.research.facilitator",
        ],
    )
    from src.graph import build_graph

    app = build_graph(debate_mode="on")
    result = await app.ainvoke({"ticker": "AAPL", "investor_mode": "Neutral"})
    rd = result["research_debate"]
    assert rd["bull_thesis"] == "bull opening"
    assert rd["bear_thesis"] == "bear opening"
    assert rd["facilitator_verdict"] == "lean BUY verdict"
    assert len(rd["rounds"]) == 2


@pytest.mark.asyncio
async def test_debate_mode_off_produces_verdict_only(fake_llm_factory):
    fake_llm_factory(
        [DebateTurn(role="bull", round=1, argument="single-pass lean HOLD")],
        ["src.agents.research.synthesis"],
    )
    from src.graph import build_graph

    app = build_graph(debate_mode="off")
    result = await app.ainvoke({"ticker": "AAPL", "investor_mode": "Neutral"})
    rd = result["research_debate"]
    assert rd["facilitator_verdict"] == "single-pass lean HOLD"
    assert rd.get("bull_thesis", "") == ""
    assert rd.get("bear_thesis", "") == ""


def test_debate_mode_off_does_not_register_debate_nodes():
    from src.graph import build_graph

    app = build_graph(debate_mode="off")
    node_names = set(app.get_graph().nodes)
    assert "research_synthesis" in node_names
    assert "bull" not in node_names
    assert "bear" not in node_names
    assert "facilitator" not in node_names


def test_debate_mode_on_registers_debate_nodes():
    from src.graph import build_graph

    app = build_graph(debate_mode="on")
    node_names = set(app.get_graph().nodes)
    assert {"bull", "bear", "facilitator"} <= node_names
    assert "research_synthesis" not in node_names


def test_build_graph_defaults_to_settings(monkeypatch):
    # No arg -> reads settings.debate_mode (default "on")
    from src.graph import build_graph

    app = build_graph()
    assert "facilitator" in set(app.get_graph().nodes)
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/test_graph_debate_modes.py -v`
Expected: FAIL — `build_graph()` does not yet accept `debate_mode` and the real research nodes are not wired (the Foundation `build_graph` takes no args and wires stub bull/bear/facilitator).

---

### Task 12: `build_graph(debate_mode)` toggle — implementation

**Files:**
- Edit: `src/graph.py` (WP-D owns this)

WP-D rewires `build_graph` to: (1) accept `debate_mode` defaulting to `get_settings().debate_mode`; (2) import the real `bull`, `bear`, `facilitator`, `research_synthesis` nodes; (3) register the `"on"` path (analysts → bull/bear → facilitator → trader) or the `"off"` path (analysts → research_synthesis → trader). Trader, risk, and reporter remain the Foundation stubs already in this file (owned by WP-E/WP-F) — leave them untouched.

- [ ] **Step 1: Read the current graph to locate the edit points**

Run: `python -m pytest tests/test_graph_skeleton.py -v`
Expected: still PASS (Foundation tests). Confirms the stubs you are keeping still work before you edit.

- [ ] **Step 2: Replace the stub `bull`/`bear`/`facilitator` functions and `build_graph` in `src/graph.py`**

Delete the three stub functions `bull`, `bear`, `facilitator` from `src/graph.py` (the real ones now live in `src/agents/research/`). Add these imports near the top of `src/graph.py`, just below `from src.state import AgentState`:

```python
from src.config.settings import get_settings
from src.agents.research.bull import bull
from src.agents.research.bear import bear
from src.agents.research.facilitator import facilitator
from src.agents.research.synthesis import research_synthesis
```

Then replace the entire `build_graph` function body with:

```python
def build_graph(debate_mode: str | None = None):
    """Compile the research pipeline.

    debate_mode:
        "on"  (default from settings) -> bull + bear + facilitator (full M2 debate).
        "off"                         -> single research_synthesis node (A/B baseline).
    Trader / risk / reporter nodes are owned by WP-E / WP-F (stubs until merged).
    """
    if debate_mode is None:
        debate_mode = get_settings().debate_mode

    g = StateGraph(AgentState)

    g.add_node("router", router)
    for name in _ANALYSTS:
        g.add_node(f"{name}_analyst", _analyst(name))
    g.add_node("trader", trader)
    g.add_node("risk_conservative", risk_conservative)
    g.add_node("risk_aggressive", risk_aggressive)
    g.add_node("risk_arbiter", risk_arbiter)
    g.add_node("reporter", reporter)

    g.add_edge(START, "router")
    for name in _ANALYSTS:
        g.add_edge("router", f"{name}_analyst")

    if debate_mode == "off":
        g.add_node("research_synthesis", research_synthesis)
        for name in _ANALYSTS:
            g.add_edge(f"{name}_analyst", "research_synthesis")
        g.add_edge("research_synthesis", "trader")
    else:  # "on"
        g.add_node("bull", bull)
        g.add_node("bear", bear)
        g.add_node("facilitator", facilitator)
        for name in _ANALYSTS:
            g.add_edge(f"{name}_analyst", "bull")
            g.add_edge(f"{name}_analyst", "bear")
        g.add_edge("bull", "facilitator")
        g.add_edge("bear", "facilitator")
        g.add_edge("facilitator", "trader")

    g.add_edge("trader", "risk_conservative")
    g.add_edge("trader", "risk_aggressive")
    g.add_edge("risk_conservative", "risk_arbiter")
    g.add_edge("risk_aggressive", "risk_arbiter")
    g.add_edge("risk_arbiter", "reporter")
    g.add_edge("reporter", END)

    return g.compile()
```

- [ ] **Step 3: Run the WP-D mode tests to verify they pass**

Run: `python -m pytest tests/test_graph_debate_modes.py -v`
Expected: PASS (5 tests). The graph runs async via `await app.ainvoke(...)`; the patched `get_llm` feeds scripted `DebateTurn`s; `research_debate`'s `merge_named_reports` reducer combines bull + bear parallel writes and the facilitator's full overwrite (right-wins).

- [ ] **Step 4: Run the full suite to confirm no regressions**

Run: `python -m pytest -q`
Expected: all PASS. NOTE: the Foundation `tests/test_graph_skeleton.py` used the SYNCHRONOUS stub graph and `app.invoke(...)`. Since the real research nodes are now `async`, the `debate_mode="on"` path must be invoked with `ainvoke`. If `test_graph_skeleton.py::test_graph_runs_end_to_end` (which calls `app.invoke`) now fails because async nodes require `ainvoke`, update those Foundation tests to `await app.ainvoke(...)` under `@pytest.mark.asyncio` (LangGraph runs async nodes under sync `invoke` only if no running loop — to be safe, prefer `ainvoke`). Document this as the one Foundation-test touch-up this WP makes; keep it in the same commit.

- [ ] **Step 5: Commit**

```bash
git add src/graph.py tests/test_graph_debate_modes.py tests/test_graph_skeleton.py
git commit -m "feat(wp-d): wire build_graph(debate_mode) on/off topologies"
```

---

### Task 13: Opt-in live integration test (Ollama Cloud tool-calling probe)

**Files:**
- Test: `tests/test_research_live.py`

This is the single opt-in live test required by COORDINATION §2. It verifies the deep model actually returns structured `DebateTurn`s via tool calling on Ollama Cloud, and confirms the `method="function_calling"` vs `method="json_schema"` decision.

- [ ] **Step 1: Write the live test**

```python
# tests/test_research_live.py
import os

import pytest

from src.agents.debate import run_debate

pytestmark = pytest.mark.live


@pytest.mark.skipif(os.environ.get("RUN_LIVE") != "1", reason="set RUN_LIVE=1 to run")
@pytest.mark.asyncio
async def test_run_debate_live_returns_structured_turns():
    personas = [("bull", "Argue to BUY, one sentence."), ("bear", "Argue to SELL, one sentence.")]
    turns, metrics = await run_debate(
        topic="AAPL",
        context="Strong margins; rich valuation; uptrend.",
        personas=personas,
        rounds=1,
        node_label="research_debate",
    )
    assert len(turns) == 2
    assert all(t.argument for t in turns)
    assert sum(m["completion_tokens"] for m in metrics) > 0
```

- [ ] **Step 2: Register the `live` marker** (append to `pyproject.toml` `[tool.pytest.ini_options]` if not already present)

```toml
markers = [
    "live: opt-in tests that hit real provider APIs (set RUN_LIVE=1)",
]
```

- [ ] **Step 3: Confirm the test is skipped without the flag**

Run: `python -m pytest tests/test_research_live.py -v`
Expected: SKIPPED (1 test).

- [ ] **Step 4: (Optional, manual) Run the live probe to verify tool-calling**

Run: `RUN_LIVE=1 python -m pytest tests/test_research_live.py -v`
Expected: PASS. If it errors with a tool-calling / function-calling unsupported message, change `method="function_calling"` → `method="json_schema"` in `src/agents/debate.py`, `bull.py`, `bear.py`, `facilitator.py`, `synthesis.py`, re-run, and record the change in this plan's Definition of Done.

- [ ] **Step 5: Commit**

```bash
git add tests/test_research_live.py pyproject.toml
git commit -m "test(wp-d): add opt-in live tool-calling probe for run_debate"
```

---

## Dependencies

- **Foundation (`2026-05-29-foundation-and-state-contract.md`) MUST be merged first.** This WP imports `get_llm`, `CostTracker`, `DebateTurn`, `ResearchDebate`, `AgentState`, `merge_named_reports`, `get_settings`, and edits the Foundation `src/graph.py`. Critically, `research_debate` MUST carry the `merge_named_reports` reducer (added in Foundation Task 10 Step 4) — bull and bear write it concurrently.
- **WP-B (router + analysts)** ultimately provides real `analyst_reports`. **Not a blocker:** all WP-D unit tests inject synthetic `analyst_reports` into state, and the end-to-end mode tests use the Foundation analyst stubs that already populate `analyst_reports`. WP-D can be developed and merged before WP-B.
- **Develop-in-parallel note for downstream WPs:**
  - **WP-E** depends on `run_debate` (this WP). If WP-E starts before WP-D merges, it stubs `run_debate` behind the exact COORDINATION §4 signature: `async def run_debate(topic, context, personas, rounds, tier="deep", node_label="debate") -> tuple[list[DebateTurn], dict]`.
  - **WP-H** depends on `build_graph(debate_mode)` (this WP) accepting `"on"`/`"off"` and producing a `research_debate` whose `facilitator_verdict` is always populated in both modes.

## Interfaces this WP exposes (downstream contract — do not change without a coordination event)

- `src/agents/debate.py::run_debate(topic, context, personas, rounds, tier="deep", node_label="debate") -> tuple[list[DebateTurn], dict]` — **consumed by WP-E.**
- `src/graph.py::build_graph(debate_mode: str | None = None)` — `"on"` wires bull→bear→facilitator; `"off"` wires a single `research_synthesis`; `None` reads `get_settings().debate_mode`. **Consumed by WP-G (streams it) and WP-H (A/B harness).**
- State guarantee: in BOTH modes the compiled graph writes `research_debate.facilitator_verdict` (non-empty) before `trader` runs; in `"on"` mode it additionally writes `bull_thesis`, `bear_thesis`, and non-empty `rounds`.

## Definition of Done

- [ ] `python -m pytest tests/test_debate_runner.py tests/test_research_nodes.py tests/test_graph_debate_modes.py -v` is green.
- [ ] `python -m pytest -q` (full suite) is green, including the touched-up Foundation graph test.
- [ ] `run_debate` respects `rounds` (turns == rounds × len(personas)), alternates personas in order, clamps `rounds<1` to 1, and aggregates all LLM-call metrics under a single `node_label`.
- [ ] `bull` and `bear` each write exactly their own thesis key and are parallel-safe via the `research_debate` merge reducer.
- [ ] `facilitator` runs `run_debate`, preserves the upstream theses, writes `rounds` + `facilitator_verdict`, and concatenates debate + verdict metrics.
- [ ] `research_synthesis` does ONE deep pass and writes `facilitator_verdict` only (empty theses/rounds).
- [ ] `build_graph("on")` registers `bull`/`bear`/`facilitator` (not `research_synthesis`); `build_graph("off")` registers `research_synthesis` (not the debate nodes); `build_graph()` reads `settings.debate_mode`. Verified via `app.get_graph().nodes`.
- [ ] Both modes run end-to-end (`await app.ainvoke(...)`) on mocked LLMs producing a populated `research_debate`.
- [ ] One opt-in `@pytest.mark.live` test exists and is skipped unless `RUN_LIVE=1`; the `function_calling` vs `json_schema` decision is recorded here (default: `function_calling`; switch documented if the live probe fails).
- [ ] No network calls in any non-live test; `get_llm` is mocked everywhere.
- [ ] No frozen contract was modified (only consumed); `build_graph` evolution stays within the COORDINATION §4 mandate.

# WP-E: Trader + Risk Debate Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the `trader`, `risk_conservative`, `risk_aggressive`, and `risk_arbiter` stub nodes with real LLM-backed logic. The trader synthesizes analyst reports + the research facilitator verdict into a structured `TradeProposal`. The two risk personas each emit a stance on that proposal, and the arbiter runs a bounded conservative↔aggressive debate (folding the paper's fund-manager role) to produce a `FinalDecision`, persisting it to the memory cache.

**Architecture:** Four async LangGraph nodes coded against the frozen contract from the Foundation plan. Each node builds short `SystemMessage`/`HumanMessage` lists, calls `get_llm("deep").with_structured_output(Model, method="function_calling")`, awaits `ainvoke(messages, config={"callbacks": [tracker]})`, and returns contract-shaped deltas plus `run_metrics`. Risk personas write into the merge-reduced `risk_debate` key (different sub-keys, no write conflict). The arbiter reuses WP-D's shared `run_debate` for the bounded persona debate and consumes WP-C's `store_verdict` cache — both behind parallel-dev fallbacks so this WP can be developed and tested in isolation.

**Tech Stack:** Python 3.13, `langgraph==1.0.4`, `langchain-core==1.2.5`, `langchain-openai==1.1.6`, `pydantic==2.12.5`, `pytest==8.4.2`, `pytest-asyncio>=0.24`. No new runtime dependencies.

---

## Context for the implementer

This WP replaces 4 stub nodes frozen by the Foundation plan (`src/graph.py`). Do NOT edit `src/graph.py`, `src/state.py`, or `src/llm/schemas.py` — those are the **frozen contract**. WP-D rewires `build_graph` to import the real nodes; this WP only provides the node modules at the import paths WP-D expects:

- `src/agents/trader.py` → `async def trader(state)`
- `src/agents/risk/conservative.py` → `async def risk_conservative(state)`
- `src/agents/risk/aggressive.py` → `async def risk_aggressive(state)`
- `src/agents/risk/arbiter.py` → `async def risk_arbiter(state)`

**Verified APIs (Context7, langchain docs, 2026-05-29):**
- `llm.with_structured_output(Model, method="function_calling")` returns a runnable that, when awaited via `ainvoke(messages, config=...)`, resolves to a **validated instance of `Model`** (e.g. `TradeProposal(...)`), not a dict. Store `result.model_dump()` into state. (`method="json_schema"` is the documented fallback if a model lacks tool calling.)
- `ainvoke(messages)` is the async invoke; `messages` is a `list` of message objects.
- `SystemMessage` / `HumanMessage` import from `langchain_core.messages` (canonical path used across this repo per COORDINATION §6 and the Foundation plan's `langchain_core.callbacks` usage).

**Conventions (COORDINATION §2):** async nodes; one `CostTracker(node_name)` per node passed as a callback to every LLM call; return `"run_metrics": tracker.totals()["per_node"]`; module-level prompt constants; absolute imports; no network in unit tests (mock `get_llm`, `run_debate`, `store_verdict`).

## File Structure

| File | Responsibility |
|---|---|
| `src/agents/__init__.py` | Package marker (create if absent) |
| `src/agents/trader.py` | `trader` node: synthesize reports + facilitator verdict → `TradeProposal` |
| `src/agents/risk/__init__.py` | Package marker |
| `src/agents/risk/_debate_stub.py` | Local parallel-dev stub of WP-D's `run_debate` (DELETE on integration) |
| `src/agents/risk/conservative.py` | `risk_conservative` node: capital-preservation stance on the proposal |
| `src/agents/risk/aggressive.py` | `risk_aggressive` node: upside-maximizing stance on the proposal |
| `src/agents/risk/arbiter.py` | `risk_arbiter` node: bounded persona debate → `FinalDecision` + `store_verdict` |
| `tests/agents/__init__.py` | Package marker for test discovery |
| `tests/agents/conftest.py` | Shared fakes: `FakeStructuredLLM`, `patch_get_llm` helper |
| `tests/agents/test_trader.py` | Trader maps LLM output → `trade_proposal`; emits metrics |
| `tests/agents/test_risk_personas.py` | Conservative/aggressive write correct `risk_debate` sub-keys |
| `tests/agents/test_risk_arbiter.py` | Arbiter → valid `FinalDecision`; calls `store_verdict`; respects `risk_debate_rounds` |

---

### Task 1: Package markers + shared test fakes

**Files:**
- Create: `src/agents/__init__.py`, `src/agents/risk/__init__.py`, `tests/agents/__init__.py`
- Create: `tests/agents/conftest.py`

- [ ] **Step 1: Create the three empty package markers**

```python
# src/agents/__init__.py
```

```python
# src/agents/risk/__init__.py
```

```python
# tests/agents/__init__.py
```

(If `src/agents/__init__.py` already exists from legacy code, leave its content but ensure it does not import legacy modules at top level — if it does, replace it with an empty file. The new WP-E modules must import cleanly.)

- [ ] **Step 2: Create `tests/agents/conftest.py`** — the single source of LLM fakes for all WP-E tests

```python
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
```

- [ ] **Step 3: Commit**

```bash
git add src/agents/__init__.py src/agents/risk/__init__.py tests/agents/__init__.py tests/agents/conftest.py
git commit -m "test(wp-e): add package markers and shared LLM fakes"
```

---

### Task 2: Local `run_debate` stub (parallel-dev fallback for WP-D)

**Files:**
- Create: `src/agents/risk/_debate_stub.py`

> **Dependency decision (COORDINATION §4):** WP-D owns `src/agents/debate.py::run_debate`. Per the coordination contract this WP picks option **(b): develop in parallel behind the identical signature.** The arbiter imports `run_debate` from WP-D's module if present, else falls back to this local stub. **DELETE this file and the fallback branch on integration once WP-D is merged** (see Task 5, Step "integration note").

- [ ] **Step 1: Create `src/agents/risk/_debate_stub.py`** — identical signature to WP-D's `run_debate`

```python
# src/agents/risk/_debate_stub.py
"""PARALLEL-DEV STUB of WP-D's src/agents/debate.py::run_debate.

Identical signature to the frozen contract (COORDINATION §4). Used ONLY when
WP-D is not yet merged so WP-E composes and its unit tests run. DELETE this file
and the import fallback in arbiter.py once WP-D lands.

The stub does a single non-LLM turn per persona per round so the arbiter has a
deterministic, network-free debate transcript to summarize. Real run_debate
calls the LLM; the arbiter does not depend on transcript *content*, only shape.
"""
from __future__ import annotations

from src.llm.schemas import DebateTurn


async def run_debate(
    topic: str,
    context: str,
    personas: list[tuple[str, str]],
    rounds: int,
    tier: str = "deep",
    node_label: str = "debate",
) -> tuple[list[DebateTurn], dict]:
    turns: list[DebateTurn] = []
    for r in range(1, rounds + 1):
        for role, _system_prompt in personas:
            turns.append(
                DebateTurn(
                    role=role,
                    round=r,
                    argument=f"[stub {role} r{r}] on: {topic}",
                )
            )
    metrics = [
        {
            "node": node_label,
            "model": "",
            "prompt_tokens": 0,
            "completion_tokens": 0,
            "latency_s": 0.0,
            "cost_usd": 0.0,
        }
    ]
    return turns, metrics
```

- [ ] **Step 2: Sanity-check it imports and runs**

Run: `python -c "import asyncio; from src.agents.risk._debate_stub import run_debate; print(asyncio.run(run_debate('t','c',[('conservative','s'),('aggressive','s')],2))[0])"`
Expected: prints a list of 4 `DebateTurn` objects (2 personas × 2 rounds), roles `conservative`/`aggressive`, rounds 1 and 2.

- [ ] **Step 3: Commit**

```bash
git add src/agents/risk/_debate_stub.py
git commit -m "feat(wp-e): add parallel-dev run_debate stub (delete on WP-D merge)"
```

---

### Task 3: Trader node — test

**Files:**
- Test: `tests/agents/test_trader.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/agents/test_trader.py
import pytest
from langchain_core.messages import SystemMessage, HumanMessage

from src.agents import trader as trader_mod
from src.llm.schemas import TradeProposal


@pytest.mark.asyncio
async def test_trader_maps_llm_output_to_trade_proposal(monkeypatch, make_fake_llm):
    proposal = TradeProposal(action="BUY", conviction=0.82, score=74, rationale="strong setup")
    fake = make_fake_llm([proposal])
    monkeypatch.setattr(trader_mod, "get_llm", lambda tier: fake)

    state = {
        "ticker": "AAPL",
        "resolved_ticker": "AAPL",
        "analyst_reports": {
            "news": {"summary": "upbeat coverage", "confidence": 0.6},
            "fundamentals": {"summary": "P/E reasonable", "confidence": 0.7},
            "technicals": {"summary": "RSI neutral", "confidence": 0.5},
        },
        "research_debate": {
            "bull_thesis": "growth", "bear_thesis": "valuation",
            "facilitator_verdict": "lean bullish",
        },
    }

    out = await trader_mod.trader(state)

    assert out["trade_proposal"] == proposal.model_dump()
    assert out["trade_proposal"]["action"] == "BUY"
    assert out["trade_proposal"]["score"] == 74
    # deep tier requested for structured output via function_calling
    assert fake.structured_args[0]["schema"] is TradeProposal
    assert fake.structured_args[0]["method"] == "function_calling"


@pytest.mark.asyncio
async def test_trader_emits_metrics_and_passes_callback(monkeypatch, make_fake_llm):
    proposal = TradeProposal(action="HOLD", conviction=0.5, score=50, rationale="mixed")
    fake = make_fake_llm([proposal])
    monkeypatch.setattr(trader_mod, "get_llm", lambda tier: fake)

    out = await trader_mod.trader({"ticker": "AAPL", "analyst_reports": {}, "research_debate": {}})

    assert isinstance(out["run_metrics"], list)
    assert out["run_metrics"][0]["node"] == "trader"
    # the CostTracker was passed as a callback on the LLM call
    cfg = fake.structured[0].calls[0]["config"]
    assert "callbacks" in cfg and len(cfg["callbacks"]) == 1


@pytest.mark.asyncio
async def test_trader_prompt_includes_facilitator_verdict(monkeypatch, make_fake_llm):
    proposal = TradeProposal(action="SELL", conviction=0.6, score=30, rationale="overvalued")
    fake = make_fake_llm([proposal])
    monkeypatch.setattr(trader_mod, "get_llm", lambda tier: fake)

    await trader_mod.trader({
        "ticker": "AAPL",
        "analyst_reports": {"news": {"summary": "x"}},
        "research_debate": {"facilitator_verdict": "lean bearish on valuation"},
    })

    messages = fake.structured[0].calls[0]["messages"]
    assert isinstance(messages[0], SystemMessage)
    assert isinstance(messages[1], HumanMessage)
    assert "lean bearish on valuation" in messages[1].content
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/agents/test_trader.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'src.agents.trader'`

---

### Task 4: Trader node — implementation

**Files:**
- Create: `src/agents/trader.py`

- [ ] **Step 1: Write the implementation**

```python
# src/agents/trader.py
"""Trader node: fold analyst reports + the research facilitator verdict into a
single structured TradeProposal (action / conviction / score / rationale)."""
from __future__ import annotations

import json

from langchain_core.messages import HumanMessage, SystemMessage

from src.llm.cost import CostTracker
from src.llm.factory import get_llm
from src.llm.schemas import TradeProposal
from src.state import AgentState

TRADER_SYSTEM = (
    "You are a disciplined buy-side trader. Synthesize the analyst reports and the "
    "research debate's facilitator verdict into ONE trade decision. Output a TradeProposal: "
    "action (BUY/SELL/HOLD), conviction (0..1), score (0..100, higher = more bullish), and a "
    "concise rationale grounded ONLY in the supplied evidence. Do not invent data. If signals "
    "conflict or are thin, prefer HOLD with moderate conviction."
)


def _build_human_message(state: AgentState) -> HumanMessage:
    ticker = state.get("resolved_ticker") or state.get("ticker", "UNKNOWN")
    reports = state.get("analyst_reports", {}) or {}
    debate = state.get("research_debate", {}) or {}
    facilitator = debate.get("facilitator_verdict", "") or "(no facilitator verdict)"
    content = (
        f"Ticker: {ticker}\n"
        f"Investor mode: {state.get('investor_mode', 'Neutral')}\n\n"
        f"Analyst reports (by analyst):\n{json.dumps(reports, indent=2, default=str)}\n\n"
        f"Research debate facilitator verdict:\n{facilitator}\n"
        f"Bull thesis: {debate.get('bull_thesis', '')}\n"
        f"Bear thesis: {debate.get('bear_thesis', '')}\n\n"
        "Produce the TradeProposal now."
    )
    return HumanMessage(content=content)


async def trader(state: AgentState) -> dict:
    tracker = CostTracker("trader")
    llm = get_llm("deep").with_structured_output(TradeProposal, method="function_calling")
    messages = [SystemMessage(content=TRADER_SYSTEM), _build_human_message(state)]
    result: TradeProposal = await llm.ainvoke(messages, config={"callbacks": [tracker]})
    return {
        "trade_proposal": result.model_dump(),
        "run_metrics": tracker.totals()["per_node"],
    }
```

- [ ] **Step 2: Run test to verify it passes**

Run: `python -m pytest tests/agents/test_trader.py -v`
Expected: PASS (3 tests)

- [ ] **Step 3: Commit**

```bash
git add src/agents/trader.py tests/agents/test_trader.py
git commit -m "feat(wp-e): add trader node producing structured TradeProposal"
```

---

### Task 5: Risk personas (conservative + aggressive) — test

**Files:**
- Test: `tests/agents/test_risk_personas.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/agents/test_risk_personas.py
import pytest

from src.agents.risk import conservative as cons_mod
from src.agents.risk import aggressive as aggr_mod
from src.agents.risk.conservative import RiskStance


@pytest.mark.asyncio
async def test_conservative_writes_conservative_key(monkeypatch, make_fake_llm):
    stance = RiskStance(stance="Trim size; valuation risk into earnings.")
    fake = make_fake_llm([stance])
    monkeypatch.setattr(cons_mod, "get_llm", lambda tier: fake)

    state = {
        "resolved_ticker": "AAPL",
        "trade_proposal": {"action": "BUY", "conviction": 0.8, "score": 74, "rationale": "r"},
    }
    out = await cons_mod.risk_conservative(state)

    assert set(out["risk_debate"]) == {"conservative"}
    assert out["risk_debate"]["conservative"] == "Trim size; valuation risk into earnings."
    assert out["run_metrics"][0]["node"] == "risk_conservative"
    assert fake.structured_args[0]["schema"] is RiskStance
    assert fake.structured_args[0]["method"] == "function_calling"


@pytest.mark.asyncio
async def test_aggressive_writes_aggressive_key(monkeypatch, make_fake_llm):
    from src.agents.risk.aggressive import RiskStance as AggrStance
    stance = AggrStance(stance="Press the position; momentum favors upside.")
    fake = make_fake_llm([stance])
    monkeypatch.setattr(aggr_mod, "get_llm", lambda tier: fake)

    state = {
        "resolved_ticker": "AAPL",
        "trade_proposal": {"action": "BUY", "conviction": 0.8, "score": 74, "rationale": "r"},
    }
    out = await aggr_mod.risk_aggressive(state)

    assert set(out["risk_debate"]) == {"aggressive"}
    assert out["risk_debate"]["aggressive"] == "Press the position; momentum favors upside."
    assert out["run_metrics"][0]["node"] == "risk_aggressive"


@pytest.mark.asyncio
async def test_personas_write_disjoint_keys_for_merge_reducer(monkeypatch, make_fake_llm):
    """conservative + aggressive run in parallel; they must write different sub-keys
    so merge_named_reports combines them without conflict."""
    cons_fake = make_fake_llm([cons_mod.RiskStance(stance="careful")])
    aggr_fake = make_fake_llm([aggr_mod.RiskStance(stance="bold")])
    monkeypatch.setattr(cons_mod, "get_llm", lambda tier: cons_fake)
    monkeypatch.setattr(aggr_mod, "get_llm", lambda tier: aggr_fake)

    proposal = {"action": "HOLD", "conviction": 0.5, "score": 50, "rationale": "r"}
    c = await cons_mod.risk_conservative({"trade_proposal": proposal})
    a = await aggr_mod.risk_aggressive({"trade_proposal": proposal})

    from src.state import merge_named_reports
    merged = merge_named_reports(c["risk_debate"], a["risk_debate"])
    assert merged == {"conservative": "careful", "aggressive": "bold"}
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/agents/test_risk_personas.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'src.agents.risk.conservative'`

---

### Task 6: Conservative risk node — implementation

**Files:**
- Create: `src/agents/risk/conservative.py`

> **Schema choice:** the frozen `RiskDebate` schema stores persona stances as plain strings (`conservative: str`, `aggressive: str`). Per the task brief, each persona module defines a **small local Pydantic stance model** (`RiskStance`) for `with_structured_output` — this does NOT touch the frozen schemas. The node extracts `.stance` and writes the string into the merge-reduced `risk_debate` dict.

- [ ] **Step 1: Write the implementation**

```python
# src/agents/risk/conservative.py
"""Conservative risk persona: capital-preservation critique of the trade proposal.
Writes its stance string into risk_debate['conservative'] (merge-reduced key)."""
from __future__ import annotations

import json

from langchain_core.messages import HumanMessage, SystemMessage
from pydantic import BaseModel, Field

from src.llm.cost import CostTracker
from src.llm.factory import get_llm
from src.state import AgentState


class RiskStance(BaseModel):
    """Local structured-output target for a risk persona. Not part of the frozen
    contract; the node unwraps `.stance` into the RiskDebate string field."""

    stance: str = Field(description="The persona's concise risk stance on the trade proposal.")


CONSERVATIVE_SYSTEM = (
    "You are the CONSERVATIVE risk officer. Your mandate is capital preservation. "
    "Critique the trade proposal: surface downside, drawdown, liquidity, concentration, and "
    "tail risks. Argue for smaller size, tighter stops, or HOLD when uncertainty is high. "
    "Be specific and grounded in the proposal; one or two tight paragraphs."
)


def _human(state: AgentState) -> HumanMessage:
    proposal = state.get("trade_proposal", {}) or {}
    ticker = state.get("resolved_ticker") or state.get("ticker", "UNKNOWN")
    return HumanMessage(
        content=(
            f"Ticker: {ticker}\n"
            f"Proposed trade:\n{json.dumps(proposal, indent=2, default=str)}\n\n"
            "Give your conservative risk stance."
        )
    )


async def risk_conservative(state: AgentState) -> dict:
    tracker = CostTracker("risk_conservative")
    llm = get_llm("deep").with_structured_output(RiskStance, method="function_calling")
    messages = [SystemMessage(content=CONSERVATIVE_SYSTEM), _human(state)]
    result: RiskStance = await llm.ainvoke(messages, config={"callbacks": [tracker]})
    return {
        "risk_debate": {"conservative": result.stance},
        "run_metrics": tracker.totals()["per_node"],
    }
```

- [ ] **Step 2: Run test to verify it passes (conservative portions)**

Run: `python -m pytest tests/agents/test_risk_personas.py -k conservative -v`
Expected: PASS for the conservative test. The aggressive/disjoint tests still fail (module missing) — that is expected until Task 7.

---

### Task 7: Aggressive risk node — implementation

**Files:**
- Create: `src/agents/risk/aggressive.py`

- [ ] **Step 1: Write the implementation**

```python
# src/agents/risk/aggressive.py
"""Aggressive risk persona: upside-maximizing case for the trade proposal.
Writes its stance string into risk_debate['aggressive'] (merge-reduced key)."""
from __future__ import annotations

import json

from langchain_core.messages import HumanMessage, SystemMessage
from pydantic import BaseModel, Field

from src.llm.cost import CostTracker
from src.llm.factory import get_llm
from src.state import AgentState


class RiskStance(BaseModel):
    """Local structured-output target for a risk persona. Not part of the frozen
    contract; the node unwraps `.stance` into the RiskDebate string field."""

    stance: str = Field(description="The persona's concise risk stance on the trade proposal.")


AGGRESSIVE_SYSTEM = (
    "You are the AGGRESSIVE risk officer. Your mandate is return maximization within "
    "mandate. Make the case for taking (or increasing) the position: highlight asymmetric "
    "upside, momentum, catalysts, and the opportunity cost of inaction. Push back on "
    "over-caution where the reward justifies the risk. One or two tight paragraphs, grounded "
    "in the proposal."
)


def _human(state: AgentState) -> HumanMessage:
    proposal = state.get("trade_proposal", {}) or {}
    ticker = state.get("resolved_ticker") or state.get("ticker", "UNKNOWN")
    return HumanMessage(
        content=(
            f"Ticker: {ticker}\n"
            f"Proposed trade:\n{json.dumps(proposal, indent=2, default=str)}\n\n"
            "Give your aggressive risk stance."
        )
    )


async def risk_aggressive(state: AgentState) -> dict:
    tracker = CostTracker("risk_aggressive")
    llm = get_llm("deep").with_structured_output(RiskStance, method="function_calling")
    messages = [SystemMessage(content=AGGRESSIVE_SYSTEM), _human(state)]
    result: RiskStance = await llm.ainvoke(messages, config={"callbacks": [tracker]})
    return {
        "risk_debate": {"aggressive": result.stance},
        "run_metrics": tracker.totals()["per_node"],
    }
```

- [ ] **Step 2: Run test to verify the whole personas suite passes**

Run: `python -m pytest tests/agents/test_risk_personas.py -v`
Expected: PASS (3 tests)

- [ ] **Step 3: Commit**

```bash
git add src/agents/risk/conservative.py src/agents/risk/aggressive.py tests/agents/test_risk_personas.py
git commit -m "feat(wp-e): add conservative + aggressive risk persona nodes"
```

---

### Task 8: Risk arbiter — test

**Files:**
- Test: `tests/agents/test_risk_arbiter.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/agents/test_risk_arbiter.py
import pytest

from src.agents.risk import arbiter as arb_mod
from src.llm.schemas import DebateTurn, FinalDecision


def _base_state():
    return {
        "ticker": "AAPL",
        "resolved_ticker": "AAPL",
        "trade_proposal": {"action": "BUY", "conviction": 0.8, "score": 74, "rationale": "r"},
        "risk_debate": {"conservative": "trim size", "aggressive": "press it"},
    }


@pytest.mark.asyncio
async def test_arbiter_produces_valid_final_decision(monkeypatch, make_fake_llm):
    decision = FinalDecision(action="HOLD", conviction=0.55, score=58,
                             rationale="Balanced down from BUY given valuation risk.")
    fake = make_fake_llm([decision])
    monkeypatch.setattr(arb_mod, "get_llm", lambda tier: fake)

    async def fake_run_debate(topic, context, personas, rounds, tier="deep", node_label="debate"):
        turns = [DebateTurn(role="conservative", round=1, argument="careful"),
                 DebateTurn(role="aggressive", round=1, argument="bold")]
        return turns, [{"node": node_label, "prompt_tokens": 0, "completion_tokens": 0,
                        "latency_s": 0.0, "cost_usd": 0.0, "model": ""}]
    monkeypatch.setattr(arb_mod, "run_debate", fake_run_debate)
    monkeypatch.setattr(arb_mod, "store_verdict", lambda *a, **k: None)

    out = await arb_mod.risk_arbiter(_base_state())

    fd = out["final_decision"]
    assert fd == decision.model_dump()
    assert fd["action"] in {"BUY", "SELL", "HOLD"}
    # risk_debate is enriched with the transcript + arbiter decision + adjustments
    rd = out["risk_debate"]
    assert len(rd["rounds"]) == 2
    assert rd["arbiter_decision"]
    assert isinstance(rd["adjustments"], list)
    assert fake.structured_args[0]["schema"] is FinalDecision
    assert fake.structured_args[0]["method"] == "function_calling"


@pytest.mark.asyncio
async def test_arbiter_calls_store_verdict_with_ticker_and_decision(monkeypatch, make_fake_llm):
    decision = FinalDecision(action="BUY", conviction=0.7, score=70, rationale="ok")
    fake = make_fake_llm([decision])
    monkeypatch.setattr(arb_mod, "get_llm", lambda tier: fake)

    async def fake_run_debate(*a, **k):
        return [], [{"node": "risk_debate", "prompt_tokens": 0, "completion_tokens": 0,
                     "latency_s": 0.0, "cost_usd": 0.0, "model": ""}]
    monkeypatch.setattr(arb_mod, "run_debate", fake_run_debate)

    calls = []
    monkeypatch.setattr(arb_mod, "store_verdict", lambda ticker, dec: calls.append((ticker, dec)))

    await arb_mod.risk_arbiter(_base_state())

    assert len(calls) == 1
    ticker, dec = calls[0]
    assert ticker == "AAPL"
    # store_verdict receives a FinalDecision instance (per WP-C signature)
    assert isinstance(dec, FinalDecision)
    assert dec.action == "BUY"


@pytest.mark.asyncio
async def test_arbiter_respects_risk_debate_rounds(monkeypatch, make_fake_llm):
    decision = FinalDecision(action="HOLD", conviction=0.5, score=50, rationale="x")
    fake = make_fake_llm([decision])
    monkeypatch.setattr(arb_mod, "get_llm", lambda tier: fake)

    captured = {}

    async def fake_run_debate(topic, context, personas, rounds, tier="deep", node_label="debate"):
        captured["rounds"] = rounds
        captured["personas"] = [p[0] for p in personas]
        return [], [{"node": node_label, "prompt_tokens": 0, "completion_tokens": 0,
                     "latency_s": 0.0, "cost_usd": 0.0, "model": ""}]
    monkeypatch.setattr(arb_mod, "run_debate", fake_run_debate)
    monkeypatch.setattr(arb_mod, "store_verdict", lambda *a, **k: None)

    # Patch settings so risk_debate_rounds is a known value.
    class _S:
        risk_debate_rounds = 3
    monkeypatch.setattr(arb_mod, "get_settings", lambda: _S())

    await arb_mod.risk_arbiter(_base_state())

    assert captured["rounds"] == 3
    assert captured["personas"] == ["conservative", "aggressive"]


@pytest.mark.asyncio
async def test_arbiter_survives_missing_store_verdict(monkeypatch, make_fake_llm):
    """If WP-C is not merged, store_verdict is None; arbiter must still produce a decision."""
    decision = FinalDecision(action="SELL", conviction=0.6, score=30, rationale="x")
    fake = make_fake_llm([decision])
    monkeypatch.setattr(arb_mod, "get_llm", lambda tier: fake)

    async def fake_run_debate(*a, **k):
        return [], [{"node": "risk_debate", "prompt_tokens": 0, "completion_tokens": 0,
                     "latency_s": 0.0, "cost_usd": 0.0, "model": ""}]
    monkeypatch.setattr(arb_mod, "run_debate", fake_run_debate)
    monkeypatch.setattr(arb_mod, "store_verdict", None)  # simulate unavailable cache

    out = await arb_mod.risk_arbiter(_base_state())
    assert out["final_decision"]["action"] == "SELL"


@pytest.mark.asyncio
async def test_arbiter_metrics_include_debate_and_arbiter(monkeypatch, make_fake_llm):
    decision = FinalDecision(action="HOLD", conviction=0.5, score=50, rationale="x")
    fake = make_fake_llm([decision])
    monkeypatch.setattr(arb_mod, "get_llm", lambda tier: fake)

    async def fake_run_debate(*a, **k):
        return [], [{"node": "risk_debate", "prompt_tokens": 1, "completion_tokens": 1,
                     "latency_s": 0.0, "cost_usd": 0.0, "model": ""}]
    monkeypatch.setattr(arb_mod, "run_debate", fake_run_debate)
    monkeypatch.setattr(arb_mod, "store_verdict", lambda *a, **k: None)

    out = await arb_mod.risk_arbiter(_base_state())
    nodes = {m["node"] for m in out["run_metrics"]}
    assert "risk_debate" in nodes        # from run_debate
    assert "risk_arbiter" in nodes       # from the arbiter's own decision call
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/agents/test_risk_arbiter.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'src.agents.risk.arbiter'`

---

### Task 9: Risk arbiter — implementation

**Files:**
- Create: `src/agents/risk/arbiter.py`

> **Dependency handling (both behind parallel-dev fallbacks):**
> - **`run_debate` (WP-D):** import from `src.agents.debate` if merged, else fall back to the Task-2 local stub. The fallback branch and `_debate_stub.py` are deleted on integration.
> - **`store_verdict` (WP-C):** import from `src.memory.cache` guarded by `try/except ImportError`, defaulting to `None`. The arbiter only calls it when not `None`, wrapped in a defensive `try/except`, so a cache failure never breaks the decision.
> - **`get_settings`:** imported at module level so tests can monkeypatch `arb_mod.get_settings` to control `risk_debate_rounds`.

- [ ] **Step 1: Write the implementation**

```python
# src/agents/risk/arbiter.py
"""Risk arbiter node: run a bounded conservative<->aggressive debate (reusing WP-D's
run_debate), then act as the fund manager — fold both stances into a FinalDecision that
adjusts the trader's proposal. Persists the verdict to the memory cache (WP-C) if present."""
from __future__ import annotations

import json

from langchain_core.messages import HumanMessage, SystemMessage

from src.config.settings import get_settings
from src.llm.cost import CostTracker
from src.llm.factory import get_llm
from src.llm.schemas import FinalDecision
from src.state import AgentState

# --- run_debate: WP-D owns it; fall back to the local parallel-dev stub. ---
# INTEGRATION NOTE: once WP-D is merged, delete the except-branch and
# src/agents/risk/_debate_stub.py so only the real import remains.
try:
    from src.agents.debate import run_debate
except ImportError:  # pragma: no cover - exercised only pre-WP-D-merge
    from src.agents.risk._debate_stub import run_debate

# --- store_verdict: WP-C owns it; guard so the graph runs if memory isn't merged. ---
try:
    from src.memory.cache import store_verdict
except ImportError:  # pragma: no cover - exercised only pre-WP-C-merge
    store_verdict = None  # type: ignore[assignment]


CONSERVATIVE_PROMPT = (
    "You are the CONSERVATIVE risk officer in a risk committee debate. Defend capital "
    "preservation: downside, drawdown, sizing, and HOLD when uncertain. Rebut the aggressive "
    "officer directly and concisely."
)
AGGRESSIVE_PROMPT = (
    "You are the AGGRESSIVE risk officer in a risk committee debate. Defend taking the "
    "opportunity: asymmetric upside, momentum, catalysts, opportunity cost. Rebut the "
    "conservative officer directly and concisely."
)

ARBITER_SYSTEM = (
    "You are the FUND MANAGER chairing the risk committee. You have the trader's proposal, both "
    "risk officers' opening stances, and the full debate transcript. Render the FINAL decision: "
    "action (BUY/SELL/HOLD), conviction (0..1), score (0..100), and a rationale that explains how "
    "you weighed the conservative vs aggressive arguments and what you adjusted from the trader's "
    "proposal (e.g. downgraded BUY->HOLD, trimmed conviction). Ground every claim in the inputs."
)


def _transcript(turns) -> str:
    if not turns:
        return "(no debate turns)"
    return "\n".join(f"[r{t.round}] {t.role}: {t.argument}" for t in turns)


def _arbiter_human(state: AgentState, turns, conservative: str, aggressive: str) -> HumanMessage:
    ticker = state.get("resolved_ticker") or state.get("ticker", "UNKNOWN")
    proposal = state.get("trade_proposal", {}) or {}
    content = (
        f"Ticker: {ticker}\n"
        f"Trader proposal:\n{json.dumps(proposal, indent=2, default=str)}\n\n"
        f"Conservative opening stance: {conservative or '(none)'}\n"
        f"Aggressive opening stance: {aggressive or '(none)'}\n\n"
        f"Debate transcript:\n{_transcript(turns)}\n\n"
        "Render the FinalDecision now."
    )
    return HumanMessage(content=content)


def _derive_adjustments(proposal: dict, decision: FinalDecision) -> list[str]:
    """Human-readable diff of what the arbiter changed vs the trader's proposal."""
    adjustments: list[str] = []
    if proposal.get("action") and proposal["action"] != decision.action:
        adjustments.append(f"action {proposal['action']} -> {decision.action}")
    if "conviction" in proposal and proposal["conviction"] != decision.conviction:
        adjustments.append(f"conviction {proposal['conviction']} -> {decision.conviction}")
    if "score" in proposal and proposal["score"] != decision.score:
        adjustments.append(f"score {proposal['score']} -> {decision.score}")
    return adjustments


async def risk_arbiter(state: AgentState) -> dict:
    tracker = CostTracker("risk_arbiter")
    settings = get_settings()
    rounds = settings.risk_debate_rounds

    risk_debate = state.get("risk_debate", {}) or {}
    conservative = risk_debate.get("conservative", "")
    aggressive = risk_debate.get("aggressive", "")
    proposal = state.get("trade_proposal", {}) or {}
    ticker = state.get("resolved_ticker") or state.get("ticker", "UNKNOWN")

    # 1. Bounded conservative<->aggressive debate (reused from WP-D).
    context = (
        f"Trade proposal for {ticker}: {json.dumps(proposal, default=str)}\n"
        f"Conservative opening: {conservative}\nAggressive opening: {aggressive}"
    )
    turns, debate_metrics = await run_debate(
        topic=f"Risk of the proposed trade on {ticker}",
        context=context,
        personas=[("conservative", CONSERVATIVE_PROMPT), ("aggressive", AGGRESSIVE_PROMPT)],
        rounds=rounds,
        tier="deep",
        node_label="risk_debate",
    )

    # 2. Fund-manager FinalDecision.
    llm = get_llm("deep").with_structured_output(FinalDecision, method="function_calling")
    messages = [
        SystemMessage(content=ARBITER_SYSTEM),
        _arbiter_human(state, turns, conservative, aggressive),
    ]
    decision: FinalDecision = await llm.ainvoke(messages, config={"callbacks": [tracker]})

    # 3. Persist to memory cache if WP-C is available (never break on failure).
    if store_verdict is not None:
        try:
            store_verdict(ticker, decision)
        except Exception:  # pragma: no cover - defensive; cache must never break the run
            pass

    adjustments = _derive_adjustments(proposal, decision)
    metrics = list(debate_metrics) + tracker.totals()["per_node"]
    return {
        "final_decision": decision.model_dump(),
        "risk_debate": {
            "rounds": [t.model_dump() for t in turns],
            "arbiter_decision": decision.rationale,
            "adjustments": adjustments,
        },
        "run_metrics": metrics,
    }
```

- [ ] **Step 2: Run test to verify it passes**

Run: `python -m pytest tests/agents/test_risk_arbiter.py -v`
Expected: PASS (5 tests)

- [ ] **Step 3: Commit**

```bash
git add src/agents/risk/arbiter.py tests/agents/test_risk_arbiter.py
git commit -m "feat(wp-e): add risk arbiter with bounded debate + FinalDecision + cache"
```

---

### Task 10: Full-suite regression + node import contract check

**Files:**
- (no new files)

- [ ] **Step 1: Confirm the four node functions are importable at the paths WP-D expects**

Run: `python -c "from src.agents.trader import trader; from src.agents.risk.conservative import risk_conservative; from src.agents.risk.aggressive import risk_aggressive; from src.agents.risk.arbiter import risk_arbiter; print('ok', trader.__name__, risk_conservative.__name__, risk_aggressive.__name__, risk_arbiter.__name__)"`
Expected: `ok trader risk_conservative risk_aggressive risk_arbiter`

- [ ] **Step 2: Confirm all four are async coroutine functions**

Run: `python -c "import inspect; from src.agents.trader import trader; from src.agents.risk.arbiter import risk_arbiter; from src.agents.risk.conservative import risk_conservative; from src.agents.risk.aggressive import risk_aggressive; assert all(inspect.iscoroutinefunction(f) for f in [trader, risk_arbiter, risk_conservative, risk_aggressive]); print('all async')"`
Expected: `all async`

- [ ] **Step 3: Run the full test suite**

Run: `python -m pytest -q`
Expected: all tests PASS — Foundation modules plus the three WP-E test files (trader 3, personas 3, arbiter 5).

- [ ] **Step 4: Commit (if any incidental fixes were needed)**

```bash
git add -A
git commit -m "test(wp-e): verify node import contract + full-suite green" --allow-empty
```

---

### Task 11: Opt-in live integration test (no network in CI)

**Files:**
- Test: `tests/agents/test_wp_e_live.py`

> Per COORDINATION §2, each WP provides ONE opt-in live test, marked `@pytest.mark.live`, skipped unless `RUN_LIVE=1`. It exercises the real Ollama Cloud deep model through the trader → arbiter path and confirms tool-calling (`method="function_calling"`) works for the deep model. If the deep model lacks tool calling, switch the four nodes to `method="json_schema"` and document it here.

- [ ] **Step 1: Write the live test**

```python
# tests/agents/test_wp_e_live.py
import os
import pytest

from src.agents.trader import trader
from src.agents.risk.arbiter import risk_arbiter

pytestmark = pytest.mark.skipif(os.getenv("RUN_LIVE") != "1", reason="set RUN_LIVE=1 to run")


@pytest.mark.live
@pytest.mark.asyncio
async def test_trader_then_arbiter_live():
    state = {
        "ticker": "AAPL",
        "resolved_ticker": "AAPL",
        "investor_mode": "Neutral",
        "analyst_reports": {
            "news": {"summary": "Steady demand; services growth.", "confidence": 0.6},
            "fundamentals": {"summary": "Healthy margins, premium valuation.", "confidence": 0.6},
            "technicals": {"summary": "Range-bound, RSI ~50.", "confidence": 0.5},
        },
        "research_debate": {
            "bull_thesis": "Services + buybacks.",
            "bear_thesis": "Valuation rich, hardware mature.",
            "facilitator_verdict": "Lean neutral-to-bullish.",
        },
    }
    tout = await trader(state)
    assert tout["trade_proposal"]["action"] in {"BUY", "SELL", "HOLD"}

    state.update(tout)
    state["risk_debate"] = {"conservative": "Trim into strength.", "aggressive": "Add on dips."}
    aout = await risk_arbiter(state)
    assert aout["final_decision"]["action"] in {"BUY", "SELL", "HOLD"}
    assert 0 <= aout["final_decision"]["score"] <= 100
```

- [ ] **Step 2: Confirm it is skipped by default**

Run: `python -m pytest tests/agents/test_wp_e_live.py -v`
Expected: 1 skipped (reason: set RUN_LIVE=1 to run).

- [ ] **Step 3: (Optional, manual) run live**

Run: `RUN_LIVE=1 python -m pytest tests/agents/test_wp_e_live.py -v`
Expected: PASS if Ollama Cloud creds in `.env` and the deep model supports tool calling. If it errors on tool calling, edit all four nodes to `method="json_schema"` and add a note to this task. Do NOT run this in CI.

- [ ] **Step 4: Commit**

```bash
git add tests/agents/test_wp_e_live.py
git commit -m "test(wp-e): add opt-in live trader+arbiter integration test"
```

---

## Dependencies

**Foundation (`2026-05-29-foundation-and-state-contract.md`) — MUST be merged first.** This WP imports the frozen `get_llm`, `CostTracker`, `get_settings`, `AgentState`, `merge_named_reports`, and schemas `TradeProposal`/`FinalDecision`/`DebateTurn`. It does NOT modify any frozen file. The `risk_debate` key already carries the `merge_named_reports` reducer (added in Foundation Task 10 Step 4), so the parallel conservative/aggressive writes merge without conflict.

**WP-D (`run_debate`) — parallel-dev fallback (option (b) per COORDINATION §4).** WP-E does NOT block on WP-D. `arbiter.py` imports `run_debate` from `src.agents.debate` if present, else from the local `src/agents/risk/_debate_stub.py` (identical signature). **Integration step on WP-D merge:** delete `_debate_stub.py` and the `except ImportError` fallback branch in `arbiter.py`, leaving only `from src.agents.debate import run_debate`. The arbiter tests monkeypatch `arb_mod.run_debate` directly, so they are agnostic to which import won.

**WP-C (`store_verdict`) — parallel-dev fallback.** `arbiter.py` imports `store_verdict` from `src.memory.cache` guarded by `try/except ImportError`, defaulting to `None`. The arbiter calls it only when not `None`, wrapped in `try/except` so a cache failure never aborts the run (`test_arbiter_survives_missing_store_verdict`). No integration edit needed — the guard is permanent and harmless once WP-C lands.

**Graph wiring is owned by WP-D, not this WP.** WP-D's `build_graph` imports these four node functions at the contracted paths (`src.agents.trader.trader`, `src.agents.risk.{conservative,aggressive,arbiter}.{risk_conservative,risk_aggressive,risk_arbiter}`). Task 10 verifies the import contract so WP-D can wire them with no surprises.

## Definition of Done
- [ ] `python -m pytest tests/agents -q` is green (trader 3, personas 3, arbiter 5; live test skipped).
- [ ] `src/agents/trader.py`, `src/agents/risk/conservative.py`, `src/agents/risk/aggressive.py`, `src/agents/risk/arbiter.py` exist; all four node functions are `async` and importable at the WP-D-contracted paths.
- [ ] `trader` writes `trade_proposal` (a `TradeProposal.model_dump()`) + `run_metrics`; uses `get_llm("deep").with_structured_output(TradeProposal, method="function_calling")`.
- [ ] `risk_conservative` writes only `risk_debate={"conservative": <str>}`; `risk_aggressive` writes only `risk_debate={"aggressive": <str>}`; both via a local `RiskStance` model (frozen schemas untouched).
- [ ] `risk_arbiter` calls `run_debate` with `rounds=settings.risk_debate_rounds` and personas `[("conservative",..),("aggressive",..)]`, writes a valid `FinalDecision` + `risk_debate` (`rounds`/`arbiter_decision`/`adjustments`), and calls `store_verdict(ticker, decision)` when the cache is available.
- [ ] No frozen file (`src/state.py`, `src/graph.py`, `src/llm/schemas.py`) was edited. No new runtime dependency added.
- [ ] Parallel-dev fallbacks documented: `_debate_stub.py` + the `except ImportError` branch in `arbiter.py` are flagged for deletion on WP-D merge; the `store_verdict` guard is permanent.
- [ ] Opt-in `@pytest.mark.live` test exists and is skipped unless `RUN_LIVE=1`; confirms `method="function_calling"` for the deep model (with documented `json_schema` fallback).

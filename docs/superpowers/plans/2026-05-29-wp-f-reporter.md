# WP-F: Reporter Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the stub `reporter` node with a real async node that assembles a clean markdown investment research report **directly from the typed `AgentState`** (NOT from a vector store — that defect is removed), surfaces the `final_decision` verdict prominently, produces a structured `financial_data` dict for the UI (radar chart + metric cards), and appends a transparent cost/observability footer aggregated from `run_metrics`.

**Architecture:** The reporter is the terminal node before `END`. It reads the frozen, accumulated state (`analyst_reports`, `research_debate`, `trade_proposal`, `risk_debate`, `final_decision`, `run_metrics`) and makes **one** `get_llm("quick").with_structured_output(ReportPayload)` async call that returns BOTH the narrative markdown sections AND the `financial_data` radar inputs in a single nested-Pydantic structured response. The node then deterministically (no LLM) renders a title header carrying the verdict, stitches the LLM's sections, and appends a metrics footer computed by pure-Python aggregation of `state["run_metrics"]`. It writes `final_report: str` and a NEW state key `financial_data: dict`. Streaming is owned by WP-G (the node is `async`; WP-G calls `graph.astream`).

**Tech Stack:** Python 3.13, `langgraph==1.0.4`, `langchain-core==1.2.5`, `langchain-openai==1.1.6`, `pydantic==2.12.5`, `pytest==8.4.2`, `pytest-asyncio>=0.24`. No new runtime dependencies.

---

## Context for the implementer

This WP codes against the **frozen contract** in `docs/superpowers/plans/COORDINATION.md` §1 and the Foundation plan (`2026-05-29-foundation-and-state-contract.md`). Read COORDINATION §2 (async node, structured output, metrics conventions) before starting.

The reporter **consumes** these typed state fields (all already frozen, all dicts/lists):
- `final_decision: dict` — `{action, conviction, score, rationale}` (the headline verdict; surfaced prominently).
- `trade_proposal: dict` — `{action, conviction, score, rationale}` (pre-risk-adjustment proposal; shown for transparency vs. final).
- `analyst_reports: dict` — `{ "news": {...}, "fundamentals": {...}, "technicals": {...} }`; each value matches `AnalystReport` shape `{summary, key_points, data, confidence, citations}`.
- `research_debate: dict` — `{bull_thesis, bear_thesis, facilitator_verdict, rounds}`.
- `risk_debate: dict` — `{conservative, aggressive, arbiter_decision, adjustments, rounds}`.
- `run_metrics: list[dict]` — per-node metric records `{node, model, prompt_tokens, completion_tokens, latency_s, cost_usd}` accumulated by the `operator.add` reducer.
- `ticker`, `resolved_ticker`, `investor_mode` — header context.

The reporter **writes** `final_report: str` and a NEW key `financial_data: dict`.

### Why one LLM call (not two)

A single `get_llm("quick").with_structured_output(ReportPayload, method="function_calling")` call returns a **nested** Pydantic model whose top level holds the narrative `sections` AND the `financial_data` (a nested `FinancialData` model). This is the minimal-cost, minimal-latency choice (one round-trip on the `quick` tier) and is verified to work: `model_dump()` recursively converts the nested model to plain dicts (verified via Context7, Pydantic v2 docs — "Pydantic models ... will be (recursively) converted to dictionaries"). Splitting into two calls would double latency/cost with no quality benefit, since the radar inputs are derived from the same analyst data the narrative summarizes. The verdict header and the metrics footer are rendered in pure Python (deterministic, never hallucinated), so the LLM is responsible only for prose + the radar numbers.

### API decisions (verified via Context7)

- `ChatOpenAI.with_structured_output(PydanticModel, method="function_calling")` returns a Runnable whose `.ainvoke(messages, config={"callbacks": [tracker]})` resolves to an **instance of the Pydantic model** (not a dict, not an AIMessage) — verified against LangChain OSS Python docs (`with_structured_output` + ChatOpenAI). Async `.ainvoke` is the standard Runnable async sibling of `.invoke` and returns the same parsed model.
- Per COORDINATION §2, default `method="function_calling"`; if the `quick` model (`gpt-oss:20b`) lacks Ollama Cloud tool-calling, fall back to `method="json_schema"`. A `@pytest.mark.live` probe (Task 7) confirms which to use; unit tests mock `get_llm` and are method-agnostic.
- Pydantic v2 nested `model_dump()` recurses into nested models and `list[Model]`, producing JSON-native dicts/lists — verified via Context7 (Pydantic serialization docs). So `payload.financial_data.model_dump()` yields a plain `dict` safe to store in state and JSON-serialize for the UI.

---

## File Structure

| File | Responsibility |
|---|---|
| `src/agents/__init__.py` | Package marker (create if absent) |
| `src/agents/reporter.py` | `ReportPayload`/`ReportSection`/`FinancialData` local Pydantic models, `aggregate_metrics`, `render_metrics_footer`, `render_verdict_header`, `build_report_messages`, async `reporter` node |
| `src/state.py` | **Edit:** add ONE key `financial_data: dict` (declared contract extension) |
| `docs/superpowers/plans/COORDINATION.md` | **Edit:** note the `financial_data` state-key extension under §1 frozen interfaces |
| `src/graph.py` | **Edit:** import the real `reporter` from `src.agents.reporter` (replace local stub) |
| `tests/test_reporter.py` | Unit tests: mocked `get_llm`, populated synthetic state, footer/header/financial_data assertions, no network |
| `tests/test_reporter_live.py` | One opt-in `@pytest.mark.live` test (skipped unless `RUN_LIVE=1`) |

---

### Task 1: Declare the `financial_data` state-key extension (coordination event)

This is an **allowed, declared** contract extension: it adds exactly ONE new key to the frozen `AgentState`. It is purely additive (no existing key changes, no reducer added — `reporter` is the sole writer and it is terminal), so it does not affect any other WP's reads/writes. We record it in COORDINATION.md and `src/state.py` before writing reporter code.

**Files:**
- Edit: `src/state.py`
- Edit: `docs/superpowers/plans/COORDINATION.md`

- [ ] **Step 1: Add the new key to `src/state.py`**

In the `AgentState` TypedDict, in the `# --- debate + decision (sequential single-writer fields) ---` block, add `financial_data` immediately after `final_report`. Exact one-line edit (add this line):

```python
    financial_data: dict
```

So the block reads:

```python
    # --- debate + decision (sequential single-writer fields) ---
    research_debate: Annotated[dict, merge_named_reports]
    trade_proposal: dict
    risk_debate: Annotated[dict, merge_named_reports]
    final_decision: dict
    final_report: str
    financial_data: dict
```

(No reducer: `reporter` is the single, terminal writer of `financial_data`.)

- [ ] **Step 2: Record the extension in COORDINATION.md** (§1, in the `# src/state.py` block)

Add `financial_data` to the listed `AgentState` keys and a one-line note. Edit the `AgentState` key list so the `final_decision, final_report, ...` line reads:

```
  trade_proposal, final_decision, final_report,
  financial_data,                # WP-F contract extension (terminal single-writer; radar/metric-card inputs for UI)
  run_metrics (reducer: operator.add — list of per-node metric dicts),
```

- [ ] **Step 3: Confirm the frozen state-contract test still passes**

Run: `python -m pytest tests/test_state.py tests/test_graph_skeleton.py -q`
Expected: PASS (additive key does not break existing reducer/keys tests; the stub graph still runs).

- [ ] **Step 4: Commit**

```bash
git add src/state.py docs/superpowers/plans/COORDINATION.md
git commit -m "feat(state): add financial_data key for reporter (declared WP-F extension)"
```

---

### Task 2: Reporter output schema — local Pydantic models (test-first)

The narrative + radar inputs are produced by ONE structured LLM call. We define the response shape as nested local Pydantic models in the reporter module. These are LOCAL to WP-F (NOT added to `src/llm/schemas.py`, which is frozen).

**Files:**
- Create: `src/agents/__init__.py` (if absent)
- Create: `src/agents/reporter.py` (models only in this task)
- Test: `tests/test_reporter.py` (schema portion)

- [ ] **Step 1: Create the package marker (if missing)**

```bash
test -f src/agents/__init__.py || : > src/agents/__init__.py
```

- [ ] **Step 2: Write the failing test for the schema**

```python
# tests/test_reporter.py
import pytest
from pydantic import ValidationError

from src.agents.reporter import ReportPayload, ReportSection, FinancialData


def test_financial_data_clamps_and_defaults():
    fd = FinancialData(
        valuation=120.0, growth=-5.0, profitability=50.0,
        momentum=50.0, sentiment=50.0, risk=50.0,
    )
    # scores are clamped to 0..100
    assert fd.valuation == 100.0
    assert fd.growth == 0.0


def test_financial_data_model_dump_is_plain_dict():
    fd = FinancialData(
        valuation=70.0, growth=60.0, profitability=80.0,
        momentum=55.0, sentiment=65.0, risk=40.0,
    )
    dumped = fd.model_dump()
    assert isinstance(dumped, dict)
    assert set(dumped) == {
        "valuation", "growth", "profitability", "momentum", "sentiment", "risk", "metric_cards",
    }
    assert dumped["metric_cards"] == []


def test_report_payload_nested_model_dump_recurses():
    payload = ReportPayload(
        sections=[ReportSection(heading="Thesis", body="strong")],
        financial_data=FinancialData(
            valuation=70.0, growth=60.0, profitability=80.0,
            momentum=55.0, sentiment=65.0, risk=40.0,
        ),
    )
    dumped = payload.model_dump()
    # nested models recursively become plain dicts (Pydantic v2 behavior)
    assert isinstance(dumped["sections"][0], dict)
    assert isinstance(dumped["financial_data"], dict)
    assert dumped["sections"][0]["heading"] == "Thesis"


def test_report_section_requires_heading_and_body():
    with pytest.raises(ValidationError):
        ReportSection(heading="only heading")  # body missing
```

- [ ] **Step 3: Run test to verify it fails**

Run: `python -m pytest tests/test_reporter.py -q`
Expected: FAIL with `ModuleNotFoundError: No module named 'src.agents.reporter'`.

- [ ] **Step 4: Write the models** (start `src/agents/reporter.py`)

```python
# src/agents/reporter.py
"""WP-F Reporter node. Assembles a markdown investment report directly from the
typed AgentState (no vector store) and a structured financial_data dict for the UI.

One LLM call (quick tier) produces the narrative sections AND the radar inputs as a
nested Pydantic model; the verdict header and the cost/observability footer are
rendered deterministically in pure Python."""
from __future__ import annotations

from pydantic import BaseModel, Field, field_validator


class MetricCard(BaseModel):
    """A single labeled metric for the UI metric-card row."""
    label: str
    value: str


class FinancialData(BaseModel):
    """Radar-chart axes (0..100) + metric cards consumed by the UI (WP-G).

    Each axis is a normalized 0..100 health score derived from analyst data:
    higher is more favorable (for `risk`, higher = better risk profile)."""
    valuation: float = Field(description="Valuation attractiveness 0..100 (higher = cheaper/fairer)")
    growth: float = Field(description="Growth strength 0..100")
    profitability: float = Field(description="Profitability/margins 0..100")
    momentum: float = Field(description="Technical momentum 0..100")
    sentiment: float = Field(description="News/market sentiment 0..100")
    risk: float = Field(description="Risk profile 0..100 (higher = safer)")
    metric_cards: list[MetricCard] = Field(default_factory=list)

    @field_validator("valuation", "growth", "profitability", "momentum", "sentiment", "risk")
    @classmethod
    def _clamp_0_100(cls, v: float) -> float:
        return max(0.0, min(100.0, float(v)))


class ReportSection(BaseModel):
    """One markdown section of the narrative report."""
    heading: str
    body: str


class ReportPayload(BaseModel):
    """The single structured LLM output: narrative sections + radar/metric inputs."""
    sections: list[ReportSection] = Field(default_factory=list)
    financial_data: FinancialData
```

- [ ] **Step 5: Run test to verify it passes**

Run: `python -m pytest tests/test_reporter.py -q`
Expected: PASS (4 tests).

- [ ] **Step 6: Commit**

```bash
git add src/agents/__init__.py src/agents/reporter.py tests/test_reporter.py
git commit -m "feat(reporter): add nested ReportPayload/FinancialData output models"
```

---

### Task 3: Metrics aggregation + footer renderer (pure Python, test-first)

The transparency footer is computed deterministically from `state["run_metrics"]` — never from the LLM. This showcases the cost/observability story.

**Files:**
- Edit: `src/agents/reporter.py`
- Test: `tests/test_reporter.py`

- [ ] **Step 1: Append the failing tests**

```python
# tests/test_reporter.py  (append)
from src.agents.reporter import aggregate_metrics, render_metrics_footer


def _sample_metrics():
    return [
        {"node": "news_analyst", "model": "gpt-oss:20b", "prompt_tokens": 100,
         "completion_tokens": 40, "latency_s": 1.5, "cost_usd": 0.002},
        {"node": "bull", "model": "gpt-oss:120b", "prompt_tokens": 200,
         "completion_tokens": 80, "latency_s": 3.0, "cost_usd": 0.01},
        {"node": "reporter", "model": "gpt-oss:20b", "prompt_tokens": 50,
         "completion_tokens": 20, "latency_s": 0.5, "cost_usd": 0.001},
    ]


def test_aggregate_metrics_sums_fields():
    agg = aggregate_metrics(_sample_metrics())
    assert agg["prompt_tokens"] == 350
    assert agg["completion_tokens"] == 140
    assert agg["total_tokens"] == 490
    assert round(agg["latency_s"], 2) == 5.0
    assert round(agg["cost_usd"], 4) == 0.013
    assert agg["node_count"] == 3


def test_aggregate_metrics_handles_empty():
    agg = aggregate_metrics([])
    assert agg["total_tokens"] == 0
    assert agg["cost_usd"] == 0.0
    assert agg["node_count"] == 0


def test_aggregate_metrics_tolerates_missing_keys():
    agg = aggregate_metrics([{"node": "x"}])  # no token/cost keys
    assert agg["total_tokens"] == 0
    assert agg["latency_s"] == 0.0


def test_render_metrics_footer_includes_aggregates_and_mode():
    footer = render_metrics_footer(_sample_metrics(), debate_mode="on")
    assert "Run Transparency" in footer
    assert "$0.013" in footer            # cost_usd
    assert "490" in footer               # total tokens
    assert "5.0" in footer or "5.00" in footer  # latency
    assert "on" in footer                # debate_mode
    assert "3" in footer                 # node count


def test_render_metrics_footer_empty_metrics():
    footer = render_metrics_footer([], debate_mode="off")
    assert "Run Transparency" in footer
    assert "off" in footer
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_reporter.py -q`
Expected: FAIL with `ImportError: cannot import name 'aggregate_metrics'`.

- [ ] **Step 3: Implement aggregation + footer** (append to `src/agents/reporter.py`)

```python
# src/agents/reporter.py  (append)


def aggregate_metrics(run_metrics: list[dict] | None) -> dict:
    """Sum per-node metric records into run totals. Tolerant of missing keys."""
    records = run_metrics or []
    prompt = sum(int(r.get("prompt_tokens", 0) or 0) for r in records)
    completion = sum(int(r.get("completion_tokens", 0) or 0) for r in records)
    latency = sum(float(r.get("latency_s", 0.0) or 0.0) for r in records)
    cost = sum(float(r.get("cost_usd", 0.0) or 0.0) for r in records)
    return {
        "prompt_tokens": prompt,
        "completion_tokens": completion,
        "total_tokens": prompt + completion,
        "latency_s": round(latency, 4),
        "cost_usd": round(cost, 6),
        "node_count": len(records),
    }


def render_metrics_footer(run_metrics: list[dict] | None, debate_mode: str) -> str:
    """Render the transparent cost/observability footer from run_metrics."""
    agg = aggregate_metrics(run_metrics)
    return (
        "\n---\n\n"
        "### Run Transparency\n\n"
        "| Metric | Value |\n"
        "|---|---|\n"
        f"| Estimated cost | ${agg['cost_usd']:.3f} |\n"
        f"| Total latency | {agg['latency_s']:.1f}s |\n"
        f"| Tokens (prompt / completion / total) | "
        f"{agg['prompt_tokens']} / {agg['completion_tokens']} / {agg['total_tokens']} |\n"
        f"| Nodes executed | {agg['node_count']} |\n"
        f"| Debate mode | {debate_mode} |\n"
        "\n_Costs and latency are measured per-node via CostTracker callbacks "
        "and aggregated here for full transparency._\n"
    )
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_reporter.py -q`
Expected: PASS (all schema + metrics tests).

- [ ] **Step 5: Commit**

```bash
git add src/agents/reporter.py tests/test_reporter.py
git commit -m "feat(reporter): add deterministic metrics aggregation + footer"
```

---

### Task 4: Verdict header renderer (pure Python, test-first)

The verdict is surfaced prominently and deterministically (never hallucinated) from `final_decision`, with the pre-risk `trade_proposal` shown for transparency.

**Files:**
- Edit: `src/agents/reporter.py`
- Test: `tests/test_reporter.py`

- [ ] **Step 1: Append the failing tests**

```python
# tests/test_reporter.py  (append)
from src.agents.reporter import render_verdict_header


def test_render_verdict_header_surfaces_action_score_ticker():
    header = render_verdict_header(
        ticker="AAPL",
        resolved_ticker="AAPL",
        investor_mode="Neutral",
        final_decision={"action": "BUY", "conviction": 0.82, "score": 78,
                        "rationale": "Strong fundamentals and momentum."},
        trade_proposal={"action": "HOLD", "conviction": 0.6, "score": 62, "rationale": "x"},
    )
    assert "AAPL" in header
    assert "BUY" in header
    assert "78" in header           # final score
    assert "0.82" in header         # conviction
    assert "Strong fundamentals" in header
    assert "Neutral" in header
    # transparency: the pre-risk proposal differing from final is noted
    assert "HOLD" in header
    assert "62" in header


def test_render_verdict_header_handles_missing_decision():
    header = render_verdict_header(
        ticker="TSLA", resolved_ticker="TSLA", investor_mode="Bullish",
        final_decision={}, trade_proposal={},
    )
    assert "TSLA" in header
    assert "HOLD" in header  # safe default action
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_reporter.py -q`
Expected: FAIL with `ImportError: cannot import name 'render_verdict_header'`.

- [ ] **Step 3: Implement the header** (append to `src/agents/reporter.py`)

```python
# src/agents/reporter.py  (append)


def render_verdict_header(
    *,
    ticker: str,
    resolved_ticker: str,
    investor_mode: str,
    final_decision: dict,
    trade_proposal: dict,
) -> str:
    """Render the prominent verdict header deterministically from final_decision.

    The pre-risk trade_proposal is shown for transparency when it differs."""
    fd = final_decision or {}
    tp = trade_proposal or {}
    action = str(fd.get("action", "HOLD"))
    conviction = float(fd.get("conviction", 0.0) or 0.0)
    score = int(fd.get("score", 0) or 0)
    rationale = str(fd.get("rationale", "No rationale provided.")).strip()
    symbol = resolved_ticker or ticker

    lines = [
        f"# Investment Research Report — {symbol}",
        "",
        f"**Verdict: {action}**  ·  Score: **{score}/100**  ·  "
        f"Conviction: **{conviction:.2f}**  ·  Investor mode: {investor_mode or 'Neutral'}",
        "",
        f"> {rationale}",
        "",
    ]

    tp_action = tp.get("action")
    if tp_action is not None and (
        tp_action != action or int(tp.get("score", -1) or -1) != score
    ):
        tp_score = int(tp.get("score", 0) or 0)
        tp_conv = float(tp.get("conviction", 0.0) or 0.0)
        lines.append(
            f"_Pre-risk-adjustment proposal: {tp_action} "
            f"(score {tp_score}/100, conviction {tp_conv:.2f}) — "
            f"adjusted to {action} by the risk arbiter._"
        )
        lines.append("")

    return "\n".join(lines)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_reporter.py -q`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/agents/reporter.py tests/test_reporter.py
git commit -m "feat(reporter): add deterministic verdict header renderer"
```

---

### Task 5: Prompt + message builder for the structured LLM call (test-first)

The system prompt is module-local (COORDINATION §2) and references ONLY the typed state the reporter consumes. The message builder serializes the relevant state into a compact human message so the LLM writes the narrative sections and the radar numbers.

**Files:**
- Edit: `src/agents/reporter.py`
- Test: `tests/test_reporter.py`

- [ ] **Step 1: Append the failing tests**

```python
# tests/test_reporter.py  (append)
from src.agents.reporter import REPORTER_SYSTEM_PROMPT, build_report_messages


def _full_state():
    return {
        "ticker": "AAPL", "resolved_ticker": "AAPL", "investor_mode": "Neutral",
        "analyst_reports": {
            "news": {"summary": "Strong product cycle", "key_points": ["iPhone demand up"],
                     "data": {}, "confidence": 0.7, "citations": ["http://x"]},
            "fundamentals": {"summary": "Healthy margins", "key_points": ["FCF growth"],
                             "data": {"pe": 28}, "confidence": 0.6, "citations": []},
            "technicals": {"summary": "Uptrend", "key_points": ["RSI 60"],
                           "data": {"rsi": 60}, "confidence": 0.5, "citations": []},
        },
        "research_debate": {"bull_thesis": "Growth runway", "bear_thesis": "Valuation rich",
                            "facilitator_verdict": "Lean bull", "rounds": []},
        "trade_proposal": {"action": "BUY", "conviction": 0.7, "score": 70, "rationale": "momentum"},
        "risk_debate": {"conservative": "size down", "aggressive": "full size",
                        "arbiter_decision": "moderate size", "adjustments": ["trim 20%"], "rounds": []},
        "final_decision": {"action": "BUY", "conviction": 0.75, "score": 72,
                           "rationale": "Net favorable"},
        "run_metrics": [
            {"node": "reporter", "model": "gpt-oss:20b", "prompt_tokens": 10,
             "completion_tokens": 5, "latency_s": 0.2, "cost_usd": 0.0001},
        ],
    }


def test_build_report_messages_includes_state_facts():
    msgs = build_report_messages(_full_state())
    assert len(msgs) == 2
    assert msgs[0]["role"] == "system"
    assert msgs[0]["content"] == REPORTER_SYSTEM_PROMPT
    human = msgs[1]["content"]
    assert msgs[1]["role"] == "user"
    # the human message carries the consumed state fields
    for needle in ["AAPL", "Strong product cycle", "Growth runway",
                   "Valuation rich", "Lean bull", "moderate size", "Net favorable"]:
        assert needle in human


def test_system_prompt_mentions_radar_and_sections():
    assert "financial_data" in REPORTER_SYSTEM_PROMPT
    assert "section" in REPORTER_SYSTEM_PROMPT.lower()
    # prompt must NOT instruct the model to invent the verdict or metrics footer
    assert "0..100" in REPORTER_SYSTEM_PROMPT or "0-100" in REPORTER_SYSTEM_PROMPT
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_reporter.py -q`
Expected: FAIL with `ImportError: cannot import name 'REPORTER_SYSTEM_PROMPT'`.

- [ ] **Step 3: Implement the prompt + builder** (append to `src/agents/reporter.py`)

```python
# src/agents/reporter.py  (append)
import json

REPORTER_SYSTEM_PROMPT = (
    "You are the Reporter agent in a multi-agent equity research system. "
    "Write a concise, professional investment research narrative for the given stock, "
    "using ONLY the analyst, debate, and decision data provided. Do not invent facts, "
    "prices, or citations. Do not restate a verdict line or any cost/latency numbers — "
    "those are rendered separately by the system.\n\n"
    "Return structured output with two parts:\n"
    "1. `sections`: an ordered list of markdown report sections. Recommended sections: "
    "Executive Summary, Bull vs. Bear, Fundamentals, Technicals, News & Sentiment, "
    "Risk Assessment, Bottom Line. Each section has a short `heading` (no leading '#') "
    "and a `body` of 1-3 tight paragraphs or bullet lists in GitHub-flavored markdown.\n"
    "2. `financial_data`: six normalized 0..100 health scores for a radar chart "
    "(valuation, growth, profitability, momentum, sentiment, risk; for `risk`, higher "
    "means a SAFER profile), each grounded in the analyst data, plus a `metric_cards` "
    "list of {label, value} pairs surfacing the most decision-relevant numbers "
    "(e.g. P/E, RSI, conviction). Use neutral 50 when a dimension is unsupported by data."
)


def _compact(value, limit: int = 1200) -> str:
    """JSON-serialize a state value compactly for the prompt (truncated, JSON-safe)."""
    try:
        text = json.dumps(value, default=str, ensure_ascii=False)
    except (TypeError, ValueError):
        text = str(value)
    return text if len(text) <= limit else text[:limit] + "…"


def build_report_messages(state: dict) -> list[dict]:
    """Build [system, user] messages serializing the consumed state fields."""
    symbol = state.get("resolved_ticker") or state.get("ticker", "")
    human = (
        f"Ticker: {symbol}\n"
        f"Investor mode: {state.get('investor_mode', 'Neutral')}\n\n"
        f"ANALYST REPORTS:\n{_compact(state.get('analyst_reports', {}), 2000)}\n\n"
        f"RESEARCH DEBATE (bull/bear/facilitator):\n"
        f"{_compact(state.get('research_debate', {}), 1500)}\n\n"
        f"TRADE PROPOSAL (pre-risk):\n{_compact(state.get('trade_proposal', {}))}\n\n"
        f"RISK DEBATE:\n{_compact(state.get('risk_debate', {}), 1500)}\n\n"
        f"FINAL DECISION:\n{_compact(state.get('final_decision', {}))}\n\n"
        "Write the report sections and the financial_data radar inputs now."
    )
    return [
        {"role": "system", "content": REPORTER_SYSTEM_PROMPT},
        {"role": "user", "content": human},
    ]
```

> Note: move the `import json` to the top of the module with the other imports when convenient; placing it here keeps the task self-contained. (Python allows the in-body import; a later cleanup task may hoist it.)

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_reporter.py -q`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/agents/reporter.py tests/test_reporter.py
git commit -m "feat(reporter): add system prompt + state->messages builder"
```

---

### Task 6: The async `reporter` node (test-first, mocked LLM, no network)

Assembles header + LLM sections + footer; writes `final_report`, `financial_data`, and `run_metrics`. Mocks `get_llm` so `.with_structured_output(...).ainvoke(...)` returns a prepared `ReportPayload` (COORDINATION §2 testing rule).

**Files:**
- Edit: `src/agents/reporter.py`
- Test: `tests/test_reporter.py`

- [ ] **Step 1: Append the failing tests**

```python
# tests/test_reporter.py  (append)
import pytest

import src.agents.reporter as reporter_mod
from src.agents.reporter import reporter, ReportPayload, ReportSection, FinancialData, MetricCard


class _FakeStructured:
    def __init__(self, payload):
        self._payload = payload

    async def ainvoke(self, messages, config=None):
        # mimic with_structured_output: returns the Pydantic model instance
        self.captured_config = config
        return self._payload


class _FakeLLM:
    def __init__(self, payload):
        self._payload = payload
        self.method = None

    def with_structured_output(self, schema, method=None):
        self.method = method
        assert schema is ReportPayload
        return _FakeStructured(self._payload)


@pytest.fixture
def fake_payload():
    return ReportPayload(
        sections=[
            ReportSection(heading="Executive Summary", body="AAPL looks favorable."),
            ReportSection(heading="Risk Assessment", body="Valuation is a watch item."),
        ],
        financial_data=FinancialData(
            valuation=65.0, growth=72.0, profitability=80.0,
            momentum=58.0, sentiment=70.0, risk=55.0,
            metric_cards=[MetricCard(label="P/E", value="28"),
                          MetricCard(label="RSI", value="60")],
        ),
    )


@pytest.mark.asyncio
async def test_reporter_returns_report_and_financial_data(monkeypatch, fake_payload):
    monkeypatch.setattr(reporter_mod, "get_llm", lambda tier: _FakeLLM(fake_payload))
    state = _full_state()
    out = await reporter(state)

    # writes the three expected keys
    assert set(out) >= {"final_report", "financial_data", "run_metrics"}

    report = out["final_report"]
    assert isinstance(report, str) and report.strip()
    # ticker + action + score surfaced
    assert "AAPL" in report
    assert "BUY" in report
    assert "72" in report
    # LLM section headings rendered as markdown
    assert "## Executive Summary" in report
    assert "AAPL looks favorable." in report
    assert "## Risk Assessment" in report
    # footer aggregated from run_metrics + debate_mode present
    assert "Run Transparency" in report
    assert "Debate mode" in report

    fd = out["financial_data"]
    assert isinstance(fd, dict)
    assert set(fd) == {"valuation", "growth", "profitability", "momentum",
                       "sentiment", "risk", "metric_cards"}
    assert fd["valuation"] == 65.0
    assert fd["metric_cards"][0] == {"label": "P/E", "value": "28"}


@pytest.mark.asyncio
async def test_reporter_appends_its_own_metric(monkeypatch, fake_payload):
    monkeypatch.setattr(reporter_mod, "get_llm", lambda tier: _FakeLLM(fake_payload))
    out = await reporter(_full_state())
    metrics = out["run_metrics"]
    assert isinstance(metrics, list)
    assert any(m["node"] == "reporter" for m in metrics)


@pytest.mark.asyncio
async def test_reporter_uses_quick_tier_and_passes_callback(monkeypatch, fake_payload):
    seen = {}

    def _capture(tier):
        seen["tier"] = tier
        return _FakeLLM(fake_payload)

    monkeypatch.setattr(reporter_mod, "get_llm", _capture)
    out = await reporter(_full_state())
    assert seen["tier"] == "quick"
    # reporter metric record exists (CostTracker callback path exercised)
    assert any(m["node"] == "reporter" for m in out["run_metrics"])


@pytest.mark.asyncio
async def test_reporter_reads_debate_mode_from_settings(monkeypatch, fake_payload):
    monkeypatch.setattr(reporter_mod, "get_llm", lambda tier: _FakeLLM(fake_payload))

    class _S:
        debate_mode = "off"

    monkeypatch.setattr(reporter_mod, "get_settings", lambda: _S())
    out = await reporter(_full_state())
    # footer reflects the configured debate mode
    assert "| Debate mode | off |" in out["final_report"]
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_reporter.py -q`
Expected: FAIL with `ImportError: cannot import name 'reporter'`.

- [ ] **Step 3: Implement the node** (append to `src/agents/reporter.py`)

```python
# src/agents/reporter.py  (append)
from src.config.settings import get_settings
from src.llm.cost import CostTracker
from src.llm.factory import get_llm

# Default structured-output method per COORDINATION §2. If the quick model lacks
# Ollama Cloud tool calling (see Task 7 live probe), change to "json_schema".
_STRUCTURED_METHOD = "function_calling"


def _render_sections(sections: list[ReportSection]) -> str:
    parts: list[str] = []
    for sec in sections:
        parts.append(f"## {sec.heading}\n\n{sec.body}")
    return "\n\n".join(parts)


async def reporter(state: dict) -> dict:
    """Terminal node: assemble the markdown report + financial_data from typed state.

    Reads analyst_reports, research_debate, trade_proposal, risk_debate,
    final_decision, run_metrics. Writes final_report, financial_data, run_metrics."""
    tracker = CostTracker("reporter")
    llm = get_llm("quick").with_structured_output(
        ReportPayload, method=_STRUCTURED_METHOD
    )
    messages = build_report_messages(state)
    payload: ReportPayload = await llm.ainvoke(messages, config={"callbacks": [tracker]})

    header = render_verdict_header(
        ticker=state.get("ticker", ""),
        resolved_ticker=state.get("resolved_ticker", ""),
        investor_mode=state.get("investor_mode", "Neutral"),
        final_decision=state.get("final_decision", {}),
        trade_proposal=state.get("trade_proposal", {}),
    )
    body = _render_sections(payload.sections)

    # Footer aggregates ALL upstream metrics PLUS this node's own call.
    debate_mode = getattr(get_settings(), "debate_mode", "on")
    this_node_metrics = tracker.totals()["per_node"]
    all_metrics = list(state.get("run_metrics", [])) + this_node_metrics
    footer = render_metrics_footer(all_metrics, debate_mode=debate_mode)

    final_report = f"{header}\n{body}\n{footer}"

    return {
        "final_report": final_report,
        "financial_data": payload.financial_data.model_dump(),
        "run_metrics": this_node_metrics,
    }
```

> **Why the footer aggregates `state["run_metrics"] + this_node_metrics` but the return only emits `this_node_metrics`:** the `operator.add` reducer will append the returned `this_node_metrics` to the accumulated list, so emitting only this node's records avoids double-counting in state. The footer, however, needs the COMPLETE run total (all prior nodes + reporter), so it combines them locally for display.

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_reporter.py -q`
Expected: PASS (all reporter tests).

- [ ] **Step 5: Run the full suite**

Run: `python -m pytest -q`
Expected: all PASS (no regressions in foundation tests).

- [ ] **Step 6: Commit**

```bash
git add src/agents/reporter.py tests/test_reporter.py
git commit -m "feat(reporter): implement async reporter node (state->markdown + financial_data)"
```

---

### Task 7: Wire the real reporter into the graph + opt-in live probe

**Files:**
- Edit: `src/graph.py`
- Test: `tests/test_reporter_live.py`
- Edit: `tests/test_graph_skeleton.py` (adjust if it asserted the stub report text)

- [ ] **Step 1: Replace the stub `reporter` in `src/graph.py`**

Remove the local `def reporter(state): ...` stub and import the real node. At the top of `src/graph.py`, add:

```python
from src.agents.reporter import reporter
```

Delete the stub function body:

```python
def reporter(state: AgentState) -> dict:
    return {"final_report": "# Stub Report\n\nReplace in WP-F.", "run_metrics": _metric("reporter")}
```

The existing `g.add_node("reporter", reporter)` line now binds the imported async node. (LangGraph supports async nodes natively; the graph must be driven with `.ainvoke`/`.astream` in production — WP-G owns that. Synchronous `.invoke` in the old skeleton test still works for sync stub nodes but will fail for the now-async reporter, so update the skeleton test below.)

- [ ] **Step 2: Update `tests/test_graph_skeleton.py`** so it no longer asserts stub report text and drives the graph asynchronously

Replace the body of `test_graph_runs_end_to_end` and any test asserting the stub report. The reporter now needs an LLM, so the skeleton test must either (a) mock `get_llm` for the reporter, or (b) be marked to only assert structure. Use approach (a):

```python
# tests/test_graph_skeleton.py  (replace the end-to-end test)
import pytest
import src.agents.reporter as reporter_mod
from src.agents.reporter import ReportPayload, ReportSection, FinancialData


@pytest.mark.asyncio
async def test_graph_runs_end_to_end(monkeypatch):
    payload = ReportPayload(
        sections=[ReportSection(heading="Summary", body="ok")],
        financial_data=FinancialData(valuation=50, growth=50, profitability=50,
                                     momentum=50, sentiment=50, risk=50),
    )

    class _FakeStructured:
        async def ainvoke(self, messages, config=None):
            return payload

    class _FakeLLM:
        def with_structured_output(self, schema, method=None):
            return _FakeStructured()

    monkeypatch.setattr(reporter_mod, "get_llm", lambda tier: _FakeLLM())

    from src.graph import build_graph
    app = build_graph()
    result = await app.ainvoke({"ticker": "AAPL", "investor_mode": "Neutral"})
    assert result["resolved_ticker"]
    assert "final_report" in result
    assert "financial_data" in result
    assert result["final_decision"]["action"] in {"BUY", "SELL", "HOLD"}
```

> Other skeleton tests that asserted `len(run_metrics) == 12` still hold: the reporter emits exactly one metric record via its `CostTracker` (which has one recorded call after the mocked `ainvoke`... note the mock does NOT trigger the callback, so the reporter's `tracker.totals()["per_node"]` is empty). To keep the metric-count test stable, the reporter ALSO needs at least a node marker. **Decision:** keep the reporter's return as `this_node_metrics` (may be empty under a mock that bypasses callbacks). Update the count test to `>= 11` and assert a `reporter`-authored report instead, OR have WP-I's integration suite own the exact count. Document this in the test: the precise per-node metric count is validated by WP-I against a fully-mocked-callback run, not here.

Concretely, change the metrics-count assertion test:

```python
@pytest.mark.asyncio
async def test_graph_accumulates_run_metrics(monkeypatch):
    payload = ReportPayload(
        sections=[ReportSection(heading="S", body="b")],
        financial_data=FinancialData(valuation=50, growth=50, profitability=50,
                                     momentum=50, sentiment=50, risk=50),
    )

    class _FakeStructured:
        async def ainvoke(self, messages, config=None):
            return payload

    class _FakeLLM:
        def with_structured_output(self, schema, method=None):
            return _FakeStructured()

    monkeypatch.setattr(reporter_mod, "get_llm", lambda tier: _FakeLLM())
    from src.graph import build_graph
    result = await build_graph().ainvoke({"ticker": "AAPL", "investor_mode": "Neutral"})
    # 11 stub nodes each emit one metric; reporter emits 0 under the mocked callback.
    assert len(result["run_metrics"]) >= 11
```

- [ ] **Step 3: Write the opt-in live probe** (verifies real Ollama Cloud structured output + which `method` works)

```python
# tests/test_reporter_live.py
import os
import pytest

pytestmark = pytest.mark.skipif(
    os.getenv("RUN_LIVE") != "1", reason="live test; set RUN_LIVE=1 to run"
)


@pytest.mark.live
@pytest.mark.asyncio
async def test_reporter_live_structured_output():
    """Confirms the quick model returns a valid ReportPayload via real Ollama Cloud.
    If this fails with a tool-calling error, set _STRUCTURED_METHOD='json_schema'
    in src/agents/reporter.py and re-run."""
    from src.agents.reporter import reporter
    state = {
        "ticker": "AAPL", "resolved_ticker": "AAPL", "investor_mode": "Neutral",
        "analyst_reports": {"fundamentals": {"summary": "Healthy margins",
                                             "key_points": ["FCF up"], "data": {"pe": 28},
                                             "confidence": 0.6, "citations": []}},
        "research_debate": {"facilitator_verdict": "Lean bull"},
        "trade_proposal": {"action": "BUY", "conviction": 0.7, "score": 70, "rationale": "x"},
        "risk_debate": {"arbiter_decision": "moderate"},
        "final_decision": {"action": "BUY", "conviction": 0.72, "score": 71, "rationale": "ok"},
        "run_metrics": [],
    }
    out = await reporter(state)
    assert "AAPL" in out["final_report"]
    assert set(out["financial_data"]) >= {"valuation", "growth", "risk"}
    # a real call should record nonzero tokens for the reporter node
    assert any(m["node"] == "reporter" for m in out["run_metrics"])
```

- [ ] **Step 4: Run the unit suite (live skipped)**

Run: `python -m pytest -q`
Expected: all PASS; `tests/test_reporter_live.py` SKIPPED.

- [ ] **Step 5 (optional, requires keys): Run the live probe to lock the method**

Run: `RUN_LIVE=1 python -m pytest tests/test_reporter_live.py -q`
Expected: PASS with `function_calling`. If it errors on tool calling, change `_STRUCTURED_METHOD = "json_schema"` in `src/agents/reporter.py`, re-run, and note the change in the plan's DoD.

- [ ] **Step 6: Commit**

```bash
git add src/graph.py tests/test_reporter_live.py tests/test_graph_skeleton.py
git commit -m "feat(graph): wire real reporter node + add live structured-output probe"
```

---

## Streaming note (owned by WP-G, not implemented here)

The reporter does NOT implement streaming itself. It is a standard `async def reporter(state) -> dict` node returning its full delta. Streaming is WP-G's concern: WP-G drives the compiled graph with
`graph.astream(input, stream_mode=["updates", "messages"])` over SSE. With `stream_mode="updates"`, WP-G receives the reporter's `{"final_report": ..., "financial_data": ...}` delta as a single node-completion event; with `stream_mode="messages"`, the token deltas from the reporter's `quick`-tier LLM call stream live to the client as the markdown is generated. Because the node is async and returns plain dict deltas, it integrates with LangGraph streaming with zero reporter-side changes. WP-G verifies LangGraph 1.0.4 `stream_mode` list behavior via Context7 (per COORDINATION §4).

---

## Dependencies

- **Foundation (`2026-05-29-foundation-and-state-contract.md`) MUST be merged first.** WP-F imports `get_llm` (`src/llm/factory.py`), `CostTracker` (`src/llm/cost.py`), `get_settings` (`src/config/settings.py`), `AgentState` (`src/state.py`), and edits the stub `reporter` in `src/graph.py`. All are frozen Foundation deliverables.
- **No dependency on WP-B/C/D/E for code to run.** The reporter reads `analyst_reports`, `research_debate`, `trade_proposal`, `risk_debate`, `final_decision` as plain dicts; the Foundation stub graph already populates contract-shaped values for all of them, so WP-F is fully testable and runnable against stubs. When the real upstream nodes land, the reporter automatically renders richer data with no changes.
- **Declared contract extension (coordination event — Task 1):** WP-F adds exactly ONE new key to the frozen `AgentState`: `financial_data: dict`. Exact edit to `src/state.py`: add the line `financial_data: dict` after `final_report: str`. This is purely additive, terminal, single-writer (no reducer), and recorded in COORDINATION.md §1. No other WP reads or writes `financial_data` except WP-G (UI), which consumes it; WP-G already codes against `AgentState`, so it picks the key up automatically.
- **Develop-in-parallel guidance:** if Foundation is not yet merged, stub `get_llm`/`CostTracker`/`get_settings`/`AgentState` behind the identical signatures shown in COORDINATION §1 and swap to real imports on merge. No signature divergence is permitted.
- **No new runtime dependencies.** Everything used (`langgraph`, `langchain-core`, `langchain-openai`, `pydantic`) is pinned by Foundation's `pyproject.toml`.

---

## Definition of Done
- [ ] `src/agents/reporter.py` exists with local `MetricCard`, `FinancialData`, `ReportSection`, `ReportPayload` Pydantic models (NOT added to the frozen `src/llm/schemas.py`).
- [ ] `reporter` is an `async def` node that makes exactly ONE `get_llm("quick").with_structured_output(ReportPayload, method=...)` call via `await llm.ainvoke(...)`, passing a `CostTracker("reporter")` callback.
- [ ] The node returns `final_report` (markdown string containing the ticker, the `final_decision` action, and score), `financial_data` (dict with keys `valuation, growth, profitability, momentum, sentiment, risk, metric_cards`), and `run_metrics` (this node's per-node records).
- [ ] The report footer (`### Run Transparency`) shows aggregated `cost_usd`, total `latency_s`, prompt/completion/total tokens, node count, and `debate_mode` — computed deterministically from `run_metrics`, not from the LLM.
- [ ] The verdict header surfaces the `final_decision` prominently and notes any divergence from the pre-risk `trade_proposal`, both rendered deterministically.
- [ ] `financial_data` is added as ONE new key in `src/state.py` (`financial_data: dict`) and recorded in `COORDINATION.md` §1 as a declared WP-F extension.
- [ ] The stub `reporter` in `src/graph.py` is replaced by `from src.agents.reporter import reporter`; the graph is driven async (`.ainvoke`/`.astream`).
- [ ] `python -m pytest tests/test_reporter.py -q` is green; `python -m pytest -q` is green (no regressions); `tests/test_reporter_live.py` is SKIPPED without `RUN_LIVE=1`.
- [ ] The structured-output `method` is confirmed against real Ollama Cloud via the live probe (default `function_calling`; documented `json_schema` fallback if tool calling is unsupported).
- [ ] No network calls in unit tests (`get_llm` mocked); no new runtime dependencies added.

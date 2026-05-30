# Work-Package Coordination Contract

Single source of truth for all 8 work-package (WP) implementation plans. Every WP codes against the **frozen contract** produced by `2026-05-29-foundation-and-state-contract.md`. Do not redefine anything here — import it.

> If a WP needs to change a frozen interface, that is a coordination event: stop, update this file, and notify all WPs. Plans must not silently diverge.

## 1. Frozen interfaces (from the Foundation plan)

```python
# src/config/settings.py
get_settings() -> Settings          # cached; fields: llm_provider, llm_base_url, ollama_api_key,
#   firecrawl_api_key, quick_model, deep_model, quick_temperature, deep_temperature,
#   research_debate_rounds, risk_debate_rounds, debate_mode ("on"|"off"),
#   chroma_dir, embedding_model, runs_dir, langsmith_enabled

# src/llm/factory.py
get_llm(tier: Literal["quick","deep"]) -> ChatOpenAI   # cached singleton, points at Ollama Cloud /v1

# src/llm/cost.py
CostTracker(node: str)              # LangChain BaseCallbackHandler; .totals() -> {prompt_tokens,
#   completion_tokens, latency_s, cost_usd, per_node:[{node,model,prompt_tokens,completion_tokens,latency_s,cost_usd}]}

# src/obs/recorder.py
RunRecorder(runs_dir: str, run_id: str=auto)  # .record(node,kind,data) ; .flush() -> Path  (writes runs/<id>.jsonl)

# src/llm/schemas.py  (Pydantic v2 models)
AnalystReport(summary:str, key_points:list[str], data:dict, confidence:float[0..1], citations:list[str])
DebateTurn(role:Literal["bull","bear","conservative","aggressive"], round:int>=1, argument:str)
ResearchDebate(rounds:list[DebateTurn], bull_thesis:str, bear_thesis:str, facilitator_verdict:str)
TradeProposal(action:Literal["BUY","SELL","HOLD"], conviction:float[0..1], score:int[0..100], rationale:str)
RiskDebate(rounds:list[DebateTurn], conservative:str, aggressive:str, arbiter_decision:str, adjustments:list[str])
FinalDecision(action, conviction, score, rationale)   # same shapes as TradeProposal

# src/state.py
AgentState (TypedDict, total=False) keys:
  ticker, resolved_ticker, screener, exchange, investor_mode, model_plan,
  analyst_reports (reducer: merge_named_reports),
  research_debate (reducer: merge_named_reports),
  risk_debate (reducer: merge_named_reports),
  trade_proposal, final_decision, final_report,
  financial_data,          # ADDED by WP-F (radar/metric-card inputs); additive, single-writer (reporter)
  run_metrics (reducer: operator.add — list of per-node metric dicts),
  run_id
merge_named_reports(left, right) -> dict   # shallow dict merge, right wins

# src/graph.py
build_graph(debate_mode: str | None = None)  # see §4; returns compiled graph
# node names: router, news_analyst, fundamentals_analyst, technicals_analyst,
#   bull, bear, facilitator, trader, risk_conservative, risk_aggressive, risk_arbiter, reporter
```

## 2. Mandatory conventions (ALL WPs follow these exactly)

**Async nodes.** Every real graph node is an `async def node(state: AgentState) -> dict`. LLM calls use `await llm.ainvoke(...)`. Blocking SDK calls (Firecrawl/yfinance/tradingview) are wrapped: `await asyncio.to_thread(sync_fn, ...)`.

**Structured output.** Never parse JSON from text. Use:
```python
from src.llm.factory import get_llm
from src.llm.cost import CostTracker
from src.llm.schemas import TradeProposal

async def trader(state):
    tracker = CostTracker("trader")
    llm = get_llm("deep").with_structured_output(TradeProposal, method="function_calling")
    result: TradeProposal = await llm.ainvoke(messages, config={"callbacks": [tracker]})
    return {"trade_proposal": result.model_dump(), "run_metrics": tracker.totals()["per_node"]}
```
- Default `method="function_calling"`. Each WP MUST verify Ollama Cloud tool-calling support for its chosen models via Context7/live probe; if a model lacks tool calling, fall back to `method="json_schema"` and document it in the plan.
- `with_structured_output` returns the Pydantic model directly; store `result.model_dump()` into state.

**Metrics.** Each node creates one `CostTracker(node_name)`, passes it as a callback to every LLM call it makes, and returns `"run_metrics": tracker.totals()["per_node"]`. The `operator.add` reducer concatenates across nodes.

**Prompts.** System prompts live next to their node (module-level constants). Keep them short, role-specific, and reference only the typed state fields the node consumes.

**No network in unit tests.** Mock `get_llm` (return a fake whose `.with_structured_output(...).ainvoke(...)` returns a prepared Pydantic model) and mock tool SDKs (`respx` for HTTP, monkeypatch for SDK objects). Provide ONE opt-in live integration test per WP, marked `@pytest.mark.live` and skipped unless `RUN_LIVE=1`.

**Imports.** Absolute: `from src.llm.factory import get_llm`. Repo root is on `sys.path` under pytest and `python -m`.

**Commits.** Conventional commits, frequent, one per task (test→impl→commit). End commit messages with the standard co-author trailer used in this repo.

## 3. Node / file ownership map

| Stub node(s) replaced | Owner WP | New files |
|---|---|---|
| `router` (ticker resolution + model plan) | **WP-B** | `src/agents/router.py` |
| `news_analyst`, `fundamentals_analyst`, `technicals_analyst` | **WP-B** | `src/agents/analysts/{news,fundamentals,technicals}.py`, `src/tools/{firecrawl,yfinance,tradingview}.py` |
| (memory layer, no node) | **WP-C** | `src/memory/{store,embeddings,cache}.py` |
| `bull`, `bear`, `facilitator` + debate runner + `build_graph` toggle | **WP-D** | `src/agents/research/{bull,bear,facilitator}.py`, `src/agents/debate.py` |
| `trader`, `risk_conservative`, `risk_aggressive`, `risk_arbiter` | **WP-E** | `src/agents/{trader.py}`, `src/agents/risk/{conservative,aggressive,arbiter}.py` |
| `reporter` | **WP-F** | `src/agents/reporter.py` |
| (API/UI, no node) | **WP-G** | `src/api/{main,stream,schemas}.py`, `web/*` |
| (eval, no node) | **WP-H** | `src/eval/{harness,judge,report}.py`, `evals/tickers.json` |
| (tests/CI + legacy removal) | **WP-I** | `tests/integration/*`, `.github/workflows/ci.yml`, deletes legacy |

## 4. Cross-WP interface decisions (resolve ordering ambiguity up front)

**Shared debate runner — owned by WP-D, reused by WP-E.** WP-D creates:
```python
# src/agents/debate.py
async def run_debate(
    topic: str,
    context: str,
    personas: list[tuple[str, str]],   # [(role, system_prompt), ...]
    rounds: int,
    tier: str = "deep",
    node_label: str = "debate",
) -> tuple[list[DebateTurn], dict]:    # (turns, metrics_per_node)
    ...
```
WP-E imports `run_debate` for the conservative↔aggressive risk debate. WP-E's plan MUST declare a dependency on WP-D being merged first (or stub `run_debate` locally behind the same signature if developed in parallel).

**`build_graph(debate_mode)` — owned by WP-D.** WP-D evolves `build_graph` to accept `debate_mode`:
- `"on"` (default from settings): full topology (bull/bear/facilitator).
- `"off"`: bull/bear/facilitator are bypassed by a single `research_synthesis` node (one `get_llm("deep")` pass that writes `research_debate.facilitator_verdict` directly). This is the A/B baseline.
WP-H (eval) calls `build_graph("on")` and `build_graph("off")` to compare. WP-D must implement and test both paths.

**Memory is opt-in for nodes — owned by WP-C, consumed by WP-B/E.** WP-C exposes:
```python
# src/memory/cache.py
get_cached_verdict(ticker: str, max_age_min: int) -> FinalDecision | None   # deterministic metadata query
store_verdict(ticker: str, decision: FinalDecision) -> None
# src/memory/store.py  -> thin Chroma wrapper used by cache + future reflection
```
The `router` (WP-B) MAY call `get_cached_verdict` to short-circuit; the `risk_arbiter` (WP-E) calls `store_verdict`. Both WPs treat memory as an injected dependency and mock it in tests. If WP-C is not yet merged, these calls are guarded (`try/except ImportError` or a feature flag) so the graph still runs.

**API streams the compiled graph — owned by WP-G.** WP-G codes against `build_graph()` + `AgentState` only; it works on the stub graph and automatically benefits when real nodes land. Use `graph.astream(input, stream_mode=["updates","messages"])` for node-level + token-level SSE. WP-G verifies LangGraph 1.0.4 stream-mode behavior via Context7.

## 5. Plan format requirements (every WP plan file)

- Path: `docs/superpowers/plans/2026-05-29-wp-<letter>-<name>.md`.
- Start with the EXACT header block (see Foundation plan): `# … Implementation Plan` + the `> For agentic workers:` line + `**Goal:**` + `**Architecture:**` + `**Tech Stack:**` + `---`.
- A `## File Structure` table (file → responsibility).
- Bite-sized TDD tasks: each step is one 2–5 min action. Test→run-fail→implement→run-pass→commit. Show COMPLETE code in every code step. Exact file paths, exact commands, expected output.
- NO placeholders ("TBD", "add error handling", "similar to above", undefined symbols). Repeat code rather than cross-reference.
- A `## Definition of Done` checklist.
- A `## Dependencies` note: which WPs/Foundation must be merged first, and how to develop in parallel if not (stub-behind-signature).
- New runtime deps: add to `pyproject.toml` `[project.optional-dependencies]` in the plan's first task, pinned to a version the plan author verified via Context7.

## 6. Library reference (verify current APIs via Context7 before writing code steps)

| WP | Libraries to verify | Notes |
|---|---|---|
| B | `firecrawl-py` (v2 `search`/`scrape`), `yfinance`, `tradingview-ta` | Firecrawl v2 search returns web results; scrape returns markdown. Confirm SDK class + method names. |
| C | `chromadb` (PersistentClient, collections, metadata `where` filter), `fastembed` (`TextEmbedding`) | Deterministic recency = metadata `where={"ticker":..}` + sort by stored `ts`, NOT similarity search. |
| D | `langgraph` (conditional edges / subgraph for bounded rounds), `langchain-core` messages | Bounded debate loop inside a node or via a small subgraph. |
| E | (reuse `run_debate`), `langchain-core` | — |
| F | `langgraph` streaming, markdown formatting | Reporter emits markdown + a `financial_data` dict (radar-chart inputs) into state. |
| G | `fastapi`, `sse-starlette` (`EventSourceResponse`), `langgraph` `astream` | Async SSE; verify `stream_mode` list support in 1.0.4. |
| H | (no new external) deep judge via `get_llm("deep")` | Honest framing: quality proxy = judge agreement + cost/latency delta, NOT P&L. |
| I | `pytest`, `pytest-asyncio`, `respx` | Integration tests on mocked externals; CI matrix on py3.11/3.13. |

---

## 7. Resolved coordination events (READ BEFORE EXECUTING ANY WP)

These were surfaced while authoring the WP plans and are now authoritative. Where a WP plan conflicts with this section, this section wins.

### 7.1 Packaging — canonical `pyproject.toml` build system
The Foundation `pyproject.toml` MUST include a build system and package discovery so that `pip install -e ".[dev]"` (Foundation), `pip install ".[all]"` (WP-I CI), and the Docker image (WP-G) all work. `src` is currently a **namespace package** (no `src/__init__.py`) — keep it that way; setuptools namespace discovery handles it. Add to `pyproject.toml`:

```toml
[build-system]
requires = ["setuptools>=68"]
build-backend = "setuptools.build_meta"

[tool.setuptools.packages.find]
where = ["."]
include = ["src*", "scripts*"]
namespaces = true
```

And add an aggregate extra (WP-I references `.[all]`). The `all` extra must list every group's pins:
```toml
[project.optional-dependencies]
all = [ "<everything from data + web + memory + api + dev>" ]
```
**Action:** Foundation Task 1 includes `[build-system]` + `[tool.setuptools.packages.find]`. WP-I's final pyproject task assembles the `all` extra from the groups each WP added. Do NOT create `src/__init__.py`.

### 7.2 `src/graph.py` is owned solely by WP-D
Only **WP-D** edits `build_graph` (wiring, node imports, the `debate_mode` toggle). Every other node-owning WP (B/E/F) ONLY delivers its node module with the agreed function name/signature; it does **not** edit `build_graph`'s `add_node`/`add_edge`/import lines. The "swap stub import → real import" edits are performed in `build_graph` by WP-D (or at integration). This removes the WP-B↔WP-D conflict: WP-B's plan step that edits `graph.py` wiring is superseded — WP-B delivers `router`/analyst modules only; WP-D imports them.

**Clarification (binding) — this means WP-B is correct to NOT touch `src/graph.py`.** A spec reviewer flagged WP-B for "not updating build_graph"; that flag is dismissed — WP-B's plan Task 13 (which edited `build_graph`) is explicitly superseded by this section.

**Mechanism WP-D must implement — guarded imports for ALL real nodes.** When WP-D rewrites `build_graph`, it wires the real callables for **every** node-owning WP (its own bull/bear/facilitator/synthesis AND WP-B's router+3 analysts AND WP-E's trader+3 risk nodes AND WP-F's reporter), each behind a guarded import so an unmerged WP falls back to the existing stub:
```python
try:
    from src.agents.router import router            # WP-B
except ImportError:
    from src.graph_stubs import router               # or keep the inline stub
```
This makes each WP's real node auto-activate the moment its module exists on the branch, requires editing `graph.py` exactly once (in WP-D), and needs NO big-bang integration. WP-D's executor MUST wire B/E/F nodes too — not only D's own. If a node module is absent at WP-D time, its stub remains and is swapped in automatically when that WP merges.

### 7.3 Async nodes + the Foundation skeleton test
Real nodes are `async def`. LangGraph's compiled `app.invoke(...)` DOES execute async nodes (it drives the event loop), so `tests/test_graph_skeleton.py` keeps passing as written. WP-D may optionally switch that test to `await app.ainvoke(...)` under pytest-asyncio, but it is not required. New per-node tests use `app.ainvoke`/`pytest.mark.asyncio`.

### 7.4 `debate_mode="off"` node/metric count
`"on"` topology = 12 nodes → 12 `run_metrics` records. `"off"` replaces `bull`,`bear`,`facilitator` (3) with a single `research_synthesis` node (1) → **10 nodes → 10 `run_metrics` records**. WP-D, WP-H, and WP-I all assert against these counts (12 on / 10 off). Changing them is a coordination event.

### 7.5 Structured-output method is a single shared constant
Every WP defaults to `with_structured_output(Schema, method="function_calling")`. To allow a one-line global fallback if an Ollama model lacks tool calling, the method is read from one place: `src/llm/factory.py` exposes `STRUCT_METHOD = "function_calling"` (Foundation adds this constant). All nodes call `get_llm(tier).with_structured_output(Schema, method=STRUCT_METHOD)`. The live probe tests (`@pytest.mark.live`) verify tool calling; if they fail, flip `STRUCT_METHOD` to `"json_schema"` in one spot. **Action:** Foundation Task 6 adds `STRUCT_METHOD` to `factory.py`; all WPs import it rather than hardcoding the string.

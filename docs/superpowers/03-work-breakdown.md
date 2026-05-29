# Work Breakdown — Dev Subagent Plan

Companion to `specs/2026-05-29-finresearchai-agentic-upgrade-design.md`. Designed so independent work packages run concurrently after a small blocking foundation. Feeds the `writing-plans` step.

## Dependency shape

```
Phase 0 (Foundation) ──► Phase 1 (State contract) ──► Phase 1b (parallel WPs B–I) ──► Phase 2 (Integration)
```

Everything in Phase 1b depends only on the **frozen state contract** from Phase 1. That contract is the coordination point — once `state.py` + Pydantic schemas are merged, work packages do not block each other.

## Phase 0 — Foundation (1 agent, blocking)
Unblocks everyone. No agent logic yet.
- `config/settings.py` (pydantic-settings: provider, base_url, key env names, tiers, debate rounds, flags) + `config/models.yaml`.
- `llm/factory.py` (`get_llm(tier)`, cached singletons) + `llm/cost.py` (token/cost/latency callback).
- `obs/recorder.py` (RunRecorder → JSONL).
- `pyproject.toml` (pinned deps), `.env.example`, `Dockerfile` skeleton.
- **Exit criteria:** `get_llm("quick")` and `get_llm("deep")` return working clients against Ollama Cloud; a smoke script logs a run with metrics.

## Phase 1 — State contract (1 agent, blocking-lite)
- `state.py` (typed `AgentState`, §4 of spec).
- `llm/schemas.py` (Pydantic models for every node's structured output).
- `graph.py` skeleton: all 12 nodes registered as stubs, edges + conditional fan-out wired, compiles and runs end-to-end returning stub data.
- **Exit criteria:** `python -m ...` runs the stubbed graph start→END; state shape is frozen and documented.

## Phase 1b — Parallel work packages (many agents)
Each is independently testable against the frozen contract.

| WP | Scope | Key files | Depends on |
|---|---|---|---|
| **B** Tools + Analysts | Firecrawl/YFinance/TradingView wrappers (typed, error-surfacing) + 3 analyst nodes | `tools/*`, `agents/analysts/*` | Phase 1 |
| **C** Memory | Chroma store, metadata-query cache, fastembed embeddings | `memory/store.py`, `memory/embeddings.py` | Phase 1 |
| **D** Research debate | Bull, Bear, Facilitator with bounded rounds | `agents/research/*` | Phase 1 |
| **E** Trader + Risk debate | Trader verdict, conservative/aggressive personas, arbiter | `agents/trader.py`, `agents/risk/*` | Phase 1 |
| **F** Reporter | Streamed markdown + structured `financial_data` | `agents/reporter.py` | Phase 1 |
| **G** API + UI | FastAPI SSE endpoints, thin frontend | `api/*`, `web/*` | Phase 1 |
| **H** Eval | Debate A/B harness, deep-judge, report generator | `eval/*` | Phase 1, (D/E for full run) |
| **I** Tests + CI | Mocked LLM/tools, real assertions, CI workflow | `tests/*`, CI config | Phase 1 |

## Phase 2 — Integration & polish (1–2 agents)
- Replace stub nodes with real implementations; resolve contract drift.
- End-to-end run on Ollama Cloud for a few tickers.
- Run the debate A/B harness; produce the first eval report in `evals/`.
- Docker build + HF Docker Space deploy; wire optional Redis.
- README / portfolio writeup: architecture diagram, the A/B finding, cost-per-verdict, "what we changed vs. the paper."
- **Exit criteria:** reviewer clones, sets 2 keys, runs first-try, watches debate stream, reads eval report.

## Suggested agent assignment
- Foundation + State contract: one careful agent, sequential (these gate everything).
- Phase 1b: up to 8 parallel agents (one per WP), each in its own worktree to avoid file conflicts.
- Integration: a single owner agent who holds the whole graph in context, plus a reviewer agent.

## Definition of done (project)
- [ ] Runs end-to-end on Ollama Cloud + Firecrawl, no paid OpenAI/Pinecone keys.
- [ ] All node I/O is structured (Pydantic), zero JSON string-scraping.
- [ ] Live SSE streaming of the debate to the UI.
- [ ] Eval report comparing debate-on vs. debate-off on quality + cost/latency.
- [ ] Honest observability (run traces, metrics), no error spam.
- [ ] Real tests with mocks + green CI.
- [ ] Deployed Docker HF Space; reproducible README.
- [ ] Dev API keys rotated.

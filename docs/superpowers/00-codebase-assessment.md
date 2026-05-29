# Codebase Assessment — Current FinResearchAI

Senior-engineering audit of the existing app (active dir: `FinResearchAI/`). Source for the upgrade spec. Date: 2026-05-29.

## Architecture model (as-is)

LangGraph `StateGraph` (`src/graph.py:31-66`):
```
__start__ → manager → [conditional fan-out] → {tavily_researcher, yfinance_researcher, tradingview_researcher} → analyst → reporter → __end__
```
- **Manager** (`src/agents/manager.py`): two sequential `gpt-4o-mini` calls — (1) audit Pinecone cache freshness per data-type (`_get_recency`, line 28) + emit `agents_to_run`; (2) resolve ticker suffix / screener / exchange. Short-circuits the graph if a `final_verdict` doc is <5 min old (lines 68-77).
- **Routing** (`route_research`, `graph.py:17-28`): returns `agents_to_run`; LangGraph fans those names out in parallel; empty → `["analyst"]`. Verified compiles + fans out under langgraph 1.0.4.
- **Researchers** write raw payloads to Pinecone tagged `ticker/source/type` and return only a status message. YFinance + TradingView are pure-fetch; Tavily summarizes via LLM (`tavily.py:65`).
- **Analyst** (`analyst.py`): does NOT read research from graph state — it re-queries Pinecone (`similarity_search(k=15)`, line 40), one LLM call → `aggregated_view` + `verdict{score,recommendation,reasoning}`, writes verdict back to Pinecone.
- **Reporter** (`reporter.py`): another `similarity_search(k=10)`, one LLM call → markdown + a trailing ` ```json ` block parsed by regex (line 98) into `financial_data`.
- **Shared memory** is exclusively Pinecone (`src/memory.py`). Research payloads flow agent→Pinecone→agent, **not** through state — inter-node communication depends on Pinecone eventual-consistency (write-then-read race).
- Entry points: `main.py` (CLI, `app.stream`), `app.py` (1938-line Gradio UI, `app.invoke`).

## Dimension scores

| Dimension | Score | Evidence |
|---|---|---|
| Architecture & modularity | 7/10 | Clean node separation, but payloads tunnel through Pinecone (`analyst.py:40`, `reporter.py:36`) → hidden coupling + race; every node re-instantiates `VectorMemory()`+`ChatOpenAI()` per call. |
| Agent design | 5/10 | Hand-rolled structured output: `response.content.replace("```json","")` + `json.loads` in every agent (`manager.py:135`, `analyst.py:92`, `reporter.py:98`). No `with_structured_output`, no tool-calling. Manager makes 2 calls where 1/0 would do. |
| State correctness | 4/10 | `main.py:32-41` keeps only chunks where `"final_report" in value`, discarding other node outputs; relies on reporter being last (self-admitted in comments). `state.py` has vestigial `dataset`/`next_step`; `messages` reducer unused. |
| Memory/caching | 5/10 | Freshness tiers (FRESH<5m/STALE<60m/EXPIRED) are nice, but recency uses **semantic search + filter** (`manager.py:32`) not a metadata query → can miss newest doc. No TTL/eviction. `REDIS_*` in `.env` but Redis never imported. App cache is in-process dict (`app.py:34`). |
| Observability | 2/10 | LangSmith **not wired in code** (zero refs). Works only by `.env` auto-detect; emits repeated `403 Forbidden` (invalid key). `print()` mixed with `logging`. |
| Modernity (2025/26) | 4/10 | `gpt-4o-mini` hardcoded in 4 files, no config/router/fallback. No structured outputs, no async, no UI streaming, no eval harness, no guardrails beyond regex JSON-scrubbing. |
| Testing | 3/10 | 3 files, no real core assertions. `test_flow.py` checks tags (`"yfinance"`, `"tavily_search"`) that don't match what code writes (`YFinance_Data`, `Tavily_News_Raw`) → dead asserts. `test_ui_logic.py` has no asserts. No CI. |
| Error handling | 5/10 | Broad coverage but silent `except Exception` everywhere masks failures; `app.py:1569-1574` has alternate-key hacks signaling an unreliable structured-output contract. |
| Deployability | 7/10 | Gradio HF frontmatter, `validate_env()`, rate-limit + XSS escaping. Confirmed `app.py` boots + binds port. Negatives: unpinned `requirements.txt` lists deprecated `pinecone-client`; Pipfile pins py3.11 vs runtime 3.13; no Dockerfile. |

**Overall ≈ 47/100 — D+ / C-.** Competent student-grade demo with thoughtful touches (parallel fan-out, cache tiers, UI hardening) undermined by hand-rolled JSON parsing, broken observability, dead tests, and Pinecone-as-message-bus.

## Run results (verbatim)

Environment: Python 3.13.5; langgraph 1.0.4, langchain 1.1.0, langchain-openai 1.1.6, langchain-pinecone 0.2.13, pinecone 7.3.0, gradio 6.2.0. All imports succeed.

- `python main.py --ticker AAPL` → **FAILED** at the `manager` node. Surface error: `UnicodeEncodeError: 'latin-1' codec...` from `PineconeVectorStore.__init__` → `describe_index` (`memory.py:33`). Root cause: `pinecone.exceptions.UnauthorizedException: (401) Invalid API Key` (the UnicodeError is a secondary artifact on the unauthorized path).
- **Key validity probe:** `OPENAI_API_KEY` → 401 invalid; `PINECONE_API_KEY` → 401 invalid; `LANGSMITH_API_KEY` → 403 forbidden (spams stderr); `TAVILY_API_KEY` → **valid**. Since every node calls OpenAI + Pinecone, the pipeline cannot complete regardless of code.
- `python app.py` (Gradio) → **boots successfully**, binds port (HTTP 200). `validate_env()` only checks key *length* (>10 chars), not validity, so the UI launches and would 401 on submit.
- **No source changes were made** during the audit.

> Note: as of this upgrade, the LLM half is solved by the **Ollama Cloud** key and web research by the **Firecrawl** key (both verified working); Pinecone is being removed in favor of state-passing + embedded Chroma.

## Ranked weaknesses → upgrade opportunities

1. **Dead credentials block all execution** (OpenAI, Pinecone, LangSmith). No degraded mode; `validate_env` checks length not validity. *S.*
2. **No structured outputs** — JSON scraped by string-replace in 4 places. The top "is this engineer current" tell. *M.*
3. **Observability theater** — LangSmith unwired, throwing 403s. *S–M.*
4. **`main.py` stream loop incorrect-by-design** (self-admitted). *S.*
5. **Pinecone as inter-agent bus** → write-read race + wrong-tool freshness check. *M.*
6. **Tests don't test** (assert-free prints + stale tags). *M.*
7. **Model hardcoded ×4, no router/async/UI streaming.** *M.*
8. **No eval harness.** *M–L.*
9. **Dependency hygiene** — unpinned, deprecated `pinecone-client`, py3.11 vs 3.13. *S.*
10. **Per-node object churn** — `VectorMemory()`+`ChatOpenAI()` rebuilt every call. *S.*
11. **In-process cache/rate-limit; Redis provisioned but unused.** *S–M.*
12. **Over-broad silent `except Exception` + print/logging mix.** *M.*

Each maps directly to a section of the upgrade spec.

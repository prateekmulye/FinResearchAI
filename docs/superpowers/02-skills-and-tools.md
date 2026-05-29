# Skills & Tools Matrix

Companion to `specs/2026-05-29-finresearchai-agentic-upgrade-design.md`. What building the upgrade demands, and where each competency surfaces.

## Skills required

| Competency | Why it matters (EU agentic-engineer signal) | Tools / libs | Surfaces in |
|---|---|---|---|
| LangGraph multi-agent orchestration | Conditional fan-out, subgraphs, bounded debate loops, async streaming | `langgraph` | `graph.py`, debates |
| Structured outputs / schema discipline | Replaces brittle JSON-scraping; the #1 "is this current" tell | `pydantic`, `with_structured_output` | `llm/schemas.py`, every agent |
| Provider-agnostic LLM abstraction | OpenAI-compatible endpoints, model tiering, cost control | `langchain-openai` → Ollama Cloud `/v1` | `llm/factory.py` |
| Persona / debate prompt engineering | Bull/bear and risk personas that genuinely diverge | — | `agents/research`, `agents/risk` |
| Async Python + SSE streaming | Live "agents thinking" UX; concurrency | `asyncio`, `fastapi`, `sse-starlette`, `uvicorn`, `httpx` | `api/` |
| Embedded vector stores & embeddings | Reproducible RAG cache without paid keys | `chromadb`, `fastembed` | `memory/` |
| Evaluation design (A/B, LLM-judge, cost) | Measuring whether debate earns its cost — out-rigors the paper | custom harness + deep judge model | `eval/` |
| Observability / tracing | Honest run traces + metrics, no theater | `RunRecorder`, structured `logging`, optional `langsmith` | `obs/` |
| Web scraping & search | Full-article extraction for news/sentiment | `firecrawl-py` | `tools/firecrawl.py` |
| Testing with mocks | Real assertions, mocked external calls, CI | `pytest`, `pytest-asyncio`, `respx` | `tests/` |
| Packaging & deploy | Pinned deps, Docker, HF Docker Space | `docker`, `uv`/`pip-tools`, pinned `pyproject.toml` | repo root |

## Tools / dependency set

**Core:** `langgraph`, `langchain-core`, `langchain-openai`, `pydantic`, `pydantic-settings`
**Memory:** `chromadb`, `fastembed`
**Web/API:** `fastapi`, `uvicorn`, `sse-starlette`, `httpx`, `firecrawl-py`
**Data:** `yfinance`, `tradingview-ta`
**Eval/obs:** custom modules, optional `langsmith`
**Quality:** `pytest`, `pytest-asyncio`, `respx`, `ruff`, `mypy`
**Optional infra:** `redis`
**Deploy:** `docker`

## External services

| Service | Use | Key | Cost |
|---|---|---|---|
| Ollama Cloud | All LLM inference (quick + deep tiers) | `OLLAMA_API_KEY` (temp, rotate) | per Ollama Cloud plan |
| Firecrawl | Web search + full-page scrape (news) | `FIRECRAWL_API_KEY` (temp, rotate) | per Firecrawl plan |
| YFinance | Fundamentals | none | free |
| TradingView-TA | Technicals (RSI/MACD/trend) | none | free (rate-limited) |
| Redis | Optional cache / rate-limit / run store | `REDIS_*` | optional |
| LangSmith | Optional tracing (off by default) | `LANGSMITH_API_KEY` | optional |

## Removed vs. current stack
- **Tavily** (`langchain-tavily`) → replaced by Firecrawl.
- **Pinecone** as message bus → replaced by typed state + embedded Chroma cache.
- **OpenAI** hardcoded `gpt-4o-mini` → provider-agnostic Ollama Cloud tiers.
- Unpinned `requirements.txt` + deprecated `pinecone-client` → pinned `pyproject.toml`.

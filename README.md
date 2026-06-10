# FinResearchAI

A multi-agent equity-research system built on **LangGraph**. A 12-node graph routes a
ticker through parallel analysts, a bounded **bull/bear debate**, a trader, a
**conservative↔aggressive risk debate**, and a reporter — producing a markdown
investment report plus a structured `final_decision` (BUY/SELL/HOLD + conviction +
score) and per-node cost/latency/token metrics.

The whole run **streams live over Server-Sent Events**: one event per node start/complete,
token deltas as agents speak, terminating in a `done` event carrying the report,
decision, and metrics. It ships as a **docker-compose** stack (Caddy + FastAPI + Postgres).

## Architecture

```
router → [news · fundamentals · technicals analysts] (parallel)
       → bull ∥ bear → facilitator        (debate_mode="on")
         └─ research_synthesis             (debate_mode="off", A/B baseline)
       → trader
       → risk_conservative ∥ risk_aggressive → risk_arbiter
       → reporter → END
```

- **LLM backbone:** provider-agnostic `ChatOpenAI` pointed at **Ollama Cloud** (`/v1`),
  with quick/deep model tiers (M7 routing). No GPU, no OpenAI key.
- **State:** a typed `AgentState` (`src/state.py`) is the primary channel; structured
  Pydantic reports are passed between nodes (no JSON string-scraping).
- **Memory:** embedded **Chroma** + local `fastembed` (BGE-small, 384-dim) as a
  deterministic cross-run *verdict cache* — metadata recency query, not similarity.
- **Web research:** **Firecrawl** search/scrape (replaces the old Tavily/Pinecone path).
- **Observability:** a `CostTracker` callback records per-node tokens/latency/cost;
  `RunRecorder` writes a JSONL trace per run, replayable at `GET /runs/{run_id}`.
- **Evaluation:** `src/eval/` runs `build_graph("on")` vs `("off")` on a ticker set and
  reports judge-preference + score/cost/latency deltas — an honest **proxy** (not P&L),
  the debate-value ablation the reference paper (arXiv 2412.20138, TradingAgents) omits.

## Configuration

Set as environment variables / HF Space secrets (never commit):

```
OLLAMA_API_KEY=<your-key>       # Ollama Cloud
FIRECRAWL_API_KEY=<your-key>    # web research
```

Optional: `ALLOWED_ORIGINS` (CORS, default `*`), `REDIS_URL` (shared rate-limit
backend; in-memory otherwise), `RUNS_DIR` (trace dir, default `runs`),
`DEBATE_MODE` (`on`|`off`), `TRUST_PROXY` (honor `X-Forwarded-For` behind a proxy).

## Develop

```bash
pip install -e ".[all]"              # all optional groups (memory, web, data, api, dev)
python -m pytest -q                  # offline test suite (live tests need RUN_LIVE=1)
ruff check . && mypy src             # lint + type-check
uvicorn src.api.main:app --port 7860 # run the API
python -m src.eval.run --tickers evals/tickers.json --label demo  # debate A/B eval
```

`POST /analyze` streams the run as SSE; `GET /healthz` is the liveness probe.
The dependency-free client `web/index.html` renders the stream live.

## Deploy

Ships as a docker-compose stack (Caddy auto-HTTPS + app + Postgres/pgvector) on any
VPS — deployment guide lands in `docs/deploy.md` as part of the v2 elevation.

## License

[MIT](./LICENSE)

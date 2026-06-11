# FinResearchAI

**Multi-agent equity research you can watch think.** A 12-node LangGraph pipeline streams
three parallel analysts, a bounded bull/bear debate, a trader, and a risk debate into a
BUY / SELL / HOLD verdict — live over SSE, persisted to a Postgres warehouse, replayable
forever, and measured by the debate-cost ablation its reference paper omits.

[![CI](https://github.com/prateekmulye/FinResearchAI/actions/workflows/ci.yml/badge.svg)](https://github.com/prateekmulye/FinResearchAI/actions/workflows/ci.yml)
[![License: MIT](https://img.shields.io/badge/license-MIT-blue.svg)](./LICENSE)
[![Python](https://img.shields.io/badge/python-3.11%20%7C%203.13-3776AB?logo=python&logoColor=white)](./pyproject.toml)
[![React](https://img.shields.io/badge/react-19-61DAFB?logo=react&logoColor=black)](./web/package.json)
[![Demo](https://img.shields.io/badge/demo-replay--first-6E56CF)](#quickstart)

**Live demo:** coming soon at `finresearch.prateekmulye.dev` — until then, the
[zero-key demo](#a-zero-key-demo-no-api-keys) runs the full app on your machine in
about two minutes.

![Analyze cockpit — the 12-node pipeline resolving AAPL into a verdict](docs/assets/hero-cockpit.png)

Type a ticker, watch the agent graph light up node by node as analysts report, the bull
and bear argue, the trader sizes a position, and a conservative↔aggressive risk debate
settles into a final decision with a 0–100 score and conviction — with per-node cost,
latency, and token counts streamed the whole way. Every run is written through to a
Postgres + pgvector warehouse, so the research library, timeline replays, market data,
and semantic search keep working even when live-run quota is spent.

## How it works

```mermaid
flowchart LR
    router[router]
    subgraph analysts [parallel analysts]
        news[news analyst]
        fund[fundamentals analyst]
        tech[technicals analyst]
    end
    subgraph debate [research debate]
        bull[bull researcher]
        bear[bear researcher]
        facilitator[facilitator]
    end
    trader[trader]
    subgraph risk [risk debate]
        cons[conservative]
        aggr[aggressive]
        arbiter[risk arbiter]
    end
    reporter[reporter]

    router --> news
    router --> fund
    router --> tech
    news --> bull
    fund --> bull
    tech --> bull
    news --> bear
    fund --> bear
    tech --> bear
    bull --> facilitator
    bear --> facilitator
    facilitator --> trader
    trader --> cons
    trader --> aggr
    cons --> arbiter
    aggr --> arbiter
    arbiter --> reporter
```

That is the debate-**on** topology (12 nodes). `build_graph("off")` swaps the three
debate nodes for a single `research_synthesis` node (10 nodes) — the single-pass
baseline the [eval harness](#the-ablation-the-paper-omits) compares against.

- **State-first LangGraph.** A typed `AgentState` (`src/state.py`) is the only channel
  between nodes; concurrent writers (analyst reports, debate transcripts, metrics) merge
  through explicit reducers, never last-write-wins.
- **Structured outputs only.** Every node calls
  `with_structured_output(Schema, method=STRUCT_METHOD)` against Pydantic models — no
  JSON string-scraping anywhere in the pipeline.
- **Degrade everywhere.** A node whose LLM or tool call fails returns a schema-shaped
  fallback plus a zero-metrics trace line; one failure never aborts the graph or drops
  observability.
- **Write-through warehouse.** Analyst tools persist whatever they fetch (prices,
  fundamentals, news) into Postgres 16 + pgvector during each run; a nightly in-process
  collector refreshes a 30-ticker watchlist across US, Indian, Japanese, Chinese,
  Hong Kong, and European exchanges.
- **Quick/deep model tiers.** Provider-agnostic `ChatOpenAI` pointed at Ollama Cloud's
  OpenAI-compatible `/v1` — `gpt-oss:20b` for routing, analysts, and reporting;
  `gpt-oss:120b` for debate, trading, risk, and judging. No OpenAI key, no GPU.
- **Local embeddings.** fastembed BGE-small (384-dim) embeds news and report summaries at
  write time; semantic search is a pgvector cosine query with a keyword fallback. No
  embedding API key.

## Screenshots

| Research library | Timeline replay |
| --- | --- |
| ![Research library — every run, replayable](docs/assets/library.png) | ![Replay theater — transport bar scrubbing a recorded run](docs/assets/replay.png) |

| Market dossier | Eval dashboard |
| --- | --- |
| ![Market dossier — candlesticks, fundamentals, news](docs/assets/market.png) | ![Eval dashboard — does the debate earn its cost?](docs/assets/eval.png) |

## The ablation the paper omits

The design adopts a deliberate subset of *TradingAgents*
([arXiv 2412.20138](https://arxiv.org/abs/2412.20138)): bull/bear debate, quick/deep
model routing, structured state-passing, and an actionable signal. The paper, however,
never isolates what the debate itself buys you. This repo does:

```bash
python -m src.eval.run --tickers evals/tickers.json --label demo
```

runs every ticker through both topologies — debate-on and debate-off — and reports
action agreement, a blind judge's reasoning preference, score deltas, and the exact
cost/latency/token price of the debate, persisted to the warehouse and visualized on the
Eval page.

**Honest framing:** the quality signal is a *judge-preference proxy*, not realized P&L.
The harness runs no backtest and reports no returns; the judge sees the two verdicts in a
fixed A/B position, so a small positional bias is possible. That disclaimer is embedded
in every report it writes (`PROXY_DISCLAIMER` in `src/eval/report.py`) — I'd rather ship
a number I can explain than a backtest I can't defend.

## Features

- **Live cockpit** — the agent graph lights node by node from the SSE stream; bull/bear
  theses stream side by side; the decision reveals with a conviction gauge and a live
  cost ticker.
- **Run library + replay** — every run is persisted with its full event stream; any run
  replays through a timeline scrubber with transport controls, exactly as it happened.
- **Market explorer + semantic search** — global instrument search, candlestick /
  fundamentals / news dossiers, and pgvector semantic search over accumulated research.
- **Eval dashboard** — the debate A/B results: judge preference, score deltas, and a
  cost-vs-quality scatter per ticker.
- **Demo guard** — live runs are capped per IP and globally per day (Postgres-backed,
  restart-proof); the library, replays, and market data stay free; an `X-Admin-Token`
  header bypasses caps.
- **Fake-LLM mode** — `APP_FAKE_LLM=1` boots the entire stack with a deterministic
  offline LLM and canned market data: no keys, no network, no cost. It powers the e2e
  suite and the zero-key demo below.

## Quickstart

### a) Zero-key demo (no API keys)

Deterministic fake LLM + canned data — the full UI with nothing to sign up for.

```bash
pip install -e ".[all]"

# seed a throwaway SQLite warehouse with a few demo runs
APP_FAKE_LLM=1 DATABASE_URL=sqlite+aiosqlite:////tmp/finr.db \
    python scripts/seed_library.py

# backend
APP_FAKE_LLM=1 DATABASE_URL=sqlite+aiosqlite:////tmp/finr.db \
    uvicorn src.api.main:app --port 7860

# frontend (second terminal) → open http://localhost:5173
cd web && npm install && npm run dev
```

### b) Real mode (live LLMs + market data)

```bash
cp .env.example .env          # add OLLAMA_API_KEY and FIRECRAWL_API_KEY
pip install -e ".[all]"

docker compose up -d db       # Postgres 16 + pgvector on localhost:5433
alembic upgrade head          # create the warehouse schema

export DATABASE_URL=postgresql+asyncpg://finresearch:finresearch@localhost:5433/finresearch
uvicorn src.api.main:app --port 7860
cd web && npm install && npm run dev
```

The warehouse is optional — without `DATABASE_URL` the graph still runs and records
JSONL traces; you lose the library, market explorer, and search.

### c) Production

One VPS, three containers (Caddy auto-HTTPS → FastAPI → Postgres):

```bash
docker compose -f docker-compose.prod.yml up -d --build
```

Full runbook — DNS, secrets, first-run checks, updates, backups, and the gated GitHub
Actions deploy pipeline — in [`docs/deploy.md`](./docs/deploy.md).

## API

Everything under `/api`, liveness at the root:

| Endpoint | What it does |
| --- | --- |
| `POST /api/analyze` | Run the graph; streams SSE (`start` / `node_start` / `node_complete` / `token` / `done` / `error`). |
| `GET /api/library` | Past runs, newest first, filterable by ticker/status. |
| `GET /api/runs/{run_id}` | Full run detail + the recorded event stream for replay. |
| `GET /api/market/instruments?q=` | Global instrument search across the watchlist. |
| `GET /api/market/{ticker}/prices` | Daily candles (also `/fundamentals`, `/news`). |
| `GET /api/eval/results` | Persisted debate A/B eval results. |
| `GET /api/search?q=` | Semantic (pgvector) search over news + run summaries, keyword fallback. |
| `GET /api/quota` | Remaining live-run demo quota for the caller. |
| `GET /healthz` | Liveness probe. |

## Stack

- **Backend:** Python 3.11+, LangGraph, FastAPI + sse-starlette, SQLAlchemy 2 (async) +
  Alembic, Postgres 16 + pgvector, fastembed (BGE-small), APScheduler
- **LLMs:** Ollama Cloud via `langchain-openai` (`gpt-oss:20b` quick / `gpt-oss:120b` deep)
- **Data:** yfinance, Firecrawl, tradingview-ta
- **Frontend:** React 19, Vite, TypeScript, Tailwind v4 + shadcn/ui, TanStack Query,
  @xyflow/react, lightweight-charts, Recharts, Motion
- **Ops:** Docker Compose, Caddy (auto-HTTPS), GitHub Actions (5-job CI + gated deploy),
  Dependabot, gitleaks / pip-audit / Trivy

## Repository layout

```
src/            the application — graph, agents, llm, tools, api, warehouse, collector, eval, memory, obs
web/            React SPA (Vite + TS); design tokens in web/DESIGN.md
tests/          offline unit + integration suites (540 tests; no network)
migrations/     Alembic schema for the warehouse
evals/          curated A/B ticker set; eval reports land here
scripts/        dev utilities (demo seeder, smoke test)
docker/         container entrypoint
docs/           deploy runbook, design history (docs/superpowers/), screenshots
.github/        CI + gated deploy workflows, Dependabot
```

## Testing

815 tests: **540 backend** (pytest, fully offline — LLMs and tools mocked) + **275
frontend** (vitest). CI runs five parallel jobs: backend matrix (3.11/3.13), frontend
gates, real-Postgres integration, security (gitleaks + pip-audit + npm audit), and a
fake-LLM e2e smoke with a Trivy image scan.

```bash
python -m pytest -q                 # backend, offline
ruff check . && mypy src            # lint + types
cd web && npm run lint && npm run typecheck && npm run test:run && npm run build
```

Live tests (real Ollama Cloud + Firecrawl) are opt-in: `RUN_LIVE=1 python -m pytest -m live`.
Postgres integration tests: `docker compose up -d db`, then `python -m pytest -m db`.

## Design docs

The full design history — paper analysis, codebase assessment, work breakdown, and the
per-work-package plans behind both the original build and the flagship elevation — lives
in [`docs/superpowers/`](./docs/superpowers/). Contributions welcome: see
[`CONTRIBUTING.md`](./CONTRIBUTING.md).

## License

[MIT](./LICENSE)

# prateekmulye.dev — FinResearchAI project copy

Refreshed copy for the portfolio site. The live card is stale (it still describes the
old Pinecone/RAG prototype). Paste-ready; tweak freely.

## Project card (2–3 sentences)

> **FinResearchAI** — a multi-agent equity-research system you can watch think. A
> 12-node LangGraph pipeline streams parallel analysts, a bull/bear debate, and a risk
> debate into a BUY/SELL/HOLD verdict over SSE, persists every run to a Postgres +
> pgvector warehouse, and replays any of them on a timeline. It also ships the
> evaluation its reference paper omits: an A/B harness measuring exactly what the
> debate costs and whether a blind judge prefers its reasoning.

## Case study paragraph

> FinResearchAI started as a question about the *TradingAgents* paper (arXiv
> 2412.20138): the authors show a multi-agent debate pipeline beats baselines, but
> never isolate what the debate itself buys. I built the system as a deliberate subset
> of the paper — three parallel analysts, a bounded bull/bear exchange, a trader, and a
> two-persona risk debate, all passing typed Pydantic state through a LangGraph
> topology that degrades gracefully on any node failure — then added the ablation the
> paper skips: every ticker runs through both a debate-on and a single-pass topology,
> and a blind LLM judge scores which verdict is better reasoned while the harness
> meters the debate's exact cost, latency, and token overhead. The quality signal is
> framed honestly as a judge-preference proxy, not P&L. Around that core sits a
> production app: a FastAPI backend streaming runs over SSE, a write-through Postgres +
> pgvector warehouse with local BGE-small embeddings powering semantic search, a React
> 19 glass-shell SPA with a live agent-graph cockpit and timeline replay, a
> quota-guarded public demo with a deterministic fake-LLM mode, and a Caddy + Docker
> Compose deployment with a five-job CI pipeline. Everything runs on open-weight models
> via Ollama Cloud — no OpenAI key, no GPU.

## Suggested metrics line

> 12-node agent graph · 540 backend + 275 frontend tests · debate A/B eval harness ·
> Postgres + pgvector warehouse · React 19 · 100% open-weight models

## Links

- Repo: https://github.com/prateekmulye/FinResearchAI
- Live demo: `finresearch.prateekmulye.dev` (once the VPS is up — until then point the
  card at the repo's README hero + screenshots)
- Paper positioned against: https://arxiv.org/abs/2412.20138

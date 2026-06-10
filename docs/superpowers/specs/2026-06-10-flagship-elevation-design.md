# FinResearchAI — 2026 Flagship Elevation Design

**Date:** 2026-06-10
**Status:** Approved (brainstormed interactively, approved section-by-section)
**Supersedes:** HF-Space deployment target; Chroma verdict-cache storage

## 1. Goal

Elevate FinResearchAI from a green-but-headless multi-agent backend into a flagship
portfolio application at a June-2026 standard: world-class frontend and UX, durable data
accumulation, hardened security, automated deploys, and a clean public GitHub presence —
showcased on prateekmulye.dev.

## 2. Locked decisions

| Decision | Choice |
|---|---|
| Data scope | Research library (persisted, replayable runs) **+** market-data warehouse |
| Hosting | VPS (Hetzner/DO class), docker-compose, domain `finresearch.prateekmulye.dev` |
| Frontend stack | React 19 + Vite + TypeScript, Tailwind v4 + shadcn/ui |
| Design direction | Hybrid: Glass-SaaS shell × Terminal-dense data surfaces |
| UI design owner | `frontend-design-virtuoso` agent (two design iterations, tokens in `web/DESIGN.md`) |
| Accumulation | Write-through on every run + daily scheduled collector for watched tickers |
| Demo guard | Library/replay/market free; live runs 3/day/IP + global ~25/day; admin-token bypass |
| Pages | Analyze · Library + replay · Market Explorer · Eval A/B dashboard |
| System shape | Modular monolith: FastAPI app + warehouse module + in-process APScheduler collector |
| Storage | Postgres 16 + pgvector replaces Chroma entirely; fastembed BGE-small → `vector(384)` |
| License | MIT |

## 3. Architecture

```
[Caddy] auto-HTTPS, security headers, serves SPA dist, proxies /api/* ──►
[App: FastAPI] existing 12-node LangGraph core (topology untouched)
   ├─ src/api/        SSE /api/analyze · library · market · eval · search · quota
   ├─ src/warehouse/  (NEW) SQLAlchemy 2 async + Alembic; repository layer
   └─ src/collector/  (NEW) APScheduler in lifespan; daily watchlist refresh
[Postgres 16 + pgvector] internal-only, volume-backed
   instruments · price_bars · fundamentals_snapshots · news_items(+vector)
   · runs(+vector) · run_events · eval_results · demo_quota
External: Ollama Cloud /v1 (quick+deep) · yfinance · Firecrawl · TradingView
```

### Semantics

- **Write-through:** analyst tools persist whatever they fetch during each run.
- **Collector:** daily refresh of `instruments.watched = true` (~30 seeded tickers across
  US/India/Japan/China/HK/EU exchanges) — prices + fundamentals only; news stays on-run to
  protect Firecrawl quota.
- **Verdict cache:** `src/memory/` keeps its public API (`get_cached_verdict`,
  `store_verdict`) but is backed by Postgres — newest run for a ticker within TTL via plain
  SQL recency ordering. Preserves the metadata-recency-not-similarity contract. Chroma and
  the chromadb dependency are deleted; fastembed stays (it powers pgvector embeddings).
- **RunRecorder:** gains a Postgres sink (runs + run_events); JSONL remains the no-DB local
  fallback. `run_events` powers timeline replay in the UI.
- **Semantic search:** fastembed BGE-small (384-dim, local, no key) embeds news titles and
  report summaries at write time → pgvector HNSW/cosine → `GET /api/search?q=`.
- **`APP_FAKE_LLM=1`:** app boots with a deterministic fake LLM (reusing test fakes) —
  powers Playwright e2e, demo GIF recording, and zero-quota local demos.

## 4. API surface (under /api)

`POST /api/analyze` (SSE, semantics unchanged) · `GET /api/library` · `GET /api/runs/{id}`
(detail + events) · `GET /api/market/instruments?q=` ·
`GET /api/market/{ticker}/prices|fundamentals|news` · `GET /api/eval/results` ·
`GET /api/search?q=` · `GET /api/quota` · `GET /healthz`.

Breaking rename from the old root paths is acceptable — we own the only client.

**Demo guard:** Postgres-backed per-IP (3/day) and global (~25/day) live-run counters;
friendly 429 that steers the UI to replays; `X-Admin-Token` (env secret, constant-time
compare) bypass. Strict ticker regex allowlist before any LLM/tool call.

## 5. Frontend

- Libraries: TanStack Query, React Router, Framer Motion, `@xyflow/react` (live agent
  graph), `lightweight-charts` (candlesticks), Recharts (radar/eval charts).
- **Analyze** — agent graph lights node-by-node from SSE; bull/bear theses stream
  side-by-side; decision reveal with conviction gauge; live cost ticker.
- **Library** — searchable run history; run detail opens a timeline replay with scrubber.
- **Market Explorer** — global instrument search, candle/fundamentals/news panels,
  coverage stats, semantic search.
- **Eval** — debate A/B dashboard: judge preference, score deltas, cost/latency scatter.
- A11y: WCAG AA contrast, keyboard navigation, `prefers-reduced-motion` respected.

## 6. Security

Caddy TLS/HSTS/CSP/X-Content-Type-Options/Referrer-Policy · CORS locked to the prod domain
plus localhost dev · quota counters in Postgres (restart-proof) · non-root slim containers ·
Postgres on the internal compose network only · CI security: gitleaks, pip-audit, trivy,
Dependabot · secrets via env only; dev-era API keys rotated at deploy time.

## 7. Repo & GitHub

Public GitHub repo + remote, `main` pushed, **v2.0.0** tagged release. README rewrite:
hero GIF (recorded in fake-LLM mode), CI/license badges, mermaid architecture diagram,
`docker compose up` quickstart, live demo link, eval results table, TradingAgents
(arXiv 2412.20138) positioning. HF frontmatter and `README-hfspace.md` retired in favor of
`docs/deploy.md`. LICENSE (MIT), CONTRIBUTING.md, SECURITY.md added.

## 8. Work packages

WP-0 groundwork (spec, LICENSE, frontmatter, GitHub) → WP-1 warehouse foundation →
WP-2 memory migration → WP-3 write-through + collector → WP-4 run persistence →
WP-5 API v2 + demo guard + fake-LLM → WP-6 frontend foundation → WP-7 Analyze →
WP-8 Library/replay → WP-9 Market Explorer → WP-10 Eval dashboard → WP-11 prod hardening →
WP-12 CI/CD + e2e → WP-13 repo polish + v2.0.0 → WP-14 debt sweep + final review.

Each WP: branch → TDD implement → subagent spec + quality review → fix → merge green.
Frozen contracts stay frozen except where this spec amends them (memory backing store,
API path reorg, README frontmatter).

**External dependency (user):** VPS provisioning, DNS A-record for
`finresearch.prateekmulye.dev`, rotated API keys as deploy-time secrets (needed from WP-11).

## 9. Testing

Offline unit suite stays sacred (mock LLM/tools; no network). Warehouse units run on
aiosqlite; Postgres+pgvector integration tests are marked `db` and run against the compose
service locally and a service container in CI. Frontend: ESLint, tsc, vitest, build gates.
E2E: Playwright smoke against the fake-LLM compose stack. One manual live run against
Ollama Cloud before tagging v2.0.0.

## 10. Out of scope

SDS submission mirror untouched · no auth/user accounts · no paid market-data feeds ·
portfolio site itself not edited (refreshed card copy provided only).

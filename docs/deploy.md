# Deploying FinResearchAI to a VPS

The production stack is `docker-compose.prod.yml`: **Caddy** (auto-HTTPS edge,
serves the built SPA, proxies `/api/*` + `/healthz`) → **app** (FastAPI +
LangGraph, runs Alembic migrations on boot) → **db** (Postgres 16 + pgvector).
Only Caddy publishes host ports; app and db stay on the internal network.

## 1. DNS

Create an **A record** for your domain (e.g. `finresearch.prateekmulye.dev`)
pointing at the VPS's public IPv4 (add AAAA if you have IPv6). Caddy provisions
the Let's Encrypt certificate automatically on first request — DNS must resolve
to the box *before* you start the stack, and ports **80 and 443** must be open
in the VPS firewall.

## 2. Install Docker

On a fresh Ubuntu/Debian VPS:

```bash
curl -fsSL https://get.docker.com | sh
```

Verify with `docker compose version` (v2 with the compose plugin is required).

## 3. Clone and configure

```bash
git clone https://github.com/<you>/FinResearchAI.git
cd FinResearchAI
cp .env.example .env
```

Edit `.env`. Every variable the prod stack reads:

| Variable            | Required | Purpose |
|---------------------|----------|---------|
| `CADDY_DOMAIN`      | yes (prod) | Domain Caddy serves with auto-HTTPS (e.g. `finresearch.prateekmulye.dev`). Unset → plain `:80`, local testing only. |
| `POSTGRES_PASSWORD` | **yes**  | Password for the in-stack Postgres. No default — compose refuses to start without it. Generate: `openssl rand -base64 24`. |
| `OLLAMA_API_KEY`    | yes      | Ollama Cloud key (LLM backbone). |
| `FIRECRAWL_API_KEY` | yes      | Firecrawl key (news analyst web research). |
| `ADMIN_TOKEN`       | recommended | `X-Admin-Token` header bypassing rate/daily-demo limits. Generate: `openssl rand -hex 24`. |
| `APP_FAKE_LLM`      | no (default `0`) | `1` = deterministic offline demo LLM. Leave `0` in production. |

Everything else (`TRUST_PROXY=1`, `COLLECTOR_ENABLED=1`, `DATABASE_URL`,
`ALLOWED_ORIGINS=https://$CADDY_DOMAIN`, `RUNS_DIR`) is wired inside
`docker-compose.prod.yml` — don't set those in `.env`.

> **Secrets hygiene — do this before going live:**
> - **Rotate/revoke any Ollama and Firecrawl keys that were ever used in
>   development or committed anywhere.** Issue fresh keys for the deployment.
> - Use a **strong random `POSTGRES_PASSWORD`** (it's embedded in the app's
>   `DATABASE_URL`).
> - Set a **strong random `ADMIN_TOKEN`** — anyone holding it bypasses every
>   rate limit and demo quota.
> - `.env` is gitignored; keep it that way. `chmod 600 .env`.

## 4. First start

```bash
docker compose -f docker-compose.prod.yml up -d --build
```

The first build takes a few minutes: it `npm ci && npm run build`s the SPA,
installs the Python runtime, and bakes the fastembed BGE-small model into the
image so first-search latency is flat. On boot the app container runs
`alembic upgrade head` (retrying while Postgres finishes initializing), then
starts uvicorn; Caddy only starts routing once the app's `/healthz` is green.

First-run checks:

```bash
docker compose -f docker-compose.prod.yml ps          # all three Up, app (healthy)
curl -I https://finresearch.prateekmulye.dev/         # 200, security headers
curl https://finresearch.prateekmulye.dev/healthz     # {"status":"ok"}
docker compose -f docker-compose.prod.yml logs app | head -30
#   -> "entrypoint: migrations up to date", watchlist seeded, collector started
```

Then open the site, run an analysis, and confirm it appears under the Library.

## 5. Updating

```bash
git pull
docker compose -f docker-compose.prod.yml up -d --build
```

Rebuilds the images and recreates only what changed. Certificates and ACME
account state live in the `caddy_data` volume and survive rebuilds. Migrations
re-run automatically (no-op when already at head).

## 6. Backups

All durable state is in named volumes — back up `pgdata_prod` (runs, market
data, news + embeddings, verdict cache) at minimum:

```bash
docker compose -f docker-compose.prod.yml exec -T db \
  pg_dump -U finresearch -Fc finresearch > finresearch-$(date +%F).dump
```

Cron that daily and ship the dump off-box. `app_runs` (JSONL traces) and
`caddy_data` (certs — Caddy reissues if lost) are nice-to-have, not critical.

## Local stack testing (no domain)

```bash
POSTGRES_PASSWORD=test APP_FAKE_LLM=1 \
  docker compose -f docker-compose.prod.yml up -d --build
# Caddy falls back to :80 -> http://localhost/
```

# Deploying FinResearchAI to a Hugging Face Docker Space

This service ships as a **Docker SDK** Space, replacing the old Gradio SDK Space.

## 1. Space README frontmatter

When creating/updating the Space, the repo root `README.md` MUST begin with this
YAML frontmatter so HF builds the Dockerfile (NOT a Gradio app):

```yaml
---
title: FinResearchAI
emoji: 📈
colorFrom: blue
colorTo: indigo
sdk: docker
app_port: 7860
pinned: false
---
```

- `sdk: docker` — build from the repo `Dockerfile` (was `sdk: gradio`).
- `app_port: 7860` — must match the `EXPOSE`/`--port` in the Dockerfile.

## 2. Secrets (Space Settings → Variables and secrets)

Set as **Secrets** (never commit): `OLLAMA_API_KEY`, `FIRECRAWL_API_KEY`.
Optional **Variables**: `ALLOWED_ORIGINS` (comma-separated; defaults to `*`),
`REDIS_URL` (enables the shared rate-limit backend; omit for in-memory),
`RUNS_DIR` (defaults to `/app/runs`).

## 3. Frontend

The Space serves the JSON API. The thin client (`web/index.html`) can be:
- served from the same container by mounting it as a static route (future enhancement), or
- opened locally / hosted on GitHub Pages pointing `API` at the Space URL.
CORS defaults to `*`, so a separately-hosted page can call the Space directly.

## 4. Resource notes

- Single uvicorn worker keeps the in-memory rate limiter coherent. To scale
  beyond one replica, set `REDIS_URL` so the limiter is shared, then raise workers.
- A Docker Space is heavier than a Gradio SDK Space — validate the free-tier
  CPU/RAM limits build and boot within the timeout before relying on it.

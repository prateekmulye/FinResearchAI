"""FastAPI app for FinResearchAI — API v2 (WP-5): everything under /api.

Endpoints:
  POST /api/analyze              -> EventSourceResponse streaming the graph run as SSE.
  GET  /api/library              -> finished/running runs, newest first (Research Library).
  GET  /api/runs/{run_id}        -> full run detail + replay events (warehouse, JSONL fallback).
  GET  /api/market/...           -> instruments / prices / fundamentals / news reads.
  GET  /api/search               -> semantic (pgvector) / keyword search over news + runs.
  GET  /api/eval/results         -> persisted debate A/B eval results.
  GET  /healthz                  -> liveness probe (stays at root).

The pre-v2 root routes (POST /analyze, GET /runs/{id}) are REMOVED — we own the
only client (web/index.html), which now calls /api/analyze.

Cross-cutting: CORS (open by default; tighten via ALLOWED_ORIGINS), a per-minute
rate limiter (in-memory default, optional Redis seam) on the analyze route, and
input validation via AnalyzeRequest. The limiter and runs dir are app-scoped on
``app.state`` so the routers share them without module globals.
"""
from __future__ import annotations

import logging
import os
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from src.api.demo_guard import DailyQuotaExceeded, daily_quota_handler
from src.api.lifespan import lifespan
from src.api.ratelimit import get_rate_limiter
from src.api.routes import analyze as analyze_routes
from src.api.routes import eval_results as eval_results_routes
from src.api.routes import library as library_routes
from src.api.routes import market as market_routes
from src.api.routes import quota as quota_routes
from src.api.routes import search as search_routes


def create_app(
    *,
    rate_limit: int = 5,
    rate_window_s: int = 3600,
    runs_dir: str | None = None,
    allowed_origins: list[str] | None = None,
) -> FastAPI:
    # Container observability (WP-11): uvicorn configures only its own loggers,
    # so without a root handler the app's INFO lines (watchlist seeding,
    # "collector started") never reach `docker logs`. basicConfig is a no-op
    # when a root handler already exists (pytest, dev reloaders, embedders).
    logging.basicConfig(
        level=os.getenv("LOG_LEVEL", "INFO").upper(),
        format="%(levelname)s [%(name)s] %(message)s",
    )

    # Lifespan (WP-3): watchlist seeding + the gated collector; degrades on any
    # failure so it can never affect startup — see src/api/lifespan.py.
    app = FastAPI(title="FinResearchAI API", version="0.2.0", lifespan=lifespan)

    origins = allowed_origins or [
        o.strip() for o in os.getenv("ALLOWED_ORIGINS", "*").split(",") if o.strip()
    ]
    app.add_middleware(
        CORSMiddleware,
        allow_origins=origins or ["*"],
        allow_credentials=False,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    app.state.limiter = get_rate_limiter(limit=rate_limit, window_s=rate_window_s)
    app.state.runs_path = Path(runs_dir or os.getenv("RUNS_DIR", "runs"))

    @app.get("/healthz")
    async def healthz() -> dict[str, str]:
        return {"status": "ok"}

    app.include_router(analyze_routes.router, prefix="/api")
    app.include_router(library_routes.router, prefix="/api")
    app.include_router(market_routes.router, prefix="/api/market")
    app.include_router(eval_results_routes.router, prefix="/api/eval")
    app.include_router(quota_routes.router, prefix="/api")
    app.include_router(search_routes.router, prefix="/api")

    # Daily demo caps render as a structured 429 the UI can act on.
    app.add_exception_handler(DailyQuotaExceeded, daily_quota_handler)

    return app


app = create_app()

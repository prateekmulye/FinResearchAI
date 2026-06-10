"""FastAPI app for FinResearchAI: streaming analysis, health, and run-trace lookup.

Endpoints:
  POST /analyze        -> EventSourceResponse streaming the graph run as SSE.
  GET  /healthz        -> liveness probe.
  GET  /runs/{run_id}  -> the JSONL trace written by RunRecorder, as JSON.

Cross-cutting: CORS (open by default; tighten via ALLOWED_ORIGINS), a rate limiter
(in-memory default, optional Redis seam), and input validation via AnalyzeRequest.
"""
from __future__ import annotations

import json
import os
from pathlib import Path

from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from sse_starlette import EventSourceResponse

from src.api.lifespan import lifespan
from src.api.ratelimit import get_rate_limiter
from src.api.schemas import AnalyzeRequest
from src.api.stream import analyze_event_stream


def _trust_proxy() -> bool:
    return os.getenv("TRUST_PROXY", "").lower() in {"1", "true", "yes"}


def _client_key(request: Request) -> str:
    # X-Forwarded-For is client-spoofable, so only honor it when TRUST_PROXY is set
    # (i.e. we are knowingly behind a trusted proxy such as the HF Spaces edge). When
    # trusted, take the LAST hop the proxy appended, not the client-controlled first.
    # Otherwise key on the real socket peer so the limiter can't be trivially bypassed.
    if _trust_proxy():
        fwd = request.headers.get("x-forwarded-for")
        if fwd:
            hops = [h.strip() for h in fwd.split(",") if h.strip()]
            if hops:
                return hops[-1]
    return request.client.host if request.client else "unknown"


def create_app(
    *,
    rate_limit: int = 5,
    rate_window_s: int = 3600,
    runs_dir: str | None = None,
    allowed_origins: list[str] | None = None,
) -> FastAPI:
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

    limiter = get_rate_limiter(limit=rate_limit, window_s=rate_window_s)
    runs_path = Path(runs_dir or os.getenv("RUNS_DIR", "runs"))

    @app.get("/healthz")
    async def healthz() -> dict[str, str]:
        return {"status": "ok"}

    @app.post("/analyze")
    async def analyze(req: AnalyzeRequest, request: Request):
        if not limiter.allow(_client_key(request)):
            raise HTTPException(status_code=429, detail="rate limit exceeded")
        generator = analyze_event_stream(
            ticker=req.ticker,
            investor_mode=req.investor_mode,
            debate_mode=req.debate_mode,
            runs_dir=str(runs_path),
        )
        return EventSourceResponse(generator, ping=15)

    @app.get("/runs/{run_id}")
    async def get_run(run_id: str) -> dict:
        # Guard against path traversal: run_ids are hex tokens.
        if not run_id.replace("-", "").isalnum():
            raise HTTPException(status_code=400, detail="invalid run_id")
        trace = runs_path / f"{run_id}.jsonl"
        if not trace.exists():
            raise HTTPException(status_code=404, detail="run not found")
        events = [
            json.loads(line)
            for line in trace.read_text(encoding="utf-8").splitlines()
            if line.strip()
        ]
        return {"run_id": run_id, "events": events}

    return app


app = create_app()

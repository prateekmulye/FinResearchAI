"""POST /api/analyze — the SSE analysis stream (moved verbatim from main.py).

Event names/payloads are unchanged from the pre-WP-5 root route; only the path
moved. The per-minute limiter and runs dir are app-scoped (``app.state``), set
by ``create_app``.
"""
from __future__ import annotations

from fastapi import APIRouter, HTTPException, Request
from sse_starlette import EventSourceResponse

from src.api.client_ip import client_key
from src.api.schemas import AnalyzeRequest
from src.api.stream import analyze_event_stream

router = APIRouter()


@router.post("/analyze")
async def analyze(req: AnalyzeRequest, request: Request):
    if not request.app.state.limiter.allow(client_key(request)):
        raise HTTPException(status_code=429, detail="rate limit exceeded")
    generator = analyze_event_stream(
        ticker=req.ticker,
        investor_mode=req.investor_mode,
        debate_mode=req.debate_mode,
        runs_dir=str(request.app.state.runs_path),
    )
    return EventSourceResponse(generator, ping=15)

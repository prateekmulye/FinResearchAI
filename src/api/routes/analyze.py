"""POST /api/analyze — the SSE analysis stream (moved verbatim from main.py).

Event names/payloads are unchanged from the pre-WP-5 root route; only the path
moved. All throttling (admin bypass -> per-hour burst limiter -> daily demo
caps) lives in the ``demo_guard`` dependency, which also delivers the validated
body (so a 422 never consumes quota). The runs dir is app-scoped
(``app.state``), set by ``create_app``.
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, Request
from sse_starlette import EventSourceResponse

from src.api.demo_guard import demo_guard
from src.api.schemas import AnalyzeRequest
from src.api.stream import analyze_event_stream

router = APIRouter()


@router.post("/analyze")
async def analyze(request: Request, req: AnalyzeRequest = Depends(demo_guard)):
    generator = analyze_event_stream(
        ticker=req.ticker,
        investor_mode=req.investor_mode,
        debate_mode=req.debate_mode,
        runs_dir=str(request.app.state.runs_path),
    )
    # send_timeout reaps black-holed clients (TCP peers that stopped reading
    # without closing): the cancelled stream task still persists its run via the
    # shielded finalize in src/api/stream.py.
    return EventSourceResponse(generator, ping=15, send_timeout=60)

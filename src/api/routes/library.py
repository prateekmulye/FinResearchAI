"""Research Library reads (WP-5): GET /api/library and GET /api/runs/{run_id}."""
from __future__ import annotations

import json
import logging
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Request

from src.api.routes.deps import clamp_limit, require_warehouse
from src.api.routes.dto import LibraryResponse, RunDetail, RunSummary, cost_from_metrics
from src.warehouse.db import session_scope, warehouse_enabled
from src.warehouse.models import Run
from src.warehouse.repos import count_runs, get_run, get_run_events, list_runs

_LOG = logging.getLogger(__name__)

router = APIRouter()

RunStatus = Literal["running", "finished", "error", "aborted"]


def _summary(run: Run) -> RunSummary:
    return RunSummary(
        run_id=run.run_id,
        ticker=run.ticker,
        debate_mode=run.debate_mode,
        status=run.status,
        started_at=run.started_at,
        finished_at=run.finished_at,
        final_decision=run.final_decision,
        cost=cost_from_metrics(run.metrics),
    )


@router.get("/library", response_model=LibraryResponse,
            dependencies=[Depends(require_warehouse)])
async def library(
    ticker: str | None = None,
    status: RunStatus | None = None,
    limit: int = 50,
    offset: int = 0,
) -> LibraryResponse:
    """Runs newest-first with a total count; filterable by ticker and status."""
    limit = clamp_limit(limit)
    offset = max(0, offset)
    norm_ticker = ticker.strip().upper() or None if ticker else None
    async with session_scope() as session:
        runs = await list_runs(
            session, ticker=norm_ticker, status=status, limit=limit, offset=offset
        )
        total = await count_runs(session, ticker=norm_ticker, status=status)
    return LibraryResponse(runs=[_summary(r) for r in runs], total=total)


@router.get("/runs/{run_id}", response_model=RunDetail)
async def run_detail(run_id: str, request: Request) -> RunDetail:
    """Full run detail + ordered replay events.

    Source order: warehouse first (run row + run_events); when the warehouse is
    disabled, errors, or doesn't know the run, fall back to the JSONL trace the
    RunRecorder wrote (the pre-WP-5 ``GET /runs/{id}`` behavior, preserved).
    404 only when NEITHER source knows the run_id."""
    # Guard against path traversal: run_ids are hex tokens.
    if not run_id.replace("-", "").isalnum():
        raise HTTPException(status_code=400, detail="invalid run_id")

    if warehouse_enabled():
        try:
            async with session_scope() as session:
                run = await get_run(session, run_id)
                if run is not None:
                    rows = await get_run_events(session, run_id)
                    return RunDetail(
                        run_id=run.run_id,
                        source="warehouse",
                        ticker=run.ticker,
                        debate_mode=run.debate_mode,
                        status=run.status,
                        started_at=run.started_at,
                        finished_at=run.finished_at,
                        final_decision=run.final_decision,
                        report=run.report,
                        metrics=run.metrics,
                        cost=cost_from_metrics(run.metrics),
                        events=[row.event for row in rows],
                    )
        except Exception as exc:  # degraded DB -> try the JSONL trace instead
            _LOG.warning("run_detail: warehouse read failed for %s: %s", run_id, exc)

    trace = request.app.state.runs_path / f"{run_id}.jsonl"
    if not trace.exists():
        raise HTTPException(status_code=404, detail="run not found")
    events = [
        json.loads(line)
        for line in trace.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    return RunDetail(run_id=run_id, source="jsonl", events=events)

"""Eval reads (WP-5): GET /api/eval/results — the persisted debate A/B results."""
from __future__ import annotations

from fastapi import APIRouter, Depends

from src.api.routes.deps import clamp_limit, require_warehouse
from src.api.routes.dto import EvalResultOut, EvalResultsResponse
from src.warehouse.db import session_scope
from src.warehouse.repos import list_eval_results

router = APIRouter(dependencies=[Depends(require_warehouse)])


@router.get("/results", response_model=EvalResultsResponse)
async def eval_results(limit: int = 20) -> EvalResultsResponse:
    """Stored eval runs, newest first."""
    limit = clamp_limit(limit)
    async with session_scope() as session:
        rows = await list_eval_results(session, limit=limit)
        return EvalResultsResponse(
            results=[EvalResultOut.model_validate(r) for r in rows]
        )

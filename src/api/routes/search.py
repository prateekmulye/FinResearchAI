"""Market Explorer search (WP-9): GET /api/search.

Semantic-first with an honest fallback chain:

1. warehouse disabled                      -> 503 (``require_warehouse``)
2. q blank / < 2 chars / > 256 chars       -> 422 (before any DB or model work)
3. PostgreSQL dialect AND embedder usable  -> pgvector cosine ``semantic_search``
4. otherwise                               -> dialect-agnostic ``keyword_search``

Any failure INSIDE the semantic path (transient DB error, dialect surprise)
logs a warning and degrades to keyword — never a 500. ``mode`` in the response
reports which path actually answered. The query embedding goes through the
same warehouse seam + ``asyncio.to_thread`` as the write path (fastembed is
sync CPU work; never block the event loop).
"""
from __future__ import annotations

import asyncio
import logging

from fastapi import APIRouter, Depends, HTTPException

from src.api.routes.deps import clamp_limit, require_warehouse
from src.api.routes.dto import SearchHitOut, SearchResponse
from src.warehouse.db import get_engine, session_scope
from src.warehouse.embeddings import embed_or_none
from src.warehouse.repos import SearchHit, keyword_search, semantic_search

_LOG = logging.getLogger(__name__)

router = APIRouter(dependencies=[Depends(require_warehouse)])

MIN_QUERY_CHARS = 2
MAX_QUERY_CHARS = 256


def _semantic_eligible() -> bool:
    """Cheap pre-check: pgvector cosine search only exists on PostgreSQL.

    Skipping ineligible dialects BEFORE embedding avoids burning model
    inference on a query that could only ever take the keyword path."""
    return get_engine().dialect.name == "postgresql"


@router.get("/search", response_model=SearchResponse)
async def search(q: str = "", limit: int = 20) -> SearchResponse:
    """Search stored news + finished runs; semantic when possible, else keyword."""
    query = q.strip()
    if len(query) < MIN_QUERY_CHARS:
        raise HTTPException(
            status_code=422, detail=f"query too short (min {MIN_QUERY_CHARS} chars)"
        )
    if len(query) > MAX_QUERY_CHARS:
        raise HTTPException(
            status_code=422, detail=f"query too long (max {MAX_QUERY_CHARS} chars)"
        )
    limit = clamp_limit(limit)

    mode = "keyword"
    hits: list[SearchHit] | None = None
    if _semantic_eligible():
        vectors = await asyncio.to_thread(embed_or_none, [query])
        if vectors:  # None -> embedder unavailable/failed -> keyword fallback
            try:
                async with session_scope() as session:
                    hits = await semantic_search(session, vectors[0], limit=limit)
                mode = "semantic"
            except Exception:
                # ANY semantic failure — transient DB error, driver hiccup, or
                # UnsupportedDialectError sneaking past _semantic_eligible —
                # degrades to the keyword path with mode honest, never a 500.
                _LOG.warning(
                    "semantic search failed; falling back to keyword", exc_info=True
                )
                hits = None
    if hits is None:
        async with session_scope() as session:
            hits = await keyword_search(session, query, limit=limit)
    return SearchResponse(
        mode=mode, hits=[SearchHitOut.model_validate(h) for h in hits]
    )

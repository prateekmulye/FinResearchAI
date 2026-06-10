"""Request models and SSE envelope builders for the FinResearchAI API.

Envelope contract (single source of truth):
  Every SSE message is a dict {"event": <name>, "data": <json-string>}.
  The decoded JSON payload always contains {"type": <name>, "run_id": <str>, ...}.
  Event/type names: start | node_start | node_complete | token | error | done.
"""
from __future__ import annotations

import json
import re
from typing import Any, Literal

from pydantic import BaseModel, Field, field_validator

# Strict ticker allowlist (WP-5 hardening): leading alphanumeric, then up to 14
# more of A-Z/0-9/dot/hyphen (covers AAPL, BRK.B, BRK-B, RELIANCE.NS, 0700.HK).
# Applied AFTER strip().upper() normalization, on the analyze body and on every
# /api/market/{ticker} path param — junk never reaches the DB or an LLM.
TICKER_RE = re.compile(r"^[A-Z0-9][A-Z0-9.\-]{0,14}$")

InvestorMode = Literal["Bullish", "Bearish", "Neutral"]


class AnalyzeRequest(BaseModel):
    ticker: str = Field(..., min_length=1, max_length=15)
    investor_mode: InvestorMode = "Neutral"
    debate_mode: Literal["on", "off"] | None = None  # None => use settings default

    @field_validator("ticker", mode="before")
    @classmethod
    def _normalize_ticker(cls, v: Any) -> str:
        if not isinstance(v, str):
            raise ValueError("ticker must be a string")
        v = v.strip().upper()
        if not TICKER_RE.fullmatch(v):
            raise ValueError(f"invalid ticker: {v!r}")
        return v


def sse_event(name: str, payload: dict[str, Any]) -> dict[str, str]:
    """Build one sse-starlette event dict. `data` is a JSON string of the payload."""
    return {"event": name, "data": json.dumps(payload, default=str)}


def start_payload(run_id: str, ticker: str, investor_mode: str) -> dict[str, Any]:
    return {"type": "start", "run_id": run_id, "ticker": ticker, "investor_mode": investor_mode}


def node_start_payload(run_id: str, node: str) -> dict[str, Any]:
    return {"type": "node_start", "run_id": run_id, "node": node}


def node_complete_payload(run_id: str, node: str, delta: dict[str, Any]) -> dict[str, Any]:
    return {"type": "node_complete", "run_id": run_id, "node": node, "delta": delta}


def token_payload(run_id: str, node: str, text: str) -> dict[str, Any]:
    return {"type": "token", "run_id": run_id, "node": node, "text": text}


def error_payload(run_id: str, message: str) -> dict[str, Any]:
    return {"type": "error", "run_id": run_id, "message": message}


def done_payload(
    run_id: str,
    final_report: str,
    final_decision: dict[str, Any] | None,
    run_metrics: list[dict[str, Any]],
) -> dict[str, Any]:
    return {
        "type": "done",
        "run_id": run_id,
        "final_report": final_report,
        "final_decision": final_decision or {},
        "run_metrics": run_metrics,
    }

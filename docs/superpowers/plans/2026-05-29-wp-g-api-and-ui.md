# WP-G: FastAPI Streaming Backend + Thin SSE Frontend + Docker HF Space Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Expose the compiled LangGraph as a production-minded HTTP service. `POST /analyze` streams the run live over Server-Sent Events — one event per node start/complete plus token deltas as agents and debaters speak — terminating in a `done` event carrying the final report, decision, and run metrics. A dependency-light single-file web client renders the stream as it arrives. The whole thing ships as a Docker Hugging Face Space, replacing the legacy Gradio SDK Space.

**Architecture:** WP-G codes against the **frozen contract only** — `build_graph(debate_mode)` from `src/graph.py` and `AgentState` from `src/state.py` (COORDINATION.md §1, §4). It never imports a concrete node. It drives `graph.astream(input, stream_mode=["updates","messages"])`, maps each `(mode, chunk)` tuple to a clean SSE envelope, and wraps the generator in `sse_starlette.EventSourceResponse`. Because it streams the *compiled graph*, it works on today's 12-node STUB graph with zero LLM keys, and automatically benefits when WP-B/D/E/F land real nodes. A small rate limiter sits in front (in-memory by default, optional Redis backend behind a guarded import). `GET /runs/{run_id}` reads the JSONL trace written by Foundation's `RunRecorder`.

**Tech Stack:** Python 3.13, builds on Foundation (`langgraph==1.0.4`, `pydantic==2.12.5`). Adds the `api` optional-deps group: `fastapi==0.136.3`, `uvicorn[standard]==0.48.0`, `sse-starlette==3.4.4`, `httpx==0.28.1`. Tests use FastAPI/Starlette `TestClient` + `httpx.ASGITransport`. Frontend is vanilla JS + HTML (no build step). Deploy: multi-stage `Dockerfile` + HF Space Docker SDK README frontmatter.

---

## Context for the implementer

Read first: `docs/superpowers/plans/COORDINATION.md` (the contract — §4 "API streams the compiled graph", §2 conventions) and `docs/superpowers/plans/2026-05-29-foundation-and-state-contract.md` (format/depth; the `build_graph()` + `AgentState` you code against). Spec reference: `docs/superpowers/specs/2026-05-29-finresearchai-agentic-upgrade-design.md` §5.5 (FastAPI + SSE + Docker HF Space; Redis optional, defaults in-memory).

**You do not touch graph internals.** Your only graph-facing imports are `from src.graph import build_graph` and `from src.state import AgentState`. The stub graph already runs end-to-end and writes 12 `run_metrics` records — that is your test fixture. NO network LLM calls anywhere in this plan's tests.

### Verified library APIs (Context7, 2026-05-29)

**LangGraph 1.0.4 `astream` with a list `stream_mode` (the riskiest part — verified via Context7 + local source probe `langgraph.pregel.Pregel.astream`):**
- When `stream_mode` is a **list**, each yielded item is a **2-tuple `(mode, chunk)`** where `mode` is the string `"updates"` or `"messages"`. This is how you disambiguate modes from one stream. (When `stream_mode` is a single string, the bare `chunk` is yielded with no tuple wrapper — we always pass a list, so we always get tuples.)
- **`"updates"` chunk** = `dict[node_name, state_delta]` — e.g. `{"router": {"resolved_ticker": "AAPL", ...}}`. One key per node that just finished a step. Parallel nodes in one superstep may produce one chunk per node (or a multi-key dict); iterate `.items()` defensively. We treat each `(node, delta)` pair as a **node-complete** event.
- **`"messages"` chunk** = a **2-tuple `(message, metadata)`** where `message` is a `BaseMessage` (typically an `AIMessageChunk` with `.content` token text) and `metadata` is a dict with keys like `langgraph_node`, `langgraph_step`, `langgraph_triggers`. We emit a **token** event carrying `metadata["langgraph_node"]` + `message.content`. The stub graph emits NO messages (no LLM calls), so token events only appear once real nodes land — tests assert the envelope contract, not token presence.
- `astream` is an async generator: `async for mode, chunk in graph.astream(inp, stream_mode=["updates","messages"]): ...`.

**sse-starlette 3.4.4 `EventSourceResponse` (verified via Context7):** constructed with an async generator that **yields dicts** shaped `{"event": "<name>", "data": "<string>", "id": "<optional>"}`. `data` must be a string (we JSON-encode our envelope into it). Constructor accepts `ping=<seconds>` (default 15; keeps the connection alive) and `headers=`. We do NOT use FastAPI's `fastapi.sse.EventSourceResponse` wrapper (that auto-wraps return values); we return `sse_starlette.EventSourceResponse(generator)` directly for full control of the envelope.

**FastAPI 0.136.3 async testing (verified via Context7):** `httpx.AsyncClient(transport=ASGITransport(app=app), base_url="http://test")`. For SSE, stream the body and split on blank lines. We also use `starlette.testclient.TestClient` (sync, context-managed) for the simple `/healthz` and rate-limit cap tests because it runs the full lifespan and is simplest for status-code assertions.

**CORS:** `from fastapi.middleware.cors import CORSMiddleware; app.add_middleware(CORSMiddleware, allow_origins=[...], ...)`.

## File Structure

| File | Responsibility |
|---|---|
| `pyproject.toml` | Fill the `api` optional-deps group with pinned versions (verified above) |
| `src/api/__init__.py` | Package marker |
| `src/api/schemas.py` | Request/response Pydantic models + SSE event envelope builders |
| `src/api/ratelimit.py` | `RateLimiter` protocol; in-memory sliding-window impl + guarded Redis backend seam |
| `src/api/stream.py` | `analyze_event_stream()` async generator: drives `build_graph().astream(...)` → SSE dicts |
| `src/api/main.py` | FastAPI app: `POST /analyze`, `GET /healthz`, `GET /runs/{run_id}`, CORS, rate limiting, validation |
| `web/index.html` | Single-file vanilla-JS client: POST `/analyze`, render the SSE stream live |
| `Dockerfile` | Multi-stage build; runs uvicorn |
| `README-hfspace.md` | HF Spaces "Docker SDK" frontmatter + config notes (replaces Gradio SDK space) |
| `tests/test_api_schemas.py` | Envelope/validation round-trip |
| `tests/test_api_ratelimit.py` | In-memory limiter allow/deny + reset |
| `tests/test_api_stream.py` | `analyze_event_stream` over the STUB graph yields node events ending in `done` |
| `tests/test_api_main.py` | `/healthz`, `/analyze` SSE end-to-end, `/runs/{id}`, 429 after cap, bad-ticker 422 |

---

### Task 1: Pin the `api` optional-dependency group

**Files:**
- Edit: `pyproject.toml`

- [ ] **Step 1: Replace the commented `api` line in `[project.optional-dependencies]`**

In `pyproject.toml`, the Foundation plan left this commented placeholder:
```toml
# api     = ["fastapi>=0.125", "uvicorn>=0.30", "sse-starlette>=2.1", "httpx>=0.27"]
```
Replace that single comment line with a real, pinned group (versions verified via Context7 / PyPI on 2026-05-29):
```toml
api = [
    "fastapi==0.136.3",
    "uvicorn[standard]==0.48.0",
    "sse-starlette==3.4.4",
    "httpx==0.28.1",
]
```

- [ ] **Step 2: Install the group**

Run: `python -m pip install -e ".[api]"`
Expected: installs/confirms fastapi 0.136.3, uvicorn 0.48.0, sse-starlette 3.4.4, httpx 0.28.1 (httpx may already be present at 0.28.1).

- [ ] **Step 3: Verify imports resolve**

Run: `python -c "import fastapi, uvicorn, sse_starlette, httpx; from sse_starlette import EventSourceResponse; print(fastapi.__version__, sse_starlette.__version__, httpx.__version__)"`
Expected: prints `0.136.3 3.4.4 0.28.1`.

- [ ] **Step 4: Commit**

```bash
git add pyproject.toml
git commit -m "build(api): pin fastapi/uvicorn/sse-starlette/httpx api deps"
```

---

### Task 2: API package marker

**Files:**
- Create: `src/api/__init__.py`

- [ ] **Step 1: Create `src/api/__init__.py`** (empty package marker)

```python
```

- [ ] **Step 2: Commit**

```bash
git add src/api/__init__.py
git commit -m "feat(api): add api package marker"
```

---

### Task 3: Request/response schemas + SSE envelope builders

The envelope design (single source of truth for the whole WP): every SSE event is `{"event": <name>, "data": <json-string>}`. The JSON `data` payload always carries `{"type": <name>, "run_id": <str>, ...}`. Event names: `start`, `node_start`, `node_complete`, `token`, `error`, `done`.

**Files:**
- Create: `src/api/schemas.py`
- Test: `tests/test_api_schemas.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_api_schemas.py
import json
import pytest
from pydantic import ValidationError
from src.api.schemas import (
    AnalyzeRequest,
    sse_event,
    start_payload,
    node_start_payload,
    node_complete_payload,
    token_payload,
    error_payload,
    done_payload,
    TICKER_RE,
)


def test_analyze_request_defaults():
    r = AnalyzeRequest(ticker="AAPL")
    assert r.ticker == "AAPL"
    assert r.investor_mode == "Neutral"
    assert r.debate_mode is None  # use settings default


def test_analyze_request_uppercases_and_strips_ticker():
    r = AnalyzeRequest(ticker="  aapl ")
    assert r.ticker == "AAPL"


def test_analyze_request_rejects_bad_ticker():
    with pytest.raises(ValidationError):
        AnalyzeRequest(ticker="; DROP TABLE--")
    with pytest.raises(ValidationError):
        AnalyzeRequest(ticker="")
    with pytest.raises(ValidationError):
        AnalyzeRequest(ticker="A" * 25)


def test_analyze_request_rejects_bad_investor_mode():
    with pytest.raises(ValidationError):
        AnalyzeRequest(ticker="AAPL", investor_mode="YOLO")


def test_analyze_request_allows_dotted_international_ticker():
    assert AnalyzeRequest(ticker="RELIANCE.NS").ticker == "RELIANCE.NS"


def test_ticker_regex_anchored():
    assert TICKER_RE.fullmatch("BRK.B")
    assert not TICKER_RE.fullmatch("AAPL AAPL")


def test_sse_event_shape():
    ev = sse_event("node_complete", {"type": "node_complete", "run_id": "r1", "node": "router"})
    assert ev["event"] == "node_complete"
    payload = json.loads(ev["data"])
    assert payload["node"] == "router"
    assert payload["run_id"] == "r1"


def test_payload_builders_carry_run_id_and_type():
    assert start_payload("r1", "AAPL", "Neutral")["type"] == "start"
    assert node_start_payload("r1", "bull")["node"] == "bull"
    assert node_complete_payload("r1", "router", {"resolved_ticker": "AAPL"})["delta"]["resolved_ticker"] == "AAPL"
    assert token_payload("r1", "bull", "hello")["text"] == "hello"
    assert error_payload("r1", "boom")["message"] == "boom"
    d = done_payload("r1", final_report="# R", final_decision={"action": "HOLD"}, run_metrics=[{"node": "router"}])
    assert d["final_decision"]["action"] == "HOLD"
    assert d["run_metrics"][0]["node"] == "router"


def test_payloads_are_json_serializable():
    # done must survive json.dumps (recorder stores arbitrary deltas)
    d = done_payload("r1", final_report="x", final_decision={"a": 1}, run_metrics=[])
    json.dumps(d)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_api_schemas.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'src.api.schemas'`

- [ ] **Step 3: Write the implementation**

```python
# src/api/schemas.py
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

# Tickers: 1-12 chars of A-Z/0-9, optional .SUFFIX for international (e.g. RELIANCE.NS, BRK.B).
TICKER_RE = re.compile(r"[A-Z0-9]{1,12}(?:\.[A-Z]{1,4})?")

InvestorMode = Literal["Bullish", "Bearish", "Neutral"]


class AnalyzeRequest(BaseModel):
    ticker: str = Field(..., min_length=1, max_length=24)
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
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_api_schemas.py -v`
Expected: PASS (9 tests)

- [ ] **Step 5: Commit**

```bash
git add src/api/schemas.py tests/test_api_schemas.py
git commit -m "feat(api): add request schema + SSE envelope builders"
```

---

### Task 4: Rate limiter (in-memory default + guarded Redis seam)

**Files:**
- Create: `src/api/ratelimit.py`
- Test: `tests/test_api_ratelimit.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_api_ratelimit.py
import time
import pytest
from src.api.ratelimit import InMemoryRateLimiter, get_rate_limiter


def test_allows_up_to_limit_then_denies():
    rl = InMemoryRateLimiter(limit=3, window_s=60)
    assert rl.allow("1.2.3.4") is True
    assert rl.allow("1.2.3.4") is True
    assert rl.allow("1.2.3.4") is True
    assert rl.allow("1.2.3.4") is False  # 4th in-window -> denied


def test_separate_keys_have_separate_budgets():
    rl = InMemoryRateLimiter(limit=1, window_s=60)
    assert rl.allow("a") is True
    assert rl.allow("b") is True
    assert rl.allow("a") is False


def test_window_expiry_resets(monkeypatch):
    rl = InMemoryRateLimiter(limit=1, window_s=10)
    base = [1000.0]
    monkeypatch.setattr("src.api.ratelimit.time.monotonic", lambda: base[0])
    assert rl.allow("a") is True
    assert rl.allow("a") is False
    base[0] += 11.0  # advance past the window
    assert rl.allow("a") is True


def test_get_rate_limiter_defaults_to_in_memory(monkeypatch):
    monkeypatch.delenv("REDIS_URL", raising=False)
    rl = get_rate_limiter(limit=5, window_s=60)
    assert isinstance(rl, InMemoryRateLimiter)


def test_get_rate_limiter_falls_back_when_redis_missing(monkeypatch):
    # REDIS_URL set but the redis package import is forced to fail -> graceful in-memory fallback.
    monkeypatch.setenv("REDIS_URL", "redis://localhost:6379/0")
    import builtins
    real_import = builtins.__import__

    def fake_import(name, *a, **k):
        if name == "redis":
            raise ImportError("no redis")
        return real_import(name, *a, **k)

    monkeypatch.setattr(builtins, "__import__", fake_import)
    rl = get_rate_limiter(limit=5, window_s=60)
    assert isinstance(rl, InMemoryRateLimiter)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_api_ratelimit.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'src.api.ratelimit'`

- [ ] **Step 3: Write the implementation**

```python
# src/api/ratelimit.py
"""Rate limiting with an in-memory default and an optional Redis backend seam.

Default is a per-key sliding-window counter held in process memory (fine for a
single HF Space replica). If REDIS_URL is set AND the `redis` package imports,
a Redis-backed limiter is used so multiple replicas share one budget. The import
is guarded: a missing package or bad URL degrades gracefully to in-memory.
"""
from __future__ import annotations

import os
import time
from collections import defaultdict, deque
from typing import Protocol


class RateLimiter(Protocol):
    def allow(self, key: str) -> bool:
        """Return True if `key` is within budget (and consume one slot), else False."""
        ...


class InMemoryRateLimiter:
    """Sliding-window limiter: at most `limit` hits per `window_s` seconds per key."""

    def __init__(self, limit: int, window_s: int) -> None:
        self.limit = limit
        self.window_s = window_s
        self._hits: dict[str, deque[float]] = defaultdict(deque)

    def allow(self, key: str) -> bool:
        now = time.monotonic()
        cutoff = now - self.window_s
        q = self._hits[key]
        while q and q[0] < cutoff:
            q.popleft()
        if len(q) >= self.limit:
            return False
        q.append(now)
        return True


class RedisRateLimiter:
    """Redis-backed fixed-window counter (INCR + EXPIRE). Shared across replicas."""

    def __init__(self, client, limit: int, window_s: int) -> None:
        self._client = client
        self.limit = limit
        self.window_s = window_s

    def allow(self, key: str) -> bool:
        bucket = int(time.time() // self.window_s)
        rkey = f"rl:{key}:{bucket}"
        try:
            count = self._client.incr(rkey)
            if count == 1:
                self._client.expire(rkey, self.window_s)
            return count <= self.limit
        except Exception:
            # Never let a Redis hiccup take down the API: fail open at the edge.
            return True


def get_rate_limiter(limit: int, window_s: int) -> RateLimiter:
    """Return a Redis limiter if REDIS_URL + redis package are available, else in-memory."""
    url = os.getenv("REDIS_URL")
    if url:
        try:
            import redis  # guarded import: optional dependency

            client = redis.Redis.from_url(url, decode_responses=True)
            client.ping()
            return RedisRateLimiter(client, limit=limit, window_s=window_s)
        except Exception:
            pass  # missing package / unreachable server -> degrade to in-memory
    return InMemoryRateLimiter(limit=limit, window_s=window_s)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_api_ratelimit.py -v`
Expected: PASS (5 tests)

- [ ] **Step 5: Commit**

```bash
git add src/api/ratelimit.py tests/test_api_ratelimit.py
git commit -m "feat(api): add in-memory rate limiter with guarded Redis seam"
```

---

### Task 5: The SSE streaming generator (drives build_graph().astream)

This is the heart of WP-G. It maps LangGraph's `(mode, chunk)` tuples to SSE envelopes. See "Verified library APIs" above for the exact chunk shapes.

**Files:**
- Create: `src/api/stream.py`
- Test: `tests/test_api_stream.py`

- [ ] **Step 1: Write the failing test** (runs against the STUB graph — no LLM keys, no network)

```python
# tests/test_api_stream.py
import json
import pytest
from src.api.stream import analyze_event_stream, _node_from_messages_meta


async def _collect(gen):
    return [ev async for ev in gen]


@pytest.mark.asyncio
async def test_stream_starts_and_ends_with_done():
    events = await _collect(
        analyze_event_stream(ticker="AAPL", investor_mode="Neutral", debate_mode="on", run_id="run-x")
    )
    names = [e["event"] for e in events]
    assert names[0] == "start"
    assert names[-1] == "done"


@pytest.mark.asyncio
async def test_stream_emits_node_complete_for_every_stub_node():
    events = await _collect(
        analyze_event_stream(ticker="AAPL", investor_mode="Neutral", debate_mode="on", run_id="run-y")
    )
    completed = {
        json.loads(e["data"])["node"]
        for e in events
        if e["event"] == "node_complete"
    }
    # The 12-node stub graph: every node reports completion.
    assert {"router", "news_analyst", "fundamentals_analyst", "technicals_analyst",
            "bull", "bear", "facilitator", "trader",
            "risk_conservative", "risk_aggressive", "risk_arbiter", "reporter"} <= completed


@pytest.mark.asyncio
async def test_done_event_carries_report_decision_and_metrics():
    events = await _collect(
        analyze_event_stream(ticker="AAPL", investor_mode="Neutral", debate_mode="on", run_id="run-z")
    )
    done = json.loads(events[-1]["data"])
    assert done["type"] == "done"
    assert done["run_id"] == "run-z"
    assert isinstance(done["final_report"], str) and done["final_report"]
    assert done["final_decision"]["action"] in {"BUY", "SELL", "HOLD"}
    assert len(done["run_metrics"]) == 12  # stub appends one metric per node


@pytest.mark.asyncio
async def test_every_event_data_is_json_with_run_id():
    events = await _collect(
        analyze_event_stream(ticker="AAPL", investor_mode="Neutral", debate_mode="on", run_id="run-q")
    )
    for e in events:
        payload = json.loads(e["data"])
        assert payload["run_id"] == "run-q"
        assert payload["type"] == e["event"]


@pytest.mark.asyncio
async def test_stream_emits_error_event_on_graph_failure(monkeypatch):
    import src.api.stream as stream_mod

    def boom(*a, **k):
        raise RuntimeError("kaboom")

    monkeypatch.setattr(stream_mod, "build_graph", boom)
    events = await _collect(
        analyze_event_stream(ticker="AAPL", investor_mode="Neutral", debate_mode="on", run_id="run-e")
    )
    assert events[-1]["event"] == "error"
    assert "kaboom" in json.loads(events[-1]["data"])["message"]


def test_node_from_messages_meta_reads_langgraph_node():
    assert _node_from_messages_meta({"langgraph_node": "bull"}) == "bull"
    assert _node_from_messages_meta({}) == "unknown"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_api_stream.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'src.api.stream'`

- [ ] **Step 3: Write the implementation**

```python
# src/api/stream.py
"""Async SSE generator that runs the compiled LangGraph and maps its stream to events.

We drive `build_graph(debate_mode).astream(input, stream_mode=["updates","messages"])`.
Because stream_mode is a LIST, LangGraph yields 2-tuples `(mode, chunk)` (verified
against langgraph 1.0.4):

  mode == "updates":  chunk is dict[node_name, state_delta]  -> node_start + node_complete
  mode == "messages": chunk is (message, metadata)           -> token (metadata.langgraph_node)

The stub graph emits no "messages" chunks (no LLM calls); token events appear once
real nodes land. The terminal `done` event carries final_report + final_decision +
run_metrics accumulated from the last "updates" deltas.
"""
from __future__ import annotations

import uuid
from collections.abc import AsyncIterator
from typing import Any

from src.api.schemas import (
    done_payload,
    error_payload,
    node_complete_payload,
    node_start_payload,
    sse_event,
    start_payload,
    token_payload,
)
from src.graph import build_graph


def _node_from_messages_meta(metadata: dict[str, Any]) -> str:
    return metadata.get("langgraph_node", "unknown")


async def analyze_event_stream(
    *,
    ticker: str,
    investor_mode: str,
    debate_mode: str | None,
    run_id: str | None = None,
) -> AsyncIterator[dict[str, str]]:
    """Yield sse-starlette event dicts for one analysis run over the compiled graph."""
    run_id = run_id or uuid.uuid4().hex[:12]
    yield sse_event("start", start_payload(run_id, ticker, investor_mode))

    final_state: dict[str, Any] = {}
    seen_started: set[str] = set()
    try:
        graph = build_graph(debate_mode)
        inputs = {"ticker": ticker, "investor_mode": investor_mode, "run_id": run_id}

        async for mode, chunk in graph.astream(inputs, stream_mode=["updates", "messages"]):
            if mode == "updates":
                # chunk: {node_name: state_delta, ...}
                for node, delta in (chunk or {}).items():
                    if node not in seen_started:
                        seen_started.add(node)
                        yield sse_event("node_start", node_start_payload(run_id, node))
                    yield sse_event(
                        "node_complete", node_complete_payload(run_id, node, delta or {})
                    )
                    if isinstance(delta, dict):
                        final_state.update(delta)
            elif mode == "messages":
                # chunk: (message, metadata)
                message, metadata = chunk
                text = getattr(message, "content", "") or ""
                if text:
                    yield sse_event(
                        "token", token_payload(run_id, _node_from_messages_meta(metadata), text)
                    )

        decision = final_state.get("final_decision") or {}
        report = final_state.get("final_report", "")
        metrics = final_state.get("run_metrics", []) or []
        yield sse_event(
            "done",
            done_payload(run_id, final_report=report, final_decision=decision, run_metrics=metrics),
        )
    except Exception as exc:  # never leak a 500 mid-stream: emit a clean error event
        yield sse_event("error", error_payload(run_id, str(exc)))
```

Note on `final_state` accumulation: `astream(stream_mode="updates")` yields per-node *deltas*, not the full state. We shallow-merge deltas as they arrive, so `final_state["run_metrics"]` ends up holding the LAST delta's metrics list — NOT the reducer-accumulated full list. To get the full accumulated `run_metrics` and `final_report`/`final_decision` reliably, we rely on the fact that `risk_arbiter` writes `final_decision`, `reporter` writes `final_report`, and each appears in its own delta (so the shallow-merge captures them). For `run_metrics`, the stub test asserts 12 entries — achieve this by also requesting the accumulated values: see Step 4.

- [ ] **Step 4: Add the accumulated `values` capture so `run_metrics` is complete**

The `"updates"` stream gives per-node deltas; the reducer-accumulated list lives in the graph's `"values"` stream. Add `"values"` to the stream mode and keep the LAST values snapshot as the authoritative final state, while still emitting node events from `"updates"`. Edit `src/api/stream.py`:

Change the `astream` call and the loop:

```python
        async for mode, chunk in graph.astream(
            inputs, stream_mode=["updates", "messages", "values"]
        ):
            if mode == "updates":
                for node, delta in (chunk or {}).items():
                    if node not in seen_started:
                        seen_started.add(node)
                        yield sse_event("node_start", node_start_payload(run_id, node))
                    yield sse_event(
                        "node_complete", node_complete_payload(run_id, node, delta or {})
                    )
            elif mode == "messages":
                message, metadata = chunk
                text = getattr(message, "content", "") or ""
                if text:
                    yield sse_event(
                        "token", token_payload(run_id, _node_from_messages_meta(metadata), text)
                    )
            elif mode == "values":
                # full reducer-accumulated state snapshot; keep the latest.
                final_state = chunk or final_state
```

Rationale (documented for reviewers): `"values"` chunks are the **full accumulated state** after each superstep (the `operator.add` reducer on `run_metrics` and `merge_named_reports` on `analyst_reports` are applied here). The final `"values"` snapshot therefore holds all 12 `run_metrics` entries and the final report/decision. `"updates"` remains the source for live per-node events. This satisfies `test_done_event_carries_report_decision_and_metrics` (12 metrics).

- [ ] **Step 5: Run test to verify it passes**

Run: `python -m pytest tests/test_api_stream.py -v`
Expected: PASS (6 tests). If `run_metrics` length is wrong, confirm `"values"` is in the stream_mode list and the `elif mode == "values"` branch assigns `final_state`.

- [ ] **Step 6: Commit**

```bash
git add src/api/stream.py tests/test_api_stream.py
git commit -m "feat(api): add SSE generator mapping astream updates/messages/values to events"
```

---

### Task 6: FastAPI app — endpoints, CORS, validation, rate limiting

**Files:**
- Create: `src/api/main.py`
- Test: `tests/test_api_main.py`

- [ ] **Step 1: Write the failing test** (all against the STUB graph — no LLM keys)

```python
# tests/test_api_main.py
import json
import pytest
from starlette.testclient import TestClient
from src.api.main import create_app


def _parse_sse(raw: str):
    """Parse an SSE text body into a list of (event, json_payload) tuples."""
    events = []
    for block in raw.strip().split("\n\n"):
        ev_name, data_lines = None, []
        for line in block.splitlines():
            if line.startswith("event:"):
                ev_name = line[len("event:"):].strip()
            elif line.startswith("data:"):
                data_lines.append(line[len("data:"):].strip())
        if ev_name and data_lines:
            events.append((ev_name, json.loads("".join(data_lines))))
    return events


def test_healthz():
    with TestClient(create_app()) as client:
        resp = client.get("/healthz")
        assert resp.status_code == 200
        assert resp.json()["status"] == "ok"


def test_analyze_streams_events_ending_in_done():
    with TestClient(create_app()) as client:
        resp = client.post("/analyze", json={"ticker": "AAPL", "investor_mode": "Neutral"})
        assert resp.status_code == 200
        assert resp.headers["content-type"].startswith("text/event-stream")
        events = _parse_sse(resp.text)
        names = [e[0] for e in events]
        assert names[0] == "start"
        assert names[-1] == "done"
        assert "node_complete" in names
        done = events[-1][1]
        assert done["final_decision"]["action"] in {"BUY", "SELL", "HOLD"}


def test_analyze_rejects_bad_ticker_with_422():
    with TestClient(create_app()) as client:
        resp = client.post("/analyze", json={"ticker": "; DROP TABLE--"})
        assert resp.status_code == 422


def test_rate_limit_returns_429_after_cap():
    # cap of 2 requests for the test app
    with TestClient(create_app(rate_limit=2, rate_window_s=3600)) as client:
        body = {"ticker": "AAPL"}
        assert client.post("/analyze", json=body).status_code == 200
        assert client.post("/analyze", json=body).status_code == 200
        resp = client.post("/analyze", json=body)
        assert resp.status_code == 429


def test_runs_endpoint_reads_jsonl_trace(tmp_path, monkeypatch):
    # Write a fake trace where RunRecorder would, then read it back.
    from src.obs.recorder import RunRecorder
    rec = RunRecorder(runs_dir=str(tmp_path))
    rec.record("router", "metric", {"node": "router"})
    rec.flush()
    monkeypatch.setenv("RUNS_DIR", str(tmp_path))
    with TestClient(create_app(runs_dir=str(tmp_path))) as client:
        resp = client.get(f"/runs/{rec.run_id}")
        assert resp.status_code == 200
        body = resp.json()
        assert body["run_id"] == rec.run_id
        assert body["events"][0]["node"] == "router"


def test_runs_endpoint_404_for_unknown_id(tmp_path):
    with TestClient(create_app(runs_dir=str(tmp_path))) as client:
        assert client.get("/runs/does-not-exist").status_code == 404


def test_cors_headers_present():
    with TestClient(create_app()) as client:
        resp = client.get("/healthz", headers={"Origin": "http://example.com"})
        assert resp.headers.get("access-control-allow-origin") == "*"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_api_main.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'src.api.main'`

- [ ] **Step 3: Write the implementation**

```python
# src/api/main.py
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

from src.api.ratelimit import get_rate_limiter
from src.api.schemas import AnalyzeRequest
from src.api.stream import analyze_event_stream


def _client_key(request: Request) -> str:
    # Honor a proxy hop (HF Spaces sits behind a proxy), else the socket peer.
    fwd = request.headers.get("x-forwarded-for")
    if fwd:
        return fwd.split(",")[0].strip()
    return request.client.host if request.client else "unknown"


def create_app(
    *,
    rate_limit: int = 5,
    rate_window_s: int = 3600,
    runs_dir: str | None = None,
    allowed_origins: list[str] | None = None,
) -> FastAPI:
    app = FastAPI(title="FinResearchAI API", version="0.2.0")

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
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_api_main.py -v`
Expected: PASS (7 tests). The 429 test relies on `create_app(rate_limit=2)` building a fresh limiter per app instance.

- [ ] **Step 5: Run the FULL suite to confirm no regression**

Run: `python -m pytest -q`
Expected: all Foundation tests + the four new `test_api_*` modules PASS.

- [ ] **Step 6: Smoke-run the server locally (manual confirmation, no LLM keys needed)**

Run (background): `python -m uvicorn src.api.main:app --port 8000 &`
Then: `curl -s http://localhost:8000/healthz` → `{"status":"ok"}`
Then: `curl -sN -X POST http://localhost:8000/analyze -H 'Content-Type: application/json' -d '{"ticker":"AAPL"}'`
Expected: a stream of `event: start` … `event: node_complete` … ending in `event: done` with the stub report. Kill the server afterward (`kill %1`).

- [ ] **Step 7: Commit**

```bash
git add src/api/main.py tests/test_api_main.py
git commit -m "feat(api): add FastAPI app (analyze SSE, healthz, runs, CORS, rate limit)"
```

---

### Task 7: Thin SSE frontend (single-file vanilla JS)

The browser `EventSource` API only does GET, so we use `fetch` + a streaming `ReadableStream` reader to POST and parse SSE manually. No build step, no dependencies.

**Files:**
- Create: `web/index.html`

- [ ] **Step 1: Write `web/index.html`**

```html
<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>FinResearchAI</title>
  <style>
    :root { color-scheme: dark; }
    body { font-family: system-ui, sans-serif; max-width: 820px; margin: 2rem auto; padding: 0 1rem;
           background: #0f1115; color: #e6e6e6; }
    h1 { font-size: 1.4rem; }
    form { display: flex; gap: .5rem; flex-wrap: wrap; margin-bottom: 1rem; }
    input, select, button { padding: .5rem .6rem; border-radius: 6px; border: 1px solid #333;
                            background: #1a1d24; color: #e6e6e6; font-size: .95rem; }
    button { cursor: pointer; background: #2d6cdf; border-color: #2d6cdf; }
    button:disabled { opacity: .5; cursor: default; }
    #steps { list-style: none; padding: 0; margin: 1rem 0; }
    #steps li { padding: .4rem .6rem; border-left: 3px solid #2d6cdf; margin-bottom: .3rem;
                background: #161922; border-radius: 0 6px 6px 0; }
    #steps li.done { border-left-color: #3fb950; }
    #report { white-space: pre-wrap; background: #161922; padding: 1rem; border-radius: 8px; }
    .err { color: #f85149; }
    .meta { color: #8b949e; font-size: .85rem; }
  </style>
</head>
<body>
  <h1>FinResearchAI — live analysis</h1>
  <form id="f">
    <input id="ticker" placeholder="Ticker (e.g. AAPL)" value="AAPL" required />
    <select id="mode">
      <option>Neutral</option><option>Bullish</option><option>Bearish</option>
    </select>
    <select id="debate">
      <option value="">debate: default</option>
      <option value="on">debate: on</option>
      <option value="off">debate: off</option>
    </select>
    <button id="go" type="submit">Analyze</button>
  </form>

  <ul id="steps"></ul>
  <div id="tokens" class="meta"></div>
  <h2 id="reportHead" style="display:none">Report</h2>
  <pre id="report"></pre>

  <script>
    const API = (location.origin && location.origin !== "null") ? location.origin : "http://localhost:8000";
    const f = document.getElementById("f");
    const steps = document.getElementById("steps");
    const report = document.getElementById("report");
    const reportHead = document.getElementById("reportHead");
    const tokens = document.getElementById("tokens");
    const go = document.getElementById("go");

    function reset() { steps.innerHTML = ""; report.textContent = ""; tokens.textContent = "";
                       reportHead.style.display = "none"; }
    function addStep(node, cls) {
      const li = document.createElement("li");
      li.id = "step-" + node; li.textContent = node; if (cls) li.className = cls;
      steps.appendChild(li); return li;
    }

    // Minimal SSE frame parser over a fetch body stream.
    function handleEvent(name, dataStr) {
      let data; try { data = JSON.parse(dataStr); } catch { return; }
      if (name === "node_start") { if (!document.getElementById("step-" + data.node)) addStep(data.node); }
      else if (name === "node_complete") {
        const el = document.getElementById("step-" + data.node) || addStep(data.node);
        el.className = "done";
      }
      else if (name === "token") { tokens.textContent += data.text; }
      else if (name === "done") {
        reportHead.style.display = "block";
        report.textContent = data.final_report || "(no report)";
        const d = data.final_decision || {};
        addStep(`DONE — ${d.action || "?"} (score ${d.score ?? "?"})`, "done");
        go.disabled = false;
      }
      else if (name === "error") {
        const li = addStep("error: " + (data.message || "unknown")); li.className = "err";
        go.disabled = false;
      }
    }

    f.addEventListener("submit", async (e) => {
      e.preventDefault(); reset(); go.disabled = true;
      const payload = {
        ticker: document.getElementById("ticker").value,
        investor_mode: document.getElementById("mode").value,
      };
      const dm = document.getElementById("debate").value; if (dm) payload.debate_mode = dm;

      let resp;
      try {
        resp = await fetch(API + "/analyze", {
          method: "POST", headers: { "Content-Type": "application/json" },
          body: JSON.stringify(payload),
        });
      } catch (err) { addStep("network error: " + err, ).className = "err"; go.disabled = false; return; }

      if (resp.status === 429) { addStep("rate limited — try later").className = "err"; go.disabled = false; return; }
      if (!resp.ok) { addStep("error " + resp.status).className = "err"; go.disabled = false; return; }

      const reader = resp.body.getReader();
      const decoder = new TextDecoder();
      let buf = "";
      while (true) {
        const { value, done } = await reader.read();
        if (done) break;
        buf += decoder.decode(value, { stream: true });
        let idx;
        while ((idx = buf.indexOf("\n\n")) !== -1) {
          const frame = buf.slice(0, idx); buf = buf.slice(idx + 2);
          let ev = "message"; const dataLines = [];
          for (const line of frame.split("\n")) {
            if (line.startsWith("event:")) ev = line.slice(6).trim();
            else if (line.startsWith("data:")) dataLines.push(line.slice(5).trim());
          }
          if (dataLines.length) handleEvent(ev, dataLines.join(""));
        }
      }
      go.disabled = false;
    });
  </script>
</body>
</html>
```

- [ ] **Step 2: Manually verify against the running server**

Start the server (Task 6 Step 6), open `web/index.html` in a browser (or serve via `python -m http.server` from `web/`), click Analyze. You should see each of the 12 stub nodes appear and turn green, then the stub report render and a `DONE — HOLD (score 50)` row. (Cross-origin works because CORS defaults to `*`.)

- [ ] **Step 3: Commit**

```bash
git add web/index.html
git commit -m "feat(web): add dependency-light vanilla-JS SSE frontend"
```

---

### Task 8: Multi-stage Dockerfile

**Files:**
- Create: `Dockerfile`
- Create: `.dockerignore`

- [ ] **Step 1: Write `.dockerignore`**

```
.git
.venv
__pycache__
*.pyc
.pytest_cache
.chroma
runs
tests
.env
docs
```

- [ ] **Step 2: Write `Dockerfile`**

```dockerfile
# ---- Stage 1: build wheels for the api runtime ----
FROM python:3.13-slim AS builder
WORKDIR /build
COPY pyproject.toml ./
# Install only the runtime + api group into a venv we copy forward.
RUN python -m venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"
RUN pip install --no-cache-dir --upgrade pip \
 && pip install --no-cache-dir ".[api]"

# ---- Stage 2: slim runtime ----
FROM python:3.13-slim AS runtime
# HF Spaces runs containers as a non-root user (uid 1000) on port 7860.
RUN useradd -m -u 1000 appuser
WORKDIR /app
COPY --from=builder /opt/venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH" \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    RUNS_DIR=/app/runs \
    PORT=7860
COPY src ./src
COPY web ./web
RUN mkdir -p /app/runs && chown -R appuser:appuser /app
USER appuser
EXPOSE 7860
# HF Spaces convention: listen on 0.0.0.0:7860. One worker keeps the in-memory
# rate limiter coherent; scale out via the Redis seam + more replicas if needed.
CMD ["uvicorn", "src.api.main:app", "--host", "0.0.0.0", "--port", "7860", "--workers", "1"]
```

Note: `pip install ".[api]"` requires `pyproject.toml` to be installable standalone. The Foundation `pyproject.toml` declares `[project]` with runtime deps and the `api` optional group, so `pip install .[api]` pulls both. No `src/` copy is needed at build time for dependency resolution because there is no build backend compiling sources — if the build errors on a missing `[build-system]`, add `[build-system]\nrequires=["setuptools>=68"]\nbuild-backend="setuptools.build_meta"` plus `[tool.setuptools] packages=["src"]` to `pyproject.toml` (coordinate this back through COORDINATION.md as it touches a shared file).

- [ ] **Step 3: Build the image (manual verification)**

Run: `docker build -t finresearchai-api .`
Expected: builds clean. Then `docker run --rm -p 7860:7860 finresearchai-api &` and `curl -s http://localhost:7860/healthz` → `{"status":"ok"}`. Stop the container afterward.

- [ ] **Step 4: Commit**

```bash
git add Dockerfile .dockerignore
git commit -m "build(api): add multi-stage Dockerfile for uvicorn on port 7860"
```

---

### Task 9: Hugging Face Space (Docker SDK) configuration note

This replaces the legacy Gradio SDK Space. HF Spaces with the Docker SDK read frontmatter from the repo `README.md` and build the `Dockerfile`, exposing port `7860`.

**Files:**
- Create: `README-hfspace.md` (documentation; the actual Space README frontmatter is applied during deployment)

- [ ] **Step 1: Write `README-hfspace.md`**

```markdown
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
```

- [ ] **Step 2: Commit**

```bash
git add README-hfspace.md
git commit -m "docs(api): document HF Docker Space config replacing Gradio SDK"
```

---

### Task 10: Full-suite green gate

**Files:** none (verification only)

- [ ] **Step 1: Run the entire test suite**

Run: `python -m pytest -q`
Expected: all Foundation modules + `test_api_schemas`, `test_api_ratelimit`, `test_api_stream`, `test_api_main` PASS. Zero network calls were made (every test ran against the stub graph).

- [ ] **Step 2: Lint the new modules**

Run: `python -m ruff check src/api tests/test_api_*.py`
Expected: clean (or auto-fixable with `ruff check --fix`).

- [ ] **Step 3: Commit any lint fixes**

```bash
git add -A && git commit -m "style(api): ruff fixes" || echo "nothing to fix"
```

---

## Dependencies

- **Foundation (`2026-05-29-foundation-and-state-contract.md`) MUST be merged first.** WP-G imports `build_graph` (`src/graph.py`), `AgentState` (`src/state.py`), and `RunRecorder` (`src/obs/recorder.py`) — all frozen by Foundation. Nothing else is required.
- **No dependency on WP-B/C/D/E/F.** Per COORDINATION.md §4, WP-G codes against the compiled graph only and works end-to-end on the 12-node STUB graph today (this is what makes its tests run with no LLM keys and no network). When the real nodes land:
  - `node_start`/`node_complete` events automatically reflect real node deltas.
  - `token` events begin appearing (the stub emits none because it makes no LLM calls).
  - `done.final_report`/`final_decision` carry real WP-F/WP-E output.
  - `debate_mode="off"` routing is exercised once WP-D wires `build_graph("off")`; the API already forwards the flag.
- **Parallel-development note:** because WP-G never imports a concrete node, it can be built, tested, and merged in parallel with every other WP. The only shared file it edits is `pyproject.toml` (Task 1, additive: fills the pre-reserved `api` group) — coordinate that one-line group fill via COORDINATION.md if another WP touches the same group simultaneously.

## Definition of Done
- [ ] `pyproject.toml` `api` group is pinned: `fastapi==0.136.3`, `uvicorn[standard]==0.48.0`, `sse-starlette==3.4.4`, `httpx==0.28.1`; `pip install -e ".[api]"` succeeds.
- [ ] `python -m pytest -q` is green including the four new `test_api_*` modules, with NO network/LLM calls (all run against the stub graph).
- [ ] `POST /analyze` returns `text/event-stream`, emits `start` → per-node `node_start`/`node_complete` (→ `token` once real nodes land) → terminal `done` carrying `final_report`, `final_decision`, and `run_metrics`; mid-run failures surface as a clean `error` event, not an HTTP 500.
- [ ] `GET /healthz` returns `{"status":"ok"}`; `GET /runs/{run_id}` returns the JSONL trace as JSON (404 on unknown id, 400 on traversal attempt).
- [ ] Input validation rejects malformed tickers with 422 (anchored `TICKER_RE`, uppercased/stripped); rate limiter returns 429 after the cap; CORS headers present.
- [ ] Rate limiter defaults to in-memory and transparently upgrades to Redis when `REDIS_URL` + the `redis` package are present, degrading gracefully if not.
- [ ] `web/index.html` POSTs to `/analyze` and renders the live stream (each node appears then turns done, then the report) with zero JS dependencies.
- [ ] `Dockerfile` builds a multi-stage image running `uvicorn src.api.main:app` on `0.0.0.0:7860` as a non-root user; `README-hfspace.md` documents the Docker SDK frontmatter (`sdk: docker`, `app_port: 7860`) and secrets, replacing the Gradio SDK Space.
- [ ] Verified-API facts are documented in "Context7-verified library APIs": LangGraph 1.0.4 list `stream_mode` yields `(mode, chunk)` tuples; `"updates"` = `{node: delta}`, `"messages"` = `(message, metadata)` with `metadata["langgraph_node"]`, `"values"` = full accumulated state snapshot; sse-starlette `EventSourceResponse` consumes a generator of `{"event","data"}` dicts.

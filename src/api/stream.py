"""Async SSE generator that runs the compiled LangGraph and maps its stream to events.

We drive `build_graph(debate_mode).astream(input, stream_mode=["updates","messages","values"])`.
Because stream_mode is a LIST, LangGraph yields 2-tuples `(mode, chunk)` (verified
against langgraph 1.0.10):

  mode == "updates":  chunk is dict[node_name, state_delta]  -> node_start + node_complete
  mode == "messages": chunk is (message, metadata)           -> token (metadata.langgraph_node)
  mode == "values":   chunk is the full reducer-accumulated state snapshot (kept as final)

The stub graph emits no "messages" chunks (no LLM calls); token events appear once
real nodes land. The terminal `done` event carries final_report + final_decision +
run_metrics taken from the last "values" snapshot (the reducer-accumulated state, so
run_metrics holds all per-node entries — 12 for the on-topology stub graph).
"""
from __future__ import annotations

import asyncio
import json
import logging
import time
import uuid
from collections.abc import AsyncIterator
from functools import lru_cache
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
from src.config.settings import get_settings
from src.graph import build_graph
from src.obs.recorder import RunRecorder
from src.warehouse.ingest import record_run_events, record_run_finish, record_run_start


_LOG = logging.getLogger(__name__)

# Strong refs to the detached finalize tasks scheduled from the stream's finally
# block (see analyze_event_stream): asyncio only keeps weak refs to tasks, so
# without this set a backgrounded finalize could be garbage-collected mid-write.
# Tasks discard themselves on completion.
_FINALIZE_TASKS: set[asyncio.Task[None]] = set()


def _node_from_messages_meta(metadata: dict[str, Any]) -> str:
    return metadata.get("langgraph_node", "unknown")


class _RunPersistence:
    """Warehouse persistence bookkeeping for one analysis run (WP-4).

    ``capture`` wraps ``sse_event``: it buffers every emitted event as
    ``{"name", "data", "ts_ms"}`` (ts_ms at yield time — the timing that powers
    the replay scrubber) and returns the SSE dict to yield. Events are written
    in ONE bulk insert at ``finalize`` — never per-event during streaming (token
    events can number thousands). All writes go through the never-raise ingest
    API, so a disabled warehouse or DB failure cannot affect streaming.
    """

    def __init__(self, run_id: str, ticker: str, debate_mode: str | None) -> None:
        self.run_id = run_id
        self.ticker = ticker
        # None means "settings default" (same resolution as build_graph); the
        # runs row stores the resolved value.
        self.debate_mode: str = debate_mode or get_settings().debate_mode
        self.events: list[dict[str, Any]] = []
        # Until done/error is reached, the run counts as aborted (client
        # disconnect mid-stream lands here via GeneratorExit -> finally).
        self.status = "aborted"
        self.final_decision: dict[str, Any] | None = None
        self.report: str | None = None
        self.metrics: list[Any] | None = None

    async def start(self) -> None:
        await record_run_start(self.run_id, self.ticker, self.debate_mode)

    def capture(self, name: str, payload: dict[str, Any]) -> dict[str, str]:
        event = sse_event(name, payload)
        # Round-trip the serialized payload: sse_event already coerced any
        # non-JSON values (default=str), so the stored event is exactly what
        # the client received and is guaranteed JSON-safe for the DB column.
        self.events.append(
            {"name": name, "data": json.loads(event["data"]), "ts_ms": int(time.time() * 1000)}
        )
        return event

    def mark_done(
        self, *, final_decision: dict[str, Any] | None, report: str, metrics: list[Any]
    ) -> None:
        self.status = "finished"
        self.final_decision = final_decision
        self.report = report
        self.metrics = metrics

    def mark_error(self) -> None:
        self.status = "error"  # error/aborted runs persist no payload

    async def finalize(self) -> None:
        # Events first, finish second: a "finished" runs row implies its events
        # are already queryable (the Research Library lists finished runs).
        await record_run_events(self.run_id, self.events)
        await record_run_finish(
            self.run_id,
            status=self.status,
            final_decision=self.final_decision,
            report=self.report,
            metrics=self.metrics,
        )


@lru_cache(maxsize=4)
def _compiled_graph(debate_mode: str | None):
    """Compile each topology once and reuse it across requests.

    Nodes read ``get_llm`` lazily at call time, so a cached compiled graph stays
    correct under per-test monkeypatching; only the static topology is memoized.
    """
    return build_graph(debate_mode)


async def analyze_event_stream(
    *,
    ticker: str,
    investor_mode: str,
    debate_mode: str | None,
    run_id: str | None = None,
    runs_dir: str = "runs",
) -> AsyncIterator[dict[str, str]]:
    """Yield sse-starlette event dicts for one analysis run over the compiled graph.

    Persists two run records, both flushed even if the stream errors mid-run:
    a JSONL trace via RunRecorder (local fallback; ``GET /api/runs/{run_id}``
    replays it) and — when the warehouse is enabled — a ``runs`` row plus the full
    ordered SSE event stream in ``run_events`` (WP-4; never affects streaming).
    """
    run_id = run_id or uuid.uuid4().hex[:12]
    recorder = RunRecorder(runs_dir=runs_dir, run_id=run_id)
    persistence = _RunPersistence(run_id, ticker, debate_mode)
    recorder.record("__run__", "start", {"ticker": ticker, "investor_mode": investor_mode})
    await persistence.start()

    final_state: dict[str, Any] = {}
    seen_started: set[str] = set()
    try:
        # The start yield lives INSIDE the try so a client disconnect at any
        # yield point (GeneratorExit) still reaches the finally-persistence.
        yield persistence.capture("start", start_payload(run_id, ticker, investor_mode))

        graph = _compiled_graph(debate_mode)
        inputs = {"ticker": ticker, "investor_mode": investor_mode, "run_id": run_id}

        async for mode, chunk in graph.astream(
            inputs, stream_mode=["updates", "messages", "values"]
        ):
            if mode == "updates":
                # chunk: {node_name: state_delta, ...}
                for node, delta in (chunk or {}).items():
                    if node not in seen_started:
                        seen_started.add(node)
                        yield persistence.capture("node_start", node_start_payload(run_id, node))
                    recorder.record(node, "node_complete", delta or {})
                    yield persistence.capture(
                        "node_complete", node_complete_payload(run_id, node, delta or {})
                    )
            elif mode == "messages":
                # chunk: (message, metadata)
                message, metadata = chunk
                text = getattr(message, "content", "") or ""
                if text:
                    yield persistence.capture(
                        "token", token_payload(run_id, _node_from_messages_meta(metadata), text)
                    )
            elif mode == "values":
                # full reducer-accumulated state snapshot; keep the latest.
                final_state = chunk or final_state

        # No decision in the final state persists as NULL (the RunDetail
        # null contract); the done SSE payload keeps its {} sentinel via
        # done_payload, so the wire shape is unchanged.
        decision = final_state.get("final_decision") or None
        report = final_state.get("final_report", "")
        metrics = final_state.get("run_metrics", []) or []
        recorder.record(
            "__run__", "done", {"final_decision": decision or {}, "run_metrics": metrics}
        )
        persistence.mark_done(final_decision=decision, report=report, metrics=metrics)
        yield persistence.capture(
            "done",
            done_payload(run_id, final_report=report, final_decision=decision, run_metrics=metrics),
        )
    except Exception as exc:  # never leak a 500 mid-stream: emit a clean error event
        # Full exception text goes to the server log + JSONL trace only — raw
        # str(exc) can carry URLs, file paths or provider details; the client
        # gets a generic message with the run_id for support correlation.
        _LOG.exception("analyze stream failed (run_id %s)", run_id)
        recorder.record("__run__", "error", {"error": str(exc)})
        persistence.mark_error()
        yield persistence.capture(
            "error",
            error_payload(run_id, f"analysis failed — see server logs (run_id {run_id})"),
        )
    finally:
        # Persist the traces regardless of success/failure/disconnect: JSONL so
        # /api/runs/{id} resolves, then the warehouse (events before the run-finish
        # row; both no-op/degrade when the warehouse is unavailable). A client
        # disconnect lands here via GeneratorExit (not the except above), so the
        # status stays "aborted" — we must only await here, never yield.
        #
        # A REAL disconnect cancels the consuming task (sse-starlette/anyio level
        # cancellation), which re-delivers CancelledError at every await in this
        # finally — a bare `await persistence.finalize()` would itself be
        # cancelled and strand the run as status="running" forever. So: flush the
        # JSONL synchronously (uncancellable), run finalize as a DETACHED task
        # (strong-ref'd in _FINALIZE_TASKS so it can't be GC'd), and await it
        # through asyncio.shield — when the shield's await is cancelled, the
        # outer cancellation proceeds while the task completes in the background.
        recorder.flush()
        task = asyncio.ensure_future(persistence.finalize())
        _FINALIZE_TASKS.add(task)
        task.add_done_callback(_FINALIZE_TASKS.discard)
        try:
            await asyncio.shield(task)
        except asyncio.CancelledError:
            # Swallow ONLY the delivery aimed at this await: the original
            # cancellation resumes propagating after this finally block.
            pass

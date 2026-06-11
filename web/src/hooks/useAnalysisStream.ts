/**
 * useAnalysisStream — drives POST /api/analyze and reduces its SSE event stream
 * into typed React state for the Analyze cockpit (WP-7 builds the full UI on top
 * of this; WP-6 ships the hook + a minimal feed to prove the plumbing).
 *
 * Exposes: phase, the ordered list of nodes seen, which completed, per-node
 * streamed token text, the terminal `done` payload, and any error. Abortable via
 * the returned `stop()` and on unmount.
 */
import { useCallback, useEffect, useReducer, useRef } from "react";

import {
  initialState,
  reducer,
  type AnalysisStreamState,
} from "@/hooks/analysisReducer";
import { type DebateMode, type InvestorMode } from "@/lib/api";
import {
  SseFrameParser,
  decodeEvent,
  type RawSseFrame,
} from "@/lib/sse";

// Re-exported so existing imports (the cockpit, panels, tests) keep resolving
// `AnalysisStreamState`/`NodeRun`/etc. from this hook unchanged after the
// reducer was lifted into analysisReducer.ts for the replay driver to share.
export type {
  AnalysisDone,
  AnalysisStreamState,
  NodeRun,
  StreamPhase,
} from "@/hooks/analysisReducer";

export interface StartAnalysisParams {
  ticker: string;
  investorMode: InvestorMode;
  debateMode?: DebateMode;
}

/**
 * Pull a human-readable message out of a FastAPI error body. Handles both
 * `{detail: "msg"}` and the 422 validation shape `{detail: [{msg, …}, …]}` so
 * a refused ticker surfaces the backend's actual reason, not "analyze -> 422".
 */
function detailMessage(body: unknown): string | null {
  if (!body || typeof body !== "object") return null;
  const detail = (body as { detail?: unknown }).detail;
  if (typeof detail === "string" && detail.trim() !== "") return detail;
  if (Array.isArray(detail)) {
    const msgs = detail
      .map((d) =>
        d && typeof d === "object" && typeof (d as { msg?: unknown }).msg === "string"
          ? (d as { msg: string }).msg
          : null,
      )
      .filter((m): m is string => m != null && m.trim() !== "");
    if (msgs.length > 0) return msgs.join("; ");
  }
  return null;
}

export interface UseAnalysisStream {
  state: AnalysisStreamState;
  isActive: boolean;
  start: (params: StartAnalysisParams) => Promise<void>;
  stop: () => void;
  reset: () => void;
}

export function useAnalysisStream(): UseAnalysisStream {
  const [state, dispatch] = useReducer(reducer, initialState);
  const controllerRef = useRef<AbortController | null>(null);

  const stop = useCallback(() => {
    controllerRef.current?.abort();
    controllerRef.current = null;
    // Terminal transition: without this the phase stays "streaming" and the
    // Stop button is dead. The reducer ignores it once done/error has landed.
    dispatch({ kind: "abort" });
  }, []);

  // Abort any in-flight stream when the owning component unmounts.
  useEffect(() => () => controllerRef.current?.abort(), []);

  const reset = useCallback(() => {
    stop();
    dispatch({ kind: "reset" });
  }, [stop]);

  const start = useCallback(
    async (params: StartAnalysisParams) => {
      // Cancel any in-flight run before starting a new one.
      stop();
      const controller = new AbortController();
      controllerRef.current = controller;
      dispatch({ kind: "connect" });

      const body: Record<string, string> = {
        ticker: params.ticker,
        investor_mode: params.investorMode,
      };
      if (params.debateMode) body.debate_mode = params.debateMode;

      let res: Response;
      try {
        res = await fetch("/api/analyze", {
          method: "POST",
          headers: {
            "Content-Type": "application/json",
            Accept: "text/event-stream",
          },
          body: JSON.stringify(body),
          signal: controller.signal,
        });
      } catch (err) {
        if (controller.signal.aborted) return;
        dispatch({
          kind: "error",
          message: err instanceof Error ? err.message : "network error",
        });
        return;
      }

      if (res.status === 429) {
        dispatch({
          kind: "error",
          message: "Rate limited — daily live-run quota reached. Try a replay.",
          status: 429,
        });
        return;
      }
      if (!res.ok || !res.body) {
        // Read the JSON error body (e.g. a 422's validation detail) so the
        // user sees the backend's reason instead of a bare status code.
        let body: unknown;
        try {
          body = await res.json();
        } catch {
          body = undefined;
        }
        dispatch({
          kind: "error",
          message: detailMessage(body) ?? `analyze -> ${res.status}`,
          status: res.status,
        });
        return;
      }

      const reader = res.body.getReader();
      const decoder = new TextDecoder();
      const parser = new SseFrameParser();

      // Tracks whether a terminal done/error frame arrived, so a stream that
      // drains without one can be surfaced instead of streaming forever.
      let sawTerminal = false;
      const handleFrame = (frame: RawSseFrame) => {
        const event = decodeEvent(frame);
        if (!event) return;
        if (event.type === "done" || event.type === "error") sawTerminal = true;
        dispatch({ kind: "event", event });
      };

      try {
        for (;;) {
          const { value, done } = await reader.read();
          if (done) break;
          const text = decoder.decode(value, { stream: true });
          for (const frame of parser.push(text)) handleFrame(frame);
        }
        // Drain any final, blank-line-less frame.
        for (const frame of parser.flush()) handleFrame(frame);
        if (!sawTerminal && !controller.signal.aborted) {
          dispatch({ kind: "error", message: "stream ended early" });
        }
      } catch (err) {
        if (controller.signal.aborted) return; // user stopped — not an error
        dispatch({
          kind: "error",
          message: err instanceof Error ? err.message : "stream interrupted",
        });
      } finally {
        if (controllerRef.current === controller) controllerRef.current = null;
      }
    },
    [stop],
  );

  const isActive = state.phase === "connecting" || state.phase === "streaming";

  return { state, isActive, start, stop, reset };
}

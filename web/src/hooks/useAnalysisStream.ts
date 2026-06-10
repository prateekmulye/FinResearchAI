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
  ApiError,
  type DebateMode,
  type FinalDecision,
  type InvestorMode,
  type NodeMetric,
} from "@/lib/api";
import {
  SseFrameParser,
  decodeEvent,
  type AnalysisEvent,
  type RawSseFrame,
} from "@/lib/sse";

export type StreamPhase = "idle" | "connecting" | "streaming" | "done" | "error";

export interface NodeRun {
  node: string;
  startedAt: number;
  completedAt: number | null;
  /** Concatenated token text streamed for this node (reporter, etc.). */
  text: string;
}

export interface AnalysisDone {
  finalReport: string;
  finalDecision: FinalDecision | null;
  runMetrics: NodeMetric[];
}

export interface AnalysisStreamState {
  phase: StreamPhase;
  runId: string | null;
  ticker: string | null;
  investorMode: string | null;
  /** Insertion-ordered node ids as they were first seen. */
  order: string[];
  nodes: Record<string, NodeRun>;
  done: AnalysisDone | null;
  error: string | null;
}

const initialState: AnalysisStreamState = {
  phase: "idle",
  runId: null,
  ticker: null,
  investorMode: null,
  order: [],
  nodes: {},
  done: null,
  error: null,
};

type Action =
  | { kind: "connect" }
  | { kind: "event"; event: AnalysisEvent }
  | { kind: "error"; message: string }
  | { kind: "abort" }
  | { kind: "reset" };

function ensureNode(state: AnalysisStreamState, node: string): AnalysisStreamState {
  if (state.nodes[node]) return state;
  return {
    ...state,
    order: [...state.order, node],
    nodes: {
      ...state.nodes,
      [node]: { node, startedAt: Date.now(), completedAt: null, text: "" },
    },
  };
}

function reducer(state: AnalysisStreamState, action: Action): AnalysisStreamState {
  switch (action.kind) {
    case "reset":
      return initialState;
    case "connect":
      return { ...initialState, phase: "connecting" };
    case "error":
      return { ...state, phase: "error", error: action.message };
    case "abort":
      // A user-stopped run lands back at rest (the form recovers its Run
      // affordance); a terminal done/error phase is never clobbered.
      return state.phase === "connecting" || state.phase === "streaming"
        ? { ...state, phase: "idle" }
        : state;
    case "event": {
      const e = action.event;
      switch (e.type) {
        case "start":
          return {
            ...state,
            phase: "streaming",
            runId: e.run_id,
            ticker: e.ticker,
            investorMode: e.investor_mode,
          };
        case "node_start":
          return { ...ensureNode(state, e.node), phase: "streaming" };
        case "node_complete": {
          const withNode = ensureNode(state, e.node);
          const existing = withNode.nodes[e.node]!;
          return {
            ...withNode,
            nodes: {
              ...withNode.nodes,
              [e.node]: { ...existing, completedAt: Date.now() },
            },
          };
        }
        case "token": {
          const withNode = ensureNode(state, e.node);
          const existing = withNode.nodes[e.node]!;
          return {
            ...withNode,
            nodes: {
              ...withNode.nodes,
              [e.node]: { ...existing, text: existing.text + e.text },
            },
          };
        }
        case "done":
          return {
            ...state,
            phase: "done",
            done: {
              finalReport: e.final_report,
              finalDecision:
                e.final_decision && "action" in e.final_decision
                  ? (e.final_decision as FinalDecision)
                  : null,
              runMetrics: e.run_metrics ?? [],
            },
          };
        case "error":
          return { ...state, phase: "error", error: e.message };
        default:
          return state;
      }
    }
    default:
      return state;
  }
}

export interface StartAnalysisParams {
  ticker: string;
  investorMode: InvestorMode;
  debateMode?: DebateMode;
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
        });
        return;
      }
      if (!res.ok || !res.body) {
        dispatch({
          kind: "error",
          message: new ApiError(`analyze -> ${res.status}`, res.status).message,
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

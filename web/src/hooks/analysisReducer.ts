/**
 * analysisReducer — the pure state machine the Analyze cockpit renders from.
 *
 * Lifted out of useAnalysisStream so that BOTH drivers share one reducer:
 *   - LIVE   (useAnalysisStream): SSE frames -> events -> this reducer.
 *   - REPLAY (useEventPlayer):    recorded events -> this reducer, on a timer.
 *
 * The cockpit is a pure function of the resulting `AnalysisStreamState`, so it
 * never knows (or cares) which driver produced the state. This is the WP-8
 * replay seam made concrete — see eventPlayer.ts.
 *
 * The reducer is deliberately timestamp-light: rendering keys off `order` and
 * the boolean `completedAt != null`, never the absolute ms, so feeding the same
 * events through it during replay reproduces the exact live visual trajectory.
 */
import { type FinalDecision, type NodeMetric } from "@/lib/api";
import { type AnalysisEvent } from "@/lib/sse";

export type StreamPhase = "idle" | "connecting" | "streaming" | "done" | "error";

export interface NodeRun {
  node: string;
  startedAt: number;
  completedAt: number | null;
  /** Concatenated token text streamed for this node (reporter, etc.). */
  text: string;
  /**
   * The structured state delta this node emitted on `node_complete` (the raw
   * LangGraph state fragment — analyst_reports, research_debate, trade_proposal,
   * risk_debate, final_decision, run_metrics, …). The cockpit's intelligence
   * panels decode this; empty until the node completes.
   */
  delta: Record<string, unknown>;
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
  /** HTTP status behind the error, when one exists (429 drives quota UX). */
  errorStatus: number | null;
}

export const initialState: AnalysisStreamState = {
  phase: "idle",
  runId: null,
  ticker: null,
  investorMode: null,
  order: [],
  nodes: {},
  done: null,
  error: null,
  errorStatus: null,
};

export type Action =
  | { kind: "connect" }
  | { kind: "event"; event: AnalysisEvent }
  | { kind: "error"; message: string; status?: number | null }
  | { kind: "abort" }
  | { kind: "reset" };

/**
 * A monotonic clock the reducer can stamp node lifecycle times with. Live runs
 * use Date.now(); replay overrides it (see `analysisClock`) so a re-reduce from
 * t=0 is deterministic and free of wall-clock drift. Rendering never reads the
 * absolute value — only its presence — so this is purely cosmetic/debuggable.
 */
export const analysisClock = { now: () => Date.now() };

function ensureNode(state: AnalysisStreamState, node: string): AnalysisStreamState {
  if (state.nodes[node]) return state;
  return {
    ...state,
    order: [...state.order, node],
    nodes: {
      ...state.nodes,
      [node]: {
        node,
        startedAt: analysisClock.now(),
        completedAt: null,
        text: "",
        delta: {},
      },
    },
  };
}

export function reducer(
  state: AnalysisStreamState,
  action: Action,
): AnalysisStreamState {
  switch (action.kind) {
    case "reset":
      return initialState;
    case "connect":
      return { ...initialState, phase: "connecting" };
    case "error":
      return {
        ...state,
        phase: "error",
        error: action.message,
        errorStatus: action.status ?? null,
      };
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
              [e.node]: {
                ...existing,
                completedAt: analysisClock.now(),
                // Merge so a node that completes in multiple updates (or that
                // also streamed tokens) keeps every key it ever reported.
                delta: { ...existing.delta, ...(e.delta ?? {}) },
              },
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
          // In-stream failure — there is no HTTP status behind it.
          return { ...state, phase: "error", error: e.message, errorStatus: null };
        default:
          return state;
      }
    }
    default:
      return state;
  }
}

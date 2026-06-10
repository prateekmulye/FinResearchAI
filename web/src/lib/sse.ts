/**
 * Pure SSE frame parser for the FinResearchAI analysis stream.
 *
 * The backend (POST /api/analyze) returns text/event-stream over a fetch body,
 * so we cannot use the native EventSource (GET-only). Frames are separated by a
 * blank line ("\n\n"); within a frame, `event:` names the event and one or more
 * `data:` lines carry the payload (joined, per the SSE spec). This module is the
 * dumb, fully-testable core: feed it raw chunks, get back typed events. The React
 * hook (useAnalysisStream) owns the network + reducer.
 *
 * Event contract (src/api/schemas.py): every decoded payload has {type, run_id}.
 *   start          { ticker, investor_mode }
 *   node_start     { node }
 *   node_complete  { node, delta }
 *   token          { node, text }
 *   error          { message }
 *   done           { final_report, final_decision, run_metrics }
 */

import type { FinalDecision, NodeMetric } from "./api";

export type SseEventName =
  | "start"
  | "node_start"
  | "node_complete"
  | "token"
  | "error"
  | "done"
  | "message"; // SSE default when no `event:` line is present

export interface RawSseFrame {
  event: SseEventName;
  data: string;
}

/* ---- typed event variants (the parsed payloads) ---- */

export interface StartEvent {
  type: "start";
  run_id: string;
  ticker: string;
  investor_mode: string;
}
export interface NodeStartEvent {
  type: "node_start";
  run_id: string;
  node: string;
}
export interface NodeCompleteEvent {
  type: "node_complete";
  run_id: string;
  node: string;
  delta: Record<string, unknown>;
}
export interface TokenEvent {
  type: "token";
  run_id: string;
  node: string;
  text: string;
}
export interface ErrorEvent {
  type: "error";
  run_id: string;
  message: string;
}
export interface DoneEvent {
  type: "done";
  run_id: string;
  final_report: string;
  final_decision: FinalDecision | Record<string, never>;
  run_metrics: NodeMetric[];
}

export type AnalysisEvent =
  | StartEvent
  | NodeStartEvent
  | NodeCompleteEvent
  | TokenEvent
  | ErrorEvent
  | DoneEvent;

/**
 * Incremental SSE parser. `push()` accepts an arbitrary chunk of decoded text
 * (chunk boundaries may split frames, even mid-line) and returns the complete
 * frames it can now emit, retaining the partial tail for the next call.
 */
export class SseFrameParser {
  private buffer = "";

  push(chunk: string): RawSseFrame[] {
    // Normalize CRLF -> LF so "\n\n" framing is reliable across servers.
    this.buffer += chunk.replace(/\r\n/g, "\n");
    const frames: RawSseFrame[] = [];

    let sepIndex: number;
    while ((sepIndex = this.buffer.indexOf("\n\n")) !== -1) {
      const rawFrame = this.buffer.slice(0, sepIndex);
      this.buffer = this.buffer.slice(sepIndex + 2);
      const parsed = parseFrame(rawFrame);
      if (parsed) frames.push(parsed);
    }
    return frames;
  }

  /** Flush any trailing frame not terminated by a blank line (stream ended). */
  flush(): RawSseFrame[] {
    const tail = this.buffer.trim();
    this.buffer = "";
    if (!tail) return [];
    const parsed = parseFrame(tail);
    return parsed ? [parsed] : [];
  }
}

/** Parse a single raw frame's lines into {event, data}; null if it has no data. */
export function parseFrame(rawFrame: string): RawSseFrame | null {
  let event: SseEventName = "message";
  const dataLines: string[] = [];

  for (const line of rawFrame.split("\n")) {
    if (line.startsWith(":")) continue; // SSE comment / heartbeat (`: ping`)
    if (line.startsWith("event:")) {
      event = line.slice(6).trim() as SseEventName;
    } else if (line.startsWith("data:")) {
      // Per spec, a single leading space after the colon is stripped.
      dataLines.push(line.slice(5).replace(/^ /, ""));
    }
  }
  if (dataLines.length === 0) return null;
  return { event, data: dataLines.join("\n") };
}

/**
 * Decode one raw frame into a typed AnalysisEvent. Returns null for frames we
 * can't use (bad JSON, unknown type) — the caller skips them rather than crash.
 */
export function decodeEvent(frame: RawSseFrame): AnalysisEvent | null {
  let payload: unknown;
  try {
    payload = JSON.parse(frame.data);
  } catch {
    return null;
  }
  if (typeof payload !== "object" || payload === null) return null;
  const obj = payload as Record<string, unknown>;
  // Trust the payload's own `type` (the backend always sets it); fall back to
  // the SSE event name for robustness.
  const type = (obj.type as string) ?? frame.event;

  switch (type) {
    case "node_start":
    case "node_complete":
    case "token":
      // Node-scoped events are unusable (and unsafe to cast) without a node id.
      if (typeof obj.node !== "string") return null;
      return { ...(obj as object), type } as AnalysisEvent;
    case "start":
    case "error":
    case "done":
      return { ...(obj as object), type } as AnalysisEvent;
    default:
      return null;
  }
}

/**
 * replayEvents — map a recorded RunDetail.events[] list onto the typed
 * AnalysisEvent stream the cockpit reducer consumes, plus a timing model.
 *
 * The warehouse stores each SSE frame as `{ name, data, ts_ms }` where `data`
 * is the already-parsed payload (carrying its own `{type, run_id, node, …}`).
 * So decoding is just: stringify `data`, hand the synthetic raw frame to the
 * SAME `decodeEvent` the live path uses. (The JSONL fallback shape
 * `{run_id, node, kind, data}` has no `name`/`ts_ms`; we tolerate it but the
 * warehouse path is the real replay fuel.)
 *
 * TIMING — the load-bearing replay decision. Recorded `ts_ms` deltas are real
 * wall-clock gaps; in APP_FAKE_LLM demo mode a whole 12-node run can land in
 * ~40ms, which would replay as an unwatchable instant. We therefore synthesize
 * a cadence: each step's gap is `clamp(realDelta, MIN_STEP, MAX_STEP)`. This
 * preserves ordering and the *relative* rhythm of a slow real run while
 * guaranteeing every node gets enough dwell time for the cockpit's breathe +
 * luminous-accent flash to read — the node-by-node animation that is the demo.
 */
import type { ReplayEvent } from "@/lib/api";
import { decodeEvent, type AnalysisEvent } from "@/lib/sse";

/** Floor/ceiling (ms) for the synthetic inter-event gap at 1x speed. */
export const MIN_STEP_MS = 420;
export const MAX_STEP_MS = 1600;

export interface ReplayStep {
  event: AnalysisEvent;
  /** Synthetic offset from playback start (ms) at 1x — drives scheduling + scrub. */
  offsetMs: number;
  /**
   * Elapsed ms in the ORIGINAL recorded run at this step — cumulative real
   * `ts_ms` deltas, UNclamped (zero-floored per gap; synthetic fallback when a
   * record carries no ts). This is what the cockpit's ELAPSED readout shows
   * during replay: the run's own timing, never the playback wall clock.
   */
  recordedOffsetMs: number;
  /** The node id this step touches, if any — used to mark stage ticks. */
  node: string | null;
  /** The wire event name, for tick semantics (node_complete = a stage landed). */
  name: AnalysisEvent["type"];
}

/** Pull the SSE payload object out of a recorded event in either store shape. */
function payloadOf(raw: ReplayEvent): Record<string, unknown> | null {
  // Warehouse: { name, data: {type, …}, ts_ms }.
  if (raw.data && typeof raw.data === "object") return raw.data;
  // Some shapes inline the payload at the top level — accept that too.
  if (typeof raw.type === "string") return raw as Record<string, unknown>;
  return null;
}

/** Decode one recorded event into a typed AnalysisEvent, reusing the live guard. */
export function decodeReplayEvent(raw: ReplayEvent): AnalysisEvent | null {
  const payload = payloadOf(raw);
  if (!payload) return null;
  // Prefer the SSE event name the recorder stored; fall back to payload.type.
  const name =
    (typeof raw.name === "string" && raw.name) ||
    (typeof payload.type === "string" ? (payload.type as string) : "message");
  // Round-trip through the same decodeEvent the live stream uses, so the two
  // paths can never diverge on validation/coercion rules.
  return decodeEvent({ event: name as never, data: JSON.stringify(payload) });
}

/**
 * Compile recorded events into an ordered, time-stamped step list with a
 * synthetic 1x cadence. Returns the steps plus the total synthetic duration.
 */
export function compileReplay(events: readonly ReplayEvent[]): {
  steps: ReplayStep[];
  durationMs: number;
} {
  const steps: ReplayStep[] = [];
  let offset = 0;
  let recorded = 0;
  let prevTs: number | null = null;

  for (const raw of events) {
    const event = decodeReplayEvent(raw);
    if (!event) continue;

    const ts = typeof raw.ts_ms === "number" ? raw.ts_ms : null;
    if (steps.length > 0) {
      const realDelta = ts != null && prevTs != null ? ts - prevTs : MIN_STEP_MS;
      offset += clamp(realDelta, MIN_STEP_MS, MAX_STEP_MS);
      // The original run's own clock: real deltas, zero-floored so a recorder
      // ts regression can never run ELAPSED backwards.
      recorded += Math.max(0, realDelta);
    }
    prevTs = ts;

    const node =
      "node" in event && typeof event.node === "string" ? event.node : null;
    steps.push({ event, offsetMs: offset, recordedOffsetMs: recorded, node, name: event.type });
  }

  return { steps, durationMs: offset };
}

function clamp(v: number, lo: number, hi: number): number {
  return Math.max(lo, Math.min(hi, v));
}

/**
 * Per-node latency (SECONDS) from the recorded run's own clock: the
 * recordedOffsetMs delta between each node's first node_start and its
 * node_complete. This is what the replay transcript shows — the reducer's
 * replay-mode lifecycle stamps are synthetic fold ticks, so deriving latency
 * from them renders nonsense ("1ms" rows).
 */
export function recordedNodeLatencies(
  steps: readonly ReplayStep[],
): Record<string, number> {
  const startedAt: Record<string, number> = {};
  const out: Record<string, number> = {};
  for (const s of steps) {
    if (!s.node) continue;
    if (s.name === "node_start" && !(s.node in startedAt)) {
      startedAt[s.node] = s.recordedOffsetMs;
    } else if (s.name === "node_complete" && s.node in startedAt) {
      out[s.node] = Math.max(0, s.recordedOffsetMs - startedAt[s.node]!) / 1000;
    }
  }
  return out;
}

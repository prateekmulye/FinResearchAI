/**
 * replayEvents — ReplayEvent -> AnalysisEvent mapping + the synthetic-cadence
 * compilation. The mapping reuses decodeEvent, so these tests focus on the
 * recorder-shape adaptation and the timing model (the bit that makes a 40ms
 * real run watchable).
 */
import { describe, expect, it } from "vitest";

import type { ReplayEvent } from "@/lib/api";

import {
  MAX_STEP_MS,
  MIN_STEP_MS,
  compileReplay,
  decodeReplayEvent,
  recordedNodeLatencies,
} from "./replayEvents";
import { fixtureEvents } from "./replayFixture";

describe("decodeReplayEvent", () => {
  it("decodes a warehouse-shaped event ({name, data, ts_ms})", () => {
    const e = decodeReplayEvent({
      name: "node_complete",
      ts_ms: 1,
      data: { type: "node_complete", run_id: "r", node: "router", delta: { a: 1 } },
    });
    expect(e).toMatchObject({ type: "node_complete", node: "router", delta: { a: 1 } });
  });

  it("falls back to the inlined payload shape (no `data` wrapper)", () => {
    const e = decodeReplayEvent({
      type: "start",
      run_id: "r",
      ticker: "AAPL",
      investor_mode: "Neutral",
    } as ReplayEvent);
    expect(e).toMatchObject({ type: "start", ticker: "AAPL" });
  });

  it("drops a node event missing its node id (guard via decodeEvent)", () => {
    expect(
      decodeReplayEvent({ name: "node_start", data: { type: "node_start", run_id: "r" } }),
    ).toBeNull();
  });

  it("returns null for an unusable record", () => {
    expect(decodeReplayEvent({} as ReplayEvent)).toBeNull();
    expect(decodeReplayEvent({ data: 5 } as unknown as ReplayEvent)).toBeNull();
  });
});

describe("compileReplay timing", () => {
  it("orders steps and assigns monotonically increasing offsets from 0", () => {
    const { steps } = compileReplay(fixtureEvents);
    expect(steps[0]!.offsetMs).toBe(0);
    for (let i = 1; i < steps.length; i++) {
      expect(steps[i]!.offsetMs).toBeGreaterThanOrEqual(steps[i - 1]!.offsetMs);
    }
  });

  it("floors a tiny real gap to MIN_STEP so node-by-node animation is visible", () => {
    // fixture ts deltas are ~10ms — far below MIN_STEP — so every gap = MIN_STEP.
    const { steps, durationMs } = compileReplay(fixtureEvents);
    expect(steps[1]!.offsetMs).toBe(MIN_STEP_MS);
    expect(durationMs).toBe(MIN_STEP_MS * (steps.length - 1));
  });

  it("caps a huge real gap at MAX_STEP", () => {
    const events: ReplayEvent[] = [
      { name: "start", ts_ms: 0, data: { type: "start", run_id: "r", ticker: "X", investor_mode: "Neutral" } },
      { name: "done", ts_ms: 60_000, data: { type: "done", run_id: "r", final_report: "", final_decision: {}, run_metrics: [] } },
    ];
    const { steps } = compileReplay(events);
    expect(steps[1]!.offsetMs).toBe(MAX_STEP_MS);
  });

  it("marks node_complete steps as stage ticks with their node", () => {
    const { steps } = compileReplay(fixtureEvents);
    const ticks = steps.filter((s) => s.name === "node_complete");
    expect(ticks.map((t) => t.node)).toEqual(["router", "reporter"]);
  });

  it("carries the ORIGINAL run's elapsed ms per step (unclamped ts deltas)", () => {
    // fixture ts_ms: 1000,1010,1020,1030,1035,1040,1050,1060 — the recorded
    // offsets are the real run's elapsed, NOT the clamped synthetic cadence.
    const { steps } = compileReplay(fixtureEvents);
    expect(steps.map((s) => s.recordedOffsetMs)).toEqual([0, 10, 20, 30, 35, 40, 50, 60]);
  });

  it("recorded offsets fall back to the synthetic gap when ts_ms is missing", () => {
    const events: ReplayEvent[] = [
      { name: "start", data: { type: "start", run_id: "r", ticker: "X", investor_mode: "Neutral" } },
      { name: "done", data: { type: "done", run_id: "r", final_report: "", final_decision: {}, run_metrics: [] } },
    ];
    const { steps } = compileReplay(events);
    expect(steps[0]!.recordedOffsetMs).toBe(0);
    expect(steps[1]!.recordedOffsetMs).toBe(MIN_STEP_MS);
  });

  it("recorded offsets never regress on out-of-order ts_ms (zero-floored gap)", () => {
    const events: ReplayEvent[] = [
      { name: "start", ts_ms: 500, data: { type: "start", run_id: "r", ticker: "X", investor_mode: "Neutral" } },
      { name: "done", ts_ms: 400, data: { type: "done", run_id: "r", final_report: "", final_decision: {}, run_metrics: [] } },
    ];
    const { steps } = compileReplay(events);
    expect(steps[1]!.recordedOffsetMs).toBe(0);
  });

  it("skips undecodable records without breaking the offset chain", () => {
    const events: ReplayEvent[] = [
      { name: "start", ts_ms: 0, data: { type: "start", run_id: "r", ticker: "X", investor_mode: "Neutral" } },
      { name: "garbage", ts_ms: 5, data: { nope: true } },
      { name: "done", ts_ms: 10, data: { type: "done", run_id: "r", final_report: "", final_decision: {}, run_metrics: [] } },
    ];
    const { steps } = compileReplay(events);
    expect(steps).toHaveLength(2);
    expect(steps.map((s) => s.event.type)).toEqual(["start", "done"]);
  });
});

describe("recordedNodeLatencies", () => {
  it("derives per-node latency (s) from recorded node_start -> node_complete deltas", () => {
    // fixture: router 1010 -> 1020 (10ms), reporter 1030 -> 1050 (20ms).
    const { steps } = compileReplay(fixtureEvents);
    expect(recordedNodeLatencies(steps)).toEqual({
      router: 0.01,
      reporter: 0.02,
    });
  });

  it("omits a node whose start was never recorded (no fabricated number)", () => {
    const events: ReplayEvent[] = [
      { name: "start", ts_ms: 0, data: { type: "start", run_id: "r", ticker: "X", investor_mode: "Neutral" } },
      { name: "node_complete", ts_ms: 30, data: { type: "node_complete", run_id: "r", node: "router", delta: {} } },
    ];
    const { steps } = compileReplay(events);
    expect(recordedNodeLatencies(steps)).toEqual({});
  });
});

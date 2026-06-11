/**
 * useEventPlayer — the replay driver. We drive its rAF loop deterministically
 * (a controllable fake rAF + a virtual performance clock) so we can assert
 * ordering, speed scaling, pause, end-of-stream, and — the key one — that seek
 * is a pure re-reduce up to the target time (no interpolation, full causal state).
 */
import { act, renderHook } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { useEventPlayer } from "./eventPlayer";
import { compileReplay } from "./replayEvents";
import { fixtureEvents } from "./replayFixture";

// ---- controllable rAF + clock -------------------------------------------------

let rafCallbacks: Map<number, FrameRequestCallback>;
let rafId: number;
let now: number;

/** Advance the virtual clock by `ms` and flush one rAF frame at the new time. */
function frame(ms: number) {
  now += ms;
  const cbs = [...rafCallbacks.values()];
  rafCallbacks.clear();
  act(() => {
    for (const cb of cbs) cb(now);
  });
}

beforeEach(() => {
  rafCallbacks = new Map();
  rafId = 0;
  now = 0;
  vi.spyOn(window, "requestAnimationFrame").mockImplementation((cb) => {
    const id = ++rafId;
    rafCallbacks.set(id, cb);
    return id;
  });
  vi.spyOn(window, "cancelAnimationFrame").mockImplementation((id) => {
    rafCallbacks.delete(id as number);
  });
});

afterEach(() => vi.restoreAllMocks());

describe("useEventPlayer", () => {
  it("autoplays and reduces events as the playhead advances", () => {
    const { result } = renderHook(() => useEventPlayer(fixtureEvents));
    // Autoplay scheduled a frame; nothing reduced at t=0 beyond the first step.
    expect(result.current.isActive).toBe(true);
    expect(result.current.state.phase).toBe("streaming");

    // Drive to the end (duration is small; 8x default would also work).
    act(() => result.current.setSpeed(1));
    frame(0); // prime lastTs
    frame(result.current.durationMs + 100);

    expect(result.current.state.phase).toBe("done");
    expect(result.current.state.done?.finalDecision?.action).toBe("BUY");
    expect(result.current.isEnded).toBe(true);
    expect(result.current.isActive).toBe(false); // stops at the end
  });

  it("seek is a pure re-reduce: jumping to a time reconstructs causal state", () => {
    const { result } = renderHook(() => useEventPlayer(fixtureEvents));
    const { steps } = compileReplay(fixtureEvents);
    act(() => result.current.pause());

    // Seek to just after router completes (2nd node_complete is reporter, later).
    const routerComplete = steps.find(
      (s) => s.name === "node_complete" && s.node === "router",
    )!;
    act(() => result.current.seek(routerComplete.offsetMs));

    // Router is complete; reporter has not been reached yet.
    expect(result.current.state.nodes.router?.completedAt).not.toBeNull();
    expect(result.current.state.nodes.reporter).toBeUndefined();
    expect(result.current.state.phase).toBe("streaming");

    // Seek backwards to 0 — state collapses to just the start event.
    act(() => result.current.seek(0));
    expect(result.current.state.order).toEqual([]);
    expect(result.current.state.ticker).toBe("AAPL"); // start applied
  });

  it("speed scales how far the playhead moves per wall-frame", () => {
    const { result } = renderHook(() => useEventPlayer(fixtureEvents));
    // Quiesce the autoplay loop before measuring.
    act(() => result.current.pause());

    const advance = (speed: 1 | 2 | 4 | 8) => {
      act(() => result.current.seek(0));
      act(() => result.current.setSpeed(speed));
      act(() => result.current.play());
      frame(0); // prime lastTs at now
      frame(100); // 100ms wall-time elapses
      const t = result.current.elapsedMs;
      act(() => result.current.pause());
      return t;
    };

    const at2x = advance(2); // ~200ms virtual
    const at8x = advance(8); // ~800ms virtual
    expect(at2x).toBeGreaterThan(0);
    expect(at8x).toBeGreaterThan(at2x);
  });

  it("pause halts the playhead", () => {
    const { result } = renderHook(() => useEventPlayer(fixtureEvents));
    act(() => result.current.seek(0));
    act(() => result.current.setSpeed(1));
    act(() => result.current.play());
    frame(0);
    frame(MIN_FRAME);
    const t = result.current.elapsedMs;
    act(() => result.current.pause());
    expect(result.current.isActive).toBe(false);
    frame(1000); // a frame after pause must not advance time
    expect(result.current.elapsedMs).toBe(t);
  });

  it("step(+1/-1) lands exactly on adjacent event offsets", () => {
    const { result } = renderHook(() => useEventPlayer(fixtureEvents));
    const { steps } = compileReplay(fixtureEvents);
    act(() => result.current.pause());
    act(() => result.current.seek(0));

    act(() => result.current.step(1));
    expect(result.current.elapsedMs).toBe(steps[1]!.offsetMs);

    act(() => result.current.step(-1));
    expect(result.current.elapsedMs).toBe(steps[0]!.offsetMs);
  });

  it("seek during playback keeps the playhead advancing (no freeze)", () => {
    const { result } = renderHook(() => useEventPlayer(fixtureEvents));
    act(() => result.current.setSpeed(1));
    frame(0); // prime the autoplay loop
    frame(100);
    expect(result.current.isActive).toBe(true);

    act(() => result.current.seek(900));
    expect(result.current.elapsedMs).toBe(900);
    expect(result.current.isActive).toBe(true); // UI still says "playing"…

    // …so the playhead must keep moving after the scrub.
    frame(0); // surviving rAF tick re-primes the wall delta
    expect(result.current.elapsedMs).toBe(900);
    frame(100);
    expect(result.current.elapsedMs).toBeCloseTo(1000, 5);
    frame(100);
    expect(result.current.elapsedMs).toBeCloseTo(1100, 5);
  });

  it("restart during playback replays from 0 without pausing", () => {
    const { result } = renderHook(() => useEventPlayer(fixtureEvents));
    act(() => result.current.setSpeed(1));
    frame(0);
    frame(500);
    expect(result.current.elapsedMs).toBeGreaterThan(0);
    expect(result.current.isActive).toBe(true);

    act(() => result.current.restart());
    expect(result.current.elapsedMs).toBe(0);
    expect(result.current.isActive).toBe(true);

    // The loop keeps running and re-advances from the start.
    frame(0); // re-prime
    frame(100);
    expect(result.current.elapsedMs).toBeCloseTo(100, 5);
    expect(result.current.state.phase).toBe("streaming");
  });

  it("keeps state identity stable across frames when no new event is due", () => {
    const { result } = renderHook(() => useEventPlayer(fixtureEvents));
    act(() => result.current.pause());
    // Steps land every 420ms (MIN_STEP cadence); park between the 3rd (840)
    // and 4th (1260) steps, then advance frames that pass no event.
    act(() => result.current.seek(850));
    act(() => result.current.setSpeed(1));
    act(() => result.current.play());
    frame(0); // prime
    frame(100); // 950ms — still before the next step
    const before = result.current.state;
    frame(100); // 1050ms — still before the next step
    expect(result.current.elapsedMs).toBeCloseTo(1050, 5);
    expect(result.current.state).toBe(before); // identity stable: no re-reduce

    frame(400); // 1450ms — the 4th step (1260) lands
    expect(result.current.state).not.toBe(before);
    act(() => result.current.pause());
  });

  it("restart returns to the start and resumes playing", () => {
    const { result } = renderHook(() => useEventPlayer(fixtureEvents));
    act(() => result.current.seek(result.current.durationMs)); // to the end
    expect(result.current.isEnded).toBe(true);

    act(() => result.current.restart());
    expect(result.current.elapsedMs).toBe(0);
    expect(result.current.isActive).toBe(true);
  });

  it("exposes phase-tickable node_complete offsets for the scrubber", () => {
    const { result } = renderHook(() => useEventPlayer(fixtureEvents));
    expect(result.current.stageTicks.map((t) => t.node)).toEqual([
      "router",
      "reporter",
    ]);
  });

  it("recordedElapsedMs tracks the ORIGINAL run's timing at the playhead", () => {
    // The replay elapsed bug: mid-replay the cockpit showed raw epoch seconds
    // because state stamps are synthetic fold ticks. The player must expose the
    // recorded run's own elapsed (ts_ms deltas) at the playhead instead.
    const { result } = renderHook(() => useEventPlayer(fixtureEvents));
    const { steps } = compileReplay(fixtureEvents);
    act(() => result.current.pause());

    // Park just after router completes — recorded ts 1020 vs first ts 1000.
    const routerComplete = steps.find(
      (s) => s.name === "node_complete" && s.node === "router",
    )!;
    act(() => result.current.seek(routerComplete.offsetMs));
    expect(result.current.recordedElapsedMs).toBe(20);

    // At the end of the timeline: the whole recorded run took 60ms.
    act(() => result.current.seek(result.current.durationMs));
    expect(result.current.recordedElapsedMs).toBe(60);

    // Back at the start: only the first event is due — zero elapsed.
    act(() => result.current.seek(0));
    expect(result.current.recordedElapsedMs).toBe(0);
  });

  it("handles an empty timeline without scheduling a loop", () => {
    const { result } = renderHook(() => useEventPlayer([]));
    expect(result.current.durationMs).toBe(0);
    expect(result.current.isActive).toBe(false);
    expect(result.current.progress).toBe(0);
  });
});

const MIN_FRAME = 50;

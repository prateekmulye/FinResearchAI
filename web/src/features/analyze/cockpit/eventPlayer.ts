/**
 * eventPlayer.ts — the WP-8 REPLAY DRIVER (implemented).
 *
 * The cockpit is a pure function of `AnalysisStreamState`. Two drivers produce
 * that state:
 *   1. LIVE   — useAnalysisStream reduces a real SSE stream.
 *   2. REPLAY — useEventPlayer (here) reduces a recorded RunDetail.events[] list
 *               through the SAME reducer (analysisReducer), on a timer, to
 *               re-create the exact live trajectory at playback speed.
 *
 * Because both terminate in identical state, <Cockpit/> never knows which one is
 * driving it. CockpitDriver captures the `{state, isActive}` equivalence.
 *
 * Design notes:
 *   - SEEK is a pure re-reduce: fold every step whose synthetic offset <= target
 *     time from the initial state. The reducer is cheap and pure, so scrubbing is
 *     instant — and visually correct, because seeking reproduces the *causal*
 *     accumulation (cost ticker, node statuses, deltas) rather than interpolating.
 *   - The wall clock is virtualised: we track elapsed playback ms (advanced while
 *     playing, scaled by speed) and derive which steps are "due". One rAF-paced
 *     loop drives both the visible time and the dispatch, so pause/resume/seek
 *     never desync.
 *   - analysisClock is monkeypatched to a deterministic counter during a folded
 *     re-reduce so node lifecycle stamps stay ordered without wall-clock drift.
 */
import { useCallback, useEffect, useMemo, useRef, useState } from "react";

import {
  analysisClock,
  initialState,
  reducer,
  type AnalysisStreamState,
} from "@/hooks/analysisReducer";
import type { UseAnalysisStream } from "@/hooks/useAnalysisStream";
import type { ReplayEvent } from "@/lib/api";

import {
  compileReplay,
  recordedNodeLatencies,
  type ReplayStep,
} from "./replayEvents";

/** Speeds the transport offers (Hick's Law: a small, tappable set). */
export const REPLAY_SPEEDS = [1, 2, 4, 8] as const;
export type ReplaySpeed = (typeof REPLAY_SPEEDS)[number];

/** The control surface a replay driver exposes to the cockpit + transport bar. */
export interface EventPlayerControls {
  state: AnalysisStreamState;
  isActive: boolean;
  /** True once the playhead has reached the end of the recorded timeline. */
  isEnded: boolean;
  play: () => void;
  pause: () => void;
  /** Jump to an absolute synthetic time (ms); clamps to [0, duration]. */
  seek: (timeMs: number) => void;
  /** Jump to 0..1 progress through the recorded timeline. */
  seekProgress: (progress: number) => void;
  /** Step exactly one recorded event forward/back (arrow-key seeking). */
  step: (direction: 1 | -1) => void;
  restart: () => void;
  setSpeed: (multiplier: ReplaySpeed) => void;
  speed: ReplaySpeed;
  /** Current playhead time (ms) and total duration (ms), synthetic 1x scale. */
  elapsedMs: number;
  durationMs: number;
  /**
   * How many decoded steps the timeline holds. THE emptiness signal: a
   * single-event run has stepCount 1 but durationMs 0 (offsets are gaps), so
   * "is there anything to replay?" must never key on durationMs.
   */
  stepCount: number;
  /**
   * Elapsed ms in the ORIGINAL recorded run at the playhead (the recorded
   * ts_ms delta of the last due event). The cockpit's ELAPSED readout shows
   * this during replay — the run's own timing, never the playback wall clock
   * (replay state stamps are synthetic fold ticks; subtracting them from
   * Date.now() renders raw epoch seconds).
   */
  recordedElapsedMs: number;
  /**
   * Per-node latency (s) from the recorded run's own ts_ms deltas, for the
   * transcript — replay state stamps are synthetic and must not be subtracted.
   */
  recordedNodeLatencies: Record<string, number>;
  /** 0..1 progress, for the scrubber fill. */
  progress: number;
  /** Stage ticks (node_complete offsets) for the pipeline-mapped scrubber. */
  stageTicks: { offsetMs: number; node: string }[];
}

/**
 * The cockpit accepts EITHER the live stream hook OR a replay player — both
 * expose `{ state, isActive }`, which is all the cockpit reads.
 */
export type CockpitDriver = Pick<
  UseAnalysisStream | EventPlayerControls,
  "state" | "isActive"
>;

/** Fold the first `count` steps into a fresh state (the pure seek core). */
function reduceFirstN(steps: ReplayStep[], count: number): AnalysisStreamState {
  // Deterministic, ordered lifecycle stamps during the fold (no wall clock).
  const real = analysisClock.now;
  let tick = 0;
  analysisClock.now = () => ++tick;
  try {
    let state = initialState;
    for (let i = 0; i < count && i < steps.length; i++) {
      state = reducer(state, { kind: "event", event: steps[i]!.event });
    }
    return state;
  } finally {
    analysisClock.now = real;
  }
}

type PlayerState = { steps: ReplayStep[]; durationMs: number; timeMs: number };

export function useEventPlayer(events: readonly ReplayEvent[]): EventPlayerControls {
  const { steps, durationMs } = useMemo(() => compileReplay(events), [events]);

  // `timeMs` is the source of truth; `state` is derived from it on every tick.
  const [timeMs, setTimeMs] = useState(0);
  const [speed, setSpeedState] = useState<ReplaySpeed>(4);
  const [playing, setPlaying] = useState(false);

  // How many steps are due at the playhead. Memoising the COUNT (not the raw
  // time) means the derived state's identity only changes when an event
  // actually lands — not on every rAF frame — so the cockpit doesn't re-render
  // per frame while the transport alone tracks the raw playhead.
  const dueCount = useMemo(() => {
    let n = 0;
    for (const s of steps) {
      if (s.offsetMs > timeMs) break;
      n += 1;
    }
    return n;
  }, [steps, timeMs]);

  // Derived render state — a pure fold of the due steps (re-runs per event).
  const state = useMemo(() => reduceFirstN(steps, dueCount), [steps, dueCount]);

  // The original run's elapsed at the playhead — advances stepwise as recorded
  // events land (same collision-driven cadence as the cost ticker's totals).
  const recordedElapsedMs =
    dueCount > 0 ? steps[dueCount - 1]!.recordedOffsetMs : 0;

  const rafRef = useRef<number | null>(null);
  const lastTsRef = useRef<number | null>(null);
  // Hold the latest time/speed/duration for the rAF loop without re-subscribing.
  const ctl = useRef<PlayerState & { speed: ReplaySpeed }>({
    steps,
    durationMs,
    timeMs,
    speed,
  });
  ctl.current.steps = steps;
  ctl.current.durationMs = durationMs;
  ctl.current.timeMs = timeMs;
  ctl.current.speed = speed;

  const stopLoop = useCallback(() => {
    if (rafRef.current != null) cancelAnimationFrame(rafRef.current);
    rafRef.current = null;
    lastTsRef.current = null;
  }, []);


  // The single rAF loop: advance virtual time by wall-delta * speed while playing.
  const tick = useCallback(
    (ts: number) => {
      if (lastTsRef.current == null) lastTsRef.current = ts;
      const wallDelta = ts - lastTsRef.current;
      lastTsRef.current = ts;

      const next = ctl.current.timeMs + wallDelta * ctl.current.speed;
      if (next >= ctl.current.durationMs) {
        setTimeMs(ctl.current.durationMs);
        setPlaying(false);
        stopLoop();
        return;
      }
      setTimeMs(next);
      rafRef.current = requestAnimationFrame(tick);
    },
    [stopLoop],
  );

  const play = useCallback(() => {
    // Replaying from the end restarts (Peak-End: re-watch is one tap).
    if (ctl.current.timeMs >= ctl.current.durationMs) setTimeMs(0);
    setPlaying(true);
  }, []);

  const pause = useCallback(() => {
    setPlaying(false);
    stopLoop();
  }, [stopLoop]);

  const seek = useCallback((t: number) => {
    // Do NOT cancel the rAF loop here: while playing, the loop must survive a
    // scrub (the effect only re-arms it when `playing` flips, so cancelling
    // would freeze the playhead with the UI still saying "Pause"). Nulling
    // lastTs makes the surviving tick re-prime its wall delta and read the new
    // playhead time — which also lets restart() rewind mid-playback.
    lastTsRef.current = null;
    setTimeMs(Math.max(0, Math.min(ctl.current.durationMs, t)));
  }, []);

  const seekProgress = useCallback(
    (p: number) => seek(p * ctl.current.durationMs),
    [seek],
  );

  const step = useCallback(
    (direction: 1 | -1) => {
      const s = ctl.current.steps;
      const now = ctl.current.timeMs;
      if (direction > 0) {
        const nxt = s.find((x) => x.offsetMs > now + 0.5);
        seek(nxt ? nxt.offsetMs : ctl.current.durationMs);
      } else {
        // Land just past the previous step so its reduction is included.
        let target = 0;
        for (const x of s) {
          if (x.offsetMs < now - 0.5) target = x.offsetMs;
          else break;
        }
        seek(target);
      }
    },
    [seek],
  );

  const restart = useCallback(() => {
    seek(0);
    setPlaying(true);
  }, [seek]);

  const setSpeed = useCallback((m: ReplaySpeed) => setSpeedState(m), []);

  // Drive the loop on/off as `playing` flips.
  useEffect(() => {
    if (playing) {
      lastTsRef.current = null;
      rafRef.current = requestAnimationFrame(tick);
      return () => stopLoop();
    }
    return undefined;
  }, [playing, tick, stopLoop]);

  // Autoplay once events are loaded (the recruiter shouldn't have to hunt for
  // play). Honoured only on first mount with a non-empty timeline.
  const didAutoplay = useRef(false);
  useEffect(() => {
    if (!didAutoplay.current && durationMs > 0) {
      didAutoplay.current = true;
      setPlaying(true);
    }
  }, [durationMs]);

  const stageTicks = useMemo(
    () =>
      steps
        .filter((s) => s.name === "node_complete" && s.node)
        .map((s) => ({ offsetMs: s.offsetMs, node: s.node! })),
    [steps],
  );

  // Stable identity per timeline — Cockpit is memo'd against this prop.
  const nodeLatencies = useMemo(() => recordedNodeLatencies(steps), [steps]);

  const isEnded = durationMs > 0 && timeMs >= durationMs;

  return {
    state,
    isActive: playing,
    isEnded,
    play,
    pause,
    seek,
    seekProgress,
    step,
    restart,
    setSpeed,
    speed,
    elapsedMs: timeMs,
    durationMs,
    stepCount: steps.length,
    recordedElapsedMs,
    recordedNodeLatencies: nodeLatencies,
    progress: durationMs > 0 ? timeMs / durationMs : 0,
    stageTicks,
  };
}

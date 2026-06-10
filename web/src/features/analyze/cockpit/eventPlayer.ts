/**
 * eventPlayer.ts — the WP-8 REPLAY SEAM (interface only; the player is WP-8).
 *
 * The cockpit is a pure function of `AnalysisStreamState`. There are exactly two
 * ways that state gets produced:
 *
 *   1. LIVE   — `useAnalysisStream()` runs POST /api/analyze and reduces its SSE
 *               frames into state. This is what WP-7 wires up.
 *
 *   2. REPLAY — WP-8 will take a recorded `RunDetail.events[]` (from
 *               GET /api/runs/{id}) and feed them through the SAME reducer, on a
 *               timer, to re-create the exact live trajectory at playback speed.
 *
 * Because both paths terminate in identical `AnalysisStreamState`, the cockpit
 * component tree never needs to know which one is driving it. The contract below
 * is the only thing WP-8 must satisfy: produce an `AnalysisStreamState` (plus the
 * same control surface the live hook exposes) and hand it to <Cockpit/>.
 *
 * WP-8 implementation sketch (do NOT build here):
 *   - reuse the reducer from useAnalysisStream (extract it if needed),
 *   - map each ReplayEvent -> an AnalysisEvent (the `name`/`data` shape from the
 *     recorder maps 1:1 onto the SSE event union),
 *   - dispatch them on a setInterval/raf scheduled by `ts_ms` deltas * (1/speed),
 *   - expose play/pause/seek/setSpeed; `state` stays the same shape.
 */
import type {
  AnalysisStreamState,
  UseAnalysisStream,
} from "@/hooks/useAnalysisStream";
import type { ReplayEvent } from "@/lib/api";

/** The control surface a replay driver must expose to the cockpit. */
export interface EventPlayerControls {
  state: AnalysisStreamState;
  isActive: boolean;
  play: () => void;
  pause: () => void;
  /** 0..1 progress through the recorded timeline. */
  seek: (progress: number) => void;
  setSpeed: (multiplier: number) => void;
}

/**
 * The cockpit accepts EITHER the live stream hook's return OR a replay player's
 * controls — both expose `{ state, isActive }`, which is all the cockpit reads.
 * This alias documents that equivalence so the page can be driven by either.
 */
export type CockpitDriver = Pick<
  UseAnalysisStream | EventPlayerControls,
  "state" | "isActive"
>;

/**
 * WP-8 will implement this. Kept as a typed stub so the seam is real and
 * type-checked today; calling it throws to make accidental use obvious.
 */
export function useEventPlayer(_events: ReplayEvent[]): EventPlayerControls {
  throw new Error(
    "useEventPlayer is a WP-8 seam stub — the replay player is not built yet.",
  );
}

/**
 * ConvictionGauge — a radial 0..1 gauge for the verdict reveal.
 *
 * An SVG arc whose stroke sweeps in via stroke-dashoffset (NLM: 350ms,
 * cubic-bezier(.16,1,.3,1)). The arc is tinted by the action (BUY/SELL/HOLD)
 * signal color, and the conviction percentage counts up in the center, sharing
 * the same rAF discipline as the score. Reduced-motion shows the final arc and
 * value with no sweep.
 */
import { useEffect, useRef } from "react";

import type { Action } from "@/lib/api";
import { useReducedMotion } from "@/hooks/useReducedMotion";

import { useCountUp } from "./useCountUp";

const TINT: Record<Action, string> = {
  BUY: "var(--color-bull)",
  SELL: "var(--color-bear)",
  HOLD: "var(--color-hold)",
};

const R = 52;
const CIRC = 2 * Math.PI * R;
// We draw a 270° gauge (¾ circle), leaving a gap at the bottom.
const SWEEP = 0.75;
const TRACK_LEN = CIRC * SWEEP;

export function ConvictionGauge({
  conviction,
  action,
  active,
}: {
  conviction: number; // 0..1
  action: Action;
  active: boolean;
}) {
  const reduced = useReducedMotion();
  const arcRef = useRef<SVGCircleElement | null>(null);
  const clamped = Math.max(0, Math.min(1, conviction));
  const pct = Math.round(clamped * 100);
  const valueRef = useCountUp(pct, { duration: 350, active });

  useEffect(() => {
    const arc = arcRef.current;
    if (!arc) return;
    const filled = TRACK_LEN * clamped;
    if (!active) {
      arc.style.strokeDashoffset = String(TRACK_LEN);
      return;
    }
    if (reduced) {
      arc.style.transition = "none";
      arc.style.strokeDashoffset = String(TRACK_LEN - filled);
      return;
    }
    // Start empty, then sweep to filled on the next frame so the transition runs.
    arc.style.transition = "none";
    arc.style.strokeDashoffset = String(TRACK_LEN);
    const raf = requestAnimationFrame(() => {
      arc.style.transition =
        "stroke-dashoffset 350ms cubic-bezier(0.16, 1, 0.3, 1)";
      arc.style.strokeDashoffset = String(TRACK_LEN - filled);
    });
    return () => cancelAnimationFrame(raf);
  }, [clamped, active, reduced]);

  return (
    <div className="relative grid size-32 shrink-0 place-items-center">
      <svg
        viewBox="0 0 128 128"
        className="size-32 -rotate-[135deg]"
        aria-hidden="true"
      >
        {/* track */}
        <circle
          cx="64"
          cy="64"
          r={R}
          fill="none"
          stroke="var(--color-line-strong)"
          strokeWidth="8"
          strokeLinecap="round"
          strokeDasharray={`${TRACK_LEN} ${CIRC}`}
        />
        {/* filled arc */}
        <circle
          ref={arcRef}
          cx="64"
          cy="64"
          r={R}
          fill="none"
          stroke={TINT[action]}
          strokeWidth="8"
          strokeLinecap="round"
          strokeDasharray={`${TRACK_LEN} ${CIRC}`}
          strokeDashoffset={TRACK_LEN}
          style={{ filter: `drop-shadow(0 0 6px ${TINT[action]})` }}
        />
      </svg>
      <div className="absolute flex flex-col items-center">
        <span
          ref={valueRef}
          className="font-mono text-2xl font-semibold tabular-nums text-[var(--color-fg)]"
          style={{ willChange: "contents" }}
        >
          0
        </span>
        <span className="font-mono text-2xs uppercase tracking-[0.18em] text-[var(--color-fg-subtle)]">
          conviction
        </span>
      </div>
    </div>
  );
}

/**
 * useCountUp — animate a number from 0 to `target` over `duration` ms using a
 * single requestAnimationFrame loop. The count is driven OUTSIDE React's render
 * cycle (we ref the DOM node and write textContent directly per frame), so a
 * 0->100 ramp stays at 60fps and never triggers a re-render storm (NLM:
 * "bypass framework re-render cycles via direct DOM manipulation").
 *
 * Returns a ref to attach to the element whose text should count up. Respects
 * prefers-reduced-motion: when reduced, it writes the final value immediately.
 */
import { useEffect, useRef } from "react";

import { useReducedMotion } from "@/hooks/useReducedMotion";

const EASE_OUT = (t: number) => 1 - Math.pow(1 - t, 3); // cubic-bezier(.16,1,.3,1)-ish

// Module-scope so the default keeps a stable identity: an inline default would
// be a fresh function every render and re-fire the effect (it deps on format).
const defaultFormat = (n: number) => String(Math.round(n));

export function useCountUp(
  target: number,
  options: { duration?: number; active?: boolean; format?: (n: number) => string } = {},
) {
  const { duration = 300, active = true, format = defaultFormat } = options;
  const ref = useRef<HTMLSpanElement | null>(null);
  const reduced = useReducedMotion();

  useEffect(() => {
    const el = ref.current;
    if (!el) return;
    if (!active) {
      el.textContent = format(0);
      return;
    }
    if (reduced) {
      el.textContent = format(target);
      return;
    }

    let raf = 0;
    const start = performance.now();
    const tick = (now: number) => {
      const t = Math.min(1, (now - start) / duration);
      el.textContent = format(target * EASE_OUT(t));
      if (t < 1) raf = requestAnimationFrame(tick);
      else el.textContent = format(target);
    };
    raf = requestAnimationFrame(tick);
    return () => cancelAnimationFrame(raf);
  }, [target, duration, active, reduced, format]);

  return ref;
}

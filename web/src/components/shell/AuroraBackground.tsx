import { useReducedMotion } from "@/hooks/useReducedMotion";

/**
 * AuroraBackground — the restrained animated backdrop behind the glass shell.
 *
 * Two large, blurred radial-gradient blobs drifting on a very slow rotation,
 * plus a fixed grid-lattice overlay (terminal-energy) and the global grain. It
 * is `fixed`, GPU-composited (transform/opacity only), and fully static under
 * prefers-reduced-motion. No per-frame JS — the animation lives in CSS keyframes
 * so it costs the main thread nothing.
 */
export function AuroraBackground() {
  const reduced = useReducedMotion();

  return (
    <div
      aria-hidden="true"
      className="pointer-events-none fixed inset-0 -z-10 overflow-hidden bg-[var(--color-base)]"
    >
      {/* Aurora blob — azure, top-left drift */}
      <div
        className="absolute -left-[15%] -top-[20%] size-[55vw] rounded-full opacity-[0.18] blur-[80px]"
        style={{
          background:
            "radial-gradient(circle, oklch(65% 0.16 245) 0%, transparent 65%)",
          animation: reduced ? "none" : "fin-aurora 64s linear infinite",
        }}
      />
      {/* Aurora blob — bull-green, bottom-right, counter-drift */}
      <div
        className="absolute -bottom-[25%] -right-[10%] size-[50vw] rounded-full opacity-[0.13] blur-[90px]"
        style={{
          background:
            "radial-gradient(circle, oklch(70% 0.14 162) 0%, transparent 65%)",
          animation: reduced ? "none" : "fin-aurora 88s linear infinite reverse",
        }}
      />
      {/* Subtle warm ember — anchors the palette, never moves */}
      <div
        className="absolute left-[40%] top-[55%] size-[30vw] rounded-full opacity-[0.07] blur-[100px]"
        style={{
          background: "radial-gradient(circle, oklch(80% 0.15 78) 0%, transparent 70%)",
        }}
      />

      {/* Terminal lattice: a faint grid that reads as a data-surface substrate.
          Masked to fade toward the edges so it never competes with content. */}
      <div
        className="absolute inset-0 opacity-[0.5]"
        style={{
          backgroundImage:
            "linear-gradient(to right, oklch(100% 0 0 / 3%) 1px, transparent 1px)," +
            "linear-gradient(to bottom, oklch(100% 0 0 / 3%) 1px, transparent 1px)",
          backgroundSize: "64px 64px",
          maskImage:
            "radial-gradient(ellipse 80% 60% at 50% 40%, black 30%, transparent 80%)",
          WebkitMaskImage:
            "radial-gradient(ellipse 80% 60% at 50% 40%, black 30%, transparent 80%)",
        }}
      />

      {/* Vignette to seat the glass cards against a darker frame */}
      <div
        className="absolute inset-0"
        style={{
          background:
            "radial-gradient(ellipse 120% 90% at 50% 0%, transparent 40%, oklch(8% 0.01 260 / 60%) 100%)",
        }}
      />
    </div>
  );
}

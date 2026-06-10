import { cn } from "@/lib/utils";

/**
 * Original mark: a candlestick-meets-node glyph. A vertical wick with a body and
 * two satellite agent-nodes — equity data + multi-agent graph in one shape. No
 * third-party logo, fully inline SVG. The wordmark sets "FinResearch" in tight
 * Inter with the "Research" half dimmed for an editorial two-tone.
 */
export function Wordmark({ className }: { className?: string }) {
  return (
    <span className={cn("inline-flex items-center gap-2.5", className)}>
      <svg
        width="22"
        height="22"
        viewBox="0 0 24 24"
        fill="none"
        aria-hidden="true"
        className="shrink-0"
      >
        {/* candle wick */}
        <line
          x1="12"
          y1="2.5"
          x2="12"
          y2="21.5"
          stroke="var(--color-fg-muted)"
          strokeWidth="1.25"
          strokeLinecap="round"
        />
        {/* candle body */}
        <rect
          x="8.5"
          y="7.5"
          width="7"
          height="9"
          rx="1.6"
          fill="var(--color-accent)"
        />
        {/* satellite agent nodes */}
        <circle cx="4" cy="9" r="2" fill="var(--color-bull)" />
        <circle cx="20" cy="15" r="2" fill="var(--color-hold)" />
      </svg>
      <span className="text-[0.95rem] font-semibold tracking-tight">
        <span className="text-[var(--color-fg)]">Fin</span>
        <span className="text-[var(--color-fg-muted)]">Research</span>
      </span>
    </span>
  );
}

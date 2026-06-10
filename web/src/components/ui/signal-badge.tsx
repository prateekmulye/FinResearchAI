import { ArrowDownRight, ArrowUpRight, Minus } from "lucide-react";

import { type Action } from "@/lib/api";
import { cn } from "@/lib/utils";

const CONFIG: Record<
  Action,
  { tint: string; dim: string; Icon: typeof Minus; label: string }
> = {
  BUY: {
    tint: "var(--color-bull)",
    dim: "var(--color-bull-dim)",
    Icon: ArrowUpRight,
    label: "BUY",
  },
  SELL: {
    tint: "var(--color-bear)",
    dim: "var(--color-bear-dim)",
    Icon: ArrowDownRight,
    label: "SELL",
  },
  HOLD: {
    tint: "var(--color-hold)",
    dim: "var(--color-hold-dim)",
    Icon: Minus,
    label: "HOLD",
  },
};

/**
 * SignalBadge — the verdict chip. Color carries meaning but never alone: an
 * arrow glyph + the literal word back it up (Von Restorff isolation + a11y).
 * Mono label, tabular score. `size="lg"` is the hero verdict on the cockpit.
 */
export function SignalBadge({
  action,
  score,
  size = "md",
  className,
}: {
  action: Action;
  score?: number;
  size?: "sm" | "md" | "lg";
  className?: string;
}) {
  const cfg = CONFIG[action];
  return (
    <span
      className={cn(
        "inline-flex items-center gap-1.5 rounded-full font-mono font-semibold tracking-tight",
        size === "sm" && "px-2 py-0.5 text-2xs",
        size === "md" && "px-3 py-1 text-xs",
        size === "lg" && "px-4 py-1.5 text-sm",
        className,
      )}
      style={{
        color: cfg.tint,
        background: cfg.dim,
        border: `1px solid ${cfg.tint}`,
      }}
    >
      <cfg.Icon
        className={cn(size === "lg" ? "size-4" : "size-3")}
        aria-hidden="true"
      />
      {cfg.label}
      {score != null && (
        <span className="text-[var(--color-fg)] opacity-80">· {score}</span>
      )}
    </span>
  );
}

/**
 * panelKit — shared primitives for the cockpit intelligence panels.
 *
 * A terminal tile (the dense data surface that lives INSIDE the glass cockpit),
 * a node status dot, a confidence chip, and an auto-scrolling token stream.
 * Every numeric stays mono + tabular; status colour is always backed by a glyph
 * (DESIGN.md §7).
 */
import { Check, Loader2, Minus, X } from "lucide-react";
import { type ReactNode, useEffect, useRef } from "react";

import { cn } from "@/lib/utils";

import type { NodeStatus } from "./pipeline";

/** A status dot + optional label. Glyph carries the meaning, never colour alone. */
export function StatusDot({ status }: { status: NodeStatus }) {
  if (status === "complete")
    return <Check className="size-3.5 text-[var(--color-bull)]" aria-hidden="true" />;
  if (status === "error")
    return <X className="size-3.5 text-[var(--color-hold)]" aria-hidden="true" />;
  if (status === "running")
    return (
      <Loader2
        className="size-3.5 animate-spin text-[var(--color-accent)]"
        aria-hidden="true"
      />
    );
  return <Minus className="size-3.5 text-[var(--color-fg-subtle)]" aria-hidden="true" />;
}

/** Terminal tile container with a mono header row and a coloured accent edge. */
export function Tile({
  title,
  phase,
  status,
  accent,
  children,
  className,
  flash,
}: {
  title: string;
  phase?: string;
  status: NodeStatus;
  accent?: string;
  children: ReactNode;
  className?: string;
  /** When true (a fresh completion), pulse the luminous-accent flash. */
  flash?: boolean;
}) {
  return (
    <div
      className={cn(
        "terminal-tile flex flex-col p-3.5",
        flash && status === "complete" && "animate-accent-flash",
        className,
      )}
      style={{
        transformOrigin: "center",
        borderColor:
          status === "complete" || status === "running"
            ? (accent ?? "var(--color-line-strong)")
            : "var(--color-line)",
      }}
    >
      <div className="mb-2 flex items-center gap-2">
        <StatusDot status={status} />
        <span className="flex-1 truncate text-sm font-medium text-[var(--color-fg)]">
          {title}
        </span>
        {phase && (
          <span className="font-mono text-[9px] uppercase tracking-[0.16em] text-[var(--color-fg-subtle)]">
            {phase}
          </span>
        )}
      </div>
      {children}
    </div>
  );
}

/** A 0..1 confidence chip rendered as a percentage. */
export function ConfidenceChip({ value }: { value: number | null }) {
  if (value == null) return null;
  return (
    <span className="inline-flex items-center gap-1 rounded-full border border-[var(--color-line-strong)] bg-[var(--color-surface-2)] px-2 py-0.5 font-mono text-2xs tabular-nums text-[var(--color-fg-muted)]">
      conf <span className="text-[var(--color-fg)]">{Math.round(value * 100)}%</span>
    </span>
  );
}

/**
 * Auto-scrolling mono token stream. Older lines fade at the top (CSS mask).
 * Pins to the bottom as new tokens arrive so the freshest text stays visible.
 */
export function TokenStream({ text, lines = 4 }: { text: string; lines?: number }) {
  const ref = useRef<HTMLDivElement | null>(null);
  useEffect(() => {
    const el = ref.current;
    if (el) el.scrollTop = el.scrollHeight;
  }, [text]);
  return (
    <div
      ref={ref}
      className="token-stream overflow-hidden font-mono text-xs leading-relaxed text-[var(--color-fg-muted)]"
      style={{ maxHeight: `${lines * 1.1}rem` }}
    >
      {text}
      <span className="ml-0.5 inline-block w-1.5 animate-pulse text-[var(--color-accent)]">
        ▍
      </span>
    </div>
  );
}

/** Evidence bullet list that rises into place (word-stream materialization). */
export function KeyPoints({ points }: { points: string[] }) {
  if (points.length === 0) return null;
  return (
    <ul className="mt-2 space-y-1">
      {points.map((p, i) => (
        <li
          key={i}
          className="animate-rise-in flex gap-1.5 text-xs text-[var(--color-fg-muted)]"
          style={{ animationDelay: `${i * 60}ms` }}
        >
          <span className="mt-1.5 size-1 shrink-0 rounded-full bg-[var(--color-accent)]" />
          <span>{p}</span>
        </li>
      ))}
    </ul>
  );
}

/**
 * marketChips — the small terminal-tile atoms shared across the explorer lanes
 * and the dossier header: the exchange chip, the "watched" indicator dot, and
 * the kind chip (news | run) for research-memory hits. Mono everywhere (these
 * IS data), signal color always backed by a glyph or word per DESIGN.md §2.
 */
import { Eye, FileText, Newspaper } from "lucide-react";

import { cn } from "@/lib/utils";

/** Exchange code in a hairline pill — the venue an instrument trades on. */
export function ExchangeChip({
  exchange,
  className,
}: {
  exchange: string;
  className?: string;
}) {
  return (
    <span
      className={cn(
        "inline-flex items-center rounded-full border border-[var(--color-line)] px-2 py-0.5",
        "font-mono text-2xs uppercase tracking-wide text-[var(--color-fg-subtle)]",
        className,
      )}
    >
      {exchange}
    </span>
  );
}

/**
 * WatchedDot — a small bull-green dot when an instrument is on the watchlist
 * (the system has analyzed it before, so data is backfilled). Color is backed
 * by an accessible label; absent state renders a hollow ring so the column
 * still aligns (Gestalt continuity) without implying "watched".
 */
export function WatchedDot({ watched }: { watched: boolean }) {
  return (
    <span
      className="inline-flex size-2.5 shrink-0 items-center justify-center"
      role="img"
      aria-label={watched ? "On watchlist" : "Not watched"}
      title={watched ? "On watchlist" : "Not watched"}
    >
      <span
        className={cn(
          "size-2 rounded-full",
          watched
            ? "bg-[var(--color-bull)] shadow-[0_0_6px_var(--color-bull)]"
            : "border border-[var(--color-line-strong)]",
        )}
      />
    </span>
  );
}

/** kind chip for a research-memory hit — news (external) vs run (internal). */
export function KindChip({ kind }: { kind: "news" | "run" }) {
  const cfg =
    kind === "news"
      ? { Icon: Newspaper, label: "news", tint: "var(--color-fg-muted)" }
      : { Icon: FileText, label: "run", tint: "var(--color-accent)" };
  return (
    <span
      className="inline-flex items-center gap-1 rounded-full border border-[var(--color-line)] px-2 py-0.5 font-mono text-2xs lowercase tracking-wide"
      style={{ color: cfg.tint }}
    >
      <cfg.Icon className="size-3" aria-hidden="true" />
      {cfg.label}
    </span>
  );
}

/** "watched" word-chip for the dossier header (more legible than a bare dot). */
export function WatchedChip({ watched }: { watched: boolean }) {
  if (!watched) return null;
  return (
    <span
      className="inline-flex items-center gap-1 rounded-full px-2 py-0.5 font-mono text-2xs lowercase tracking-wide"
      style={{
        color: "var(--color-bull)",
        background: "var(--color-bull-dim)",
        border: "1px solid var(--color-bull)",
      }}
    >
      <Eye className="size-3" aria-hidden="true" />
      watched
    </span>
  );
}

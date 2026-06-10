/**
 * RunRail — the eval-run selector. A horizontal rail of glass run cards
 * (newest-first), each a label + relative timestamp + an n_tickers chip. The
 * active run lifts and gets an accent rail; selecting one writes ?label= to the
 * URL so a run is deep-linkable (the same URL-as-source-of-truth idiom the
 * library and market screens use). Hick's Law: a finite, scannable rail beats a
 * dropdown that hides the comparison set.
 */
import { Link } from "react-router";

import type { EvalResult } from "@/lib/api";
import { cn } from "@/lib/utils";
import { formatRelativeTime } from "@/lib/utils";

export function RunRail({
  runs,
  activeLabel,
}: {
  runs: EvalResult[];
  /** The label currently selected (from ?label=), or the newest by default. */
  activeLabel: string;
}) {
  return (
    <div>
      <p className="mb-2 px-1 font-mono text-2xs font-medium uppercase tracking-[0.18em] text-[var(--color-accent)]">
        Eval runs
        <span className="ml-2 tabular-nums text-[var(--color-fg-subtle)]">
          {runs.length}
        </span>
      </p>
      <ul
        className="flex snap-x gap-3 overflow-x-auto pb-2"
        aria-label="Stored eval runs, newest first"
      >
        {runs.map((run) => {
          const active = run.label === activeLabel;
          const nTickers =
            typeof run.summary?.n_tickers === "number"
              ? run.summary.n_tickers
              : null;
          return (
            <li key={run.id} className="snap-start">
              <Link
                to={`/eval?label=${encodeURIComponent(run.label)}`}
                aria-current={active ? "true" : undefined}
                className={cn(
                  // The card IS the focus target, so the ring lives right here
                  // (house pattern: LibraryRow restores it via group-* on the
                  // inner card; there is no inner card to delegate to).
                  "group flex min-w-[10.5rem] flex-col gap-1.5 rounded-xl border p-3 transition-[transform,border-color,box-shadow] duration-[200ms] ease-[var(--ease-spring)] focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-[var(--color-accent)]",
                  active
                    ? "glass-strong -translate-y-0.5 shadow-[var(--shadow-raised)]"
                    : "glass hover:-translate-y-0.5 hover:shadow-[var(--shadow-glass)]",
                )}
                style={
                  active
                    ? { borderColor: "var(--color-accent)" }
                    : undefined
                }
              >
                <div className="flex items-center justify-between gap-2">
                  <span
                    className={cn(
                      "truncate font-mono text-sm font-semibold tracking-tight",
                      active
                        ? "text-[var(--color-fg)]"
                        : "text-[var(--color-fg-muted)] group-hover:text-[var(--color-fg)]",
                    )}
                  >
                    {run.label}
                  </span>
                  {nTickers != null && (
                    <span className="shrink-0 rounded-full border border-[var(--color-line-strong)] px-1.5 py-0.5 font-mono text-[10px] tabular-nums text-[var(--color-fg-subtle)]">
                      {nTickers}t
                    </span>
                  )}
                </div>
                <span className="font-mono text-2xs text-[var(--color-fg-subtle)]">
                  {formatRelativeTime(run.created_at)}
                </span>
              </Link>
            </li>
          );
        })}
      </ul>
    </div>
  );
}

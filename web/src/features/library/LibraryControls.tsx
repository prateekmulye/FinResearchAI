/**
 * LibraryControls — the search + filter command bar for the run history.
 * Ticker search is a mono command-line input (it IS data); status is a
 * segmented control (Fitts/Hick: one tap per filter, no dropdown). The page
 * owns debouncing + the query; this is presentational.
 */
import { Search, X } from "lucide-react";
import { useId } from "react";

import { type RunStatus } from "@/lib/api";
import { cn } from "@/lib/utils";

export type StatusFilter = "all" | RunStatus;

const STATUS_OPTIONS: { value: StatusFilter; label: string }[] = [
  { value: "all", label: "All" },
  { value: "running", label: "Running" },
  { value: "finished", label: "Finished" },
  { value: "error", label: "Error" },
  { value: "aborted", label: "Aborted" },
];

export function LibraryControls({
  ticker,
  onTicker,
  status,
  onStatus,
}: {
  ticker: string;
  onTicker: (v: string) => void;
  status: StatusFilter;
  onStatus: (v: StatusFilter) => void;
}) {
  const inputId = useId();
  return (
    <div className="flex flex-col gap-3 sm:flex-row sm:items-end sm:justify-between">
      <div className="sm:w-72">
        <label
          htmlFor={inputId}
          className="mb-1.5 block font-mono text-2xs uppercase tracking-[0.18em] text-[var(--color-fg-subtle)]"
        >
          Filter ticker
        </label>
        <div className="relative">
          <Search
            className="pointer-events-none absolute left-3 top-1/2 size-4 -translate-y-1/2 text-[var(--color-fg-subtle)]"
            aria-hidden="true"
          />
          <input
            id={inputId}
            value={ticker}
            onChange={(e) => onTicker(e.target.value)}
            placeholder="AAPL · NVDA · 0700.HK"
            autoComplete="off"
            spellCheck={false}
            maxLength={15}
            className={cn(
              "h-10 w-full rounded-lg pl-9 pr-9",
              "bg-[var(--color-surface-2)] font-mono text-sm font-medium uppercase tracking-wide text-[var(--color-fg)]",
              "border border-[var(--color-line-strong)] placeholder:font-normal placeholder:normal-case placeholder:tracking-normal placeholder:text-[var(--color-fg-subtle)]",
              "transition-[border-color,box-shadow] duration-[120ms]",
              "focus:border-[var(--color-accent)] focus:shadow-[var(--shadow-glow-accent)] focus:outline-none",
            )}
          />
          {ticker && (
            <button
              type="button"
              onClick={() => onTicker("")}
              aria-label="Clear ticker filter"
              className="absolute right-2 top-1/2 flex size-6 -translate-y-1/2 items-center justify-center rounded-md text-[var(--color-fg-subtle)] transition-colors hover:text-[var(--color-fg)]"
            >
              <X className="size-3.5" aria-hidden="true" />
            </button>
          )}
        </div>
      </div>

      <fieldset>
        <legend className="mb-1.5 font-mono text-2xs uppercase tracking-[0.18em] text-[var(--color-fg-subtle)]">
          Status
        </legend>
        <div className="inline-flex h-10 items-center gap-0.5 rounded-lg border border-[var(--color-line)] bg-[var(--color-surface-1)] p-1">
          {STATUS_OPTIONS.map((opt) => (
            <button
              key={opt.value}
              type="button"
              aria-pressed={status === opt.value}
              onClick={() => onStatus(opt.value)}
              className={cn(
                "rounded-md px-3 py-1.5 text-xs font-medium transition-colors duration-[120ms]",
                status === opt.value
                  ? "bg-[var(--color-glass-strong)] text-[var(--color-fg)] ring-1 ring-[var(--color-glass-border)]"
                  : "text-[var(--color-fg-subtle)] hover:text-[var(--color-fg-muted)]",
              )}
            >
              {opt.label}
            </button>
          ))}
        </div>
      </fieldset>
    </div>
  );
}

/**
 * ExplorerSearch — the search-first hero. One mono command line drives BOTH
 * lanes (instruments + research memory), so the recruiter types once and the
 * whole page reorganises. Heavier than the library filter (it IS the page's
 * primary affordance — Fitts: large hit target, top-of-fold). The page owns
 * debouncing + the URL; this stays presentational.
 */
import { Search, X } from "lucide-react";
import { useId } from "react";

import { cn } from "@/lib/utils";

export function ExplorerSearch({
  value,
  onChange,
  resultCount,
}: {
  value: string;
  onChange: (v: string) => void;
  /** Optional live count for the aria status line (announced, not shown). */
  resultCount?: number;
}) {
  const inputId = useId();
  return (
    <div className="relative">
      <label htmlFor={inputId} className="sr-only">
        Search instruments and research memory
      </label>
      <Search
        className="pointer-events-none absolute left-4 top-1/2 size-5 -translate-y-1/2 text-[var(--color-fg-subtle)]"
        aria-hidden="true"
      />
      <input
        id={inputId}
        value={value}
        onChange={(e) => onChange(e.target.value)}
        placeholder="Search any ticker, company, or research memory — AAPL · Reliance · “tariff risk”"
        autoComplete="off"
        spellCheck={false}
        maxLength={256}
        className={cn(
          "h-14 w-full rounded-2xl pl-12 pr-12",
          "bg-[var(--color-surface-2)] font-mono text-base font-medium text-[var(--color-fg)]",
          "border border-[var(--color-line-strong)]",
          "placeholder:font-normal placeholder:text-[var(--color-fg-subtle)]",
          "shadow-[inset_0_1px_0_0_oklch(100%_0_0/4%)] transition-[border-color,box-shadow] duration-[120ms]",
          "focus:border-[var(--color-accent)] focus:shadow-[var(--shadow-glow-accent)] focus:outline-none",
        )}
      />
      {value && (
        <button
          type="button"
          onClick={() => onChange("")}
          aria-label="Clear search"
          className="absolute right-3 top-1/2 flex size-8 -translate-y-1/2 items-center justify-center rounded-lg text-[var(--color-fg-subtle)] transition-colors hover:bg-[var(--color-glass)] hover:text-[var(--color-fg)]"
        >
          <X className="size-4" aria-hidden="true" />
        </button>
      )}
      {resultCount != null && (
        <span className="sr-only" role="status" aria-live="polite">
          {resultCount} {resultCount === 1 ? "result" : "results"}
        </span>
      )}
    </div>
  );
}

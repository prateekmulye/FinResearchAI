/**
 * PricePanel — the chart tile: a header (kicker + last-close delta + range
 * pills), the candlestick canvas, and the loading / empty / error states. The
 * range pills are ghost buttons (NotebookLM recipe) that re-key the prices query
 * by `days`; the active pill carries the glass-strong fill. When a ticker has no
 * bars yet, the empty state is an outcome-oriented nudge (Peak-End): "analyze
 * TICKER to backfill", deep-linking to / with the ticker prefilled.
 */
import { CandlestickChart as ChartIcon, LineChart, Radio } from "lucide-react";
import { Link } from "react-router";

import { buttonVariants } from "@/components/ui/button";
import type { PriceBar } from "@/lib/api";
import { cn, formatPercent } from "@/lib/utils";

import { CandlestickChart } from "./CandlestickChart";
import { RANGE_OPTIONS, type RangeKey } from "./dossierRange";

function ChangeBadge({ bars }: { bars: PriceBar[] }) {
  if (bars.length < 2) return null;
  const first = bars[0]?.close;
  const last = bars[bars.length - 1]?.close;
  if (first == null || last == null || !first) return null;
  const frac = (last - first) / first;
  const up = frac >= 0;
  return (
    <span
      className="inline-flex items-center gap-1 rounded-full px-2 py-0.5 font-mono text-2xs tabular-nums"
      style={{
        color: up ? "var(--color-bull)" : "var(--color-bear)",
        background: up ? "var(--color-bull-dim)" : "var(--color-bear-dim)",
      }}
    >
      {up ? "▲" : "▼"} {formatPercent(frac, { signed: true })}
      <span className="text-[var(--color-fg-subtle)]">over range</span>
    </span>
  );
}

export function PricePanel({
  ticker,
  bars,
  range,
  onRange,
  isLoading,
  isError,
  onRetry,
}: {
  ticker: string;
  bars: PriceBar[];
  range: RangeKey;
  onRange: (r: RangeKey) => void;
  isLoading: boolean;
  isError: boolean;
  onRetry: () => void;
}) {
  return (
    <section className="glass space-y-4 rounded-2xl p-5 sm:p-6">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div className="flex items-center gap-3">
          <p className="font-mono text-2xs font-medium uppercase tracking-[0.18em] text-[var(--color-accent)]">
            Daily price action
          </p>
          {bars.length >= 2 && <ChangeBadge bars={bars} />}
        </div>

        {/* Range pills — ghost buttons, active = glass-strong. */}
        <div
          className="inline-flex items-center gap-0.5 rounded-lg border border-[var(--color-line)] bg-[var(--color-surface-1)] p-1"
          role="group"
          aria-label="Chart range"
        >
          {RANGE_OPTIONS.map((opt) => (
            <button
              key={opt.key}
              type="button"
              aria-pressed={range === opt.key}
              onClick={() => onRange(opt.key)}
              className={cn(
                "rounded-md px-3 py-1 font-mono text-2xs font-medium tracking-wide transition-colors duration-[120ms]",
                range === opt.key
                  ? "bg-[var(--color-glass-strong)] text-[var(--color-fg)] ring-1 ring-[var(--color-glass-border)]"
                  : "text-[var(--color-fg-subtle)] hover:text-[var(--color-fg-muted)]",
              )}
            >
              {opt.label}
            </button>
          ))}
        </div>
      </div>

      {isLoading ? (
        <div
          className="h-[340px] w-full animate-shimmer rounded-xl bg-[var(--color-surface-1)] sm:h-[420px]"
          aria-hidden="true"
        />
      ) : isError ? (
        <div className="flex h-[340px] flex-col items-center justify-center gap-3 rounded-xl border border-[var(--color-line)] sm:h-[420px]">
          <LineChart className="size-6 text-[var(--color-fg-subtle)]" aria-hidden="true" />
          <p className="text-sm text-[var(--color-fg-muted)]">
            Couldn’t load price bars
          </p>
          <button
            type="button"
            onClick={onRetry}
            className="rounded-md bg-[var(--color-accent)] px-3 py-1.5 text-xs font-semibold text-[var(--color-accent-fg)] transition-colors hover:bg-[var(--color-accent-strong)]"
          >
            Retry
          </button>
        </div>
      ) : bars.length === 0 ? (
        <div className="flex h-[340px] flex-col items-center justify-center gap-3 rounded-xl border border-dashed border-[var(--color-line-strong)] px-6 text-center sm:h-[420px]">
          <span className="flex size-12 items-center justify-center rounded-2xl bg-[var(--color-glass-strong)] ring-1 ring-[var(--color-glass-border)]">
            <ChartIcon className="size-5 text-[var(--color-accent)]" aria-hidden="true" />
          </span>
          <div className="max-w-sm space-y-1">
            <p className="text-sm font-medium text-[var(--color-fg)]">
              No bars stored for {ticker} yet
            </p>
            <p className="text-xs leading-relaxed text-[var(--color-fg-muted)]">
              Price history is backfilled when the analysts run. Analyze {ticker}{" "}
              live and its daily candles land here.
            </p>
          </div>
          <Link
            to="/"
            state={{ ticker }}
            className={cn(buttonVariants({ variant: "primary", size: "sm" }), "mt-1")}
          >
            <Radio className="size-4" aria-hidden="true" />
            Analyze {ticker} to backfill
          </Link>
        </div>
      ) : (
        <CandlestickChart bars={bars} />
      )}
    </section>
  );
}

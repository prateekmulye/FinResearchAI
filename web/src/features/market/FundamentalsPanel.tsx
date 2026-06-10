/**
 * FundamentalsPanel — the latest snapshot as a mono metric tape (Bloomberg
 * energy): market cap abbreviated, P/E, EPS, revenue growth %, profit margin %,
 * each tabular so the column never jitters. Growth and margin are signed so a
 * contraction reads negative at a glance. A snapshot timestamp grounds the data
 * in time (System Status Visibility). Missing snapshot → an outcome-oriented
 * empty state, not a dead "no data".
 */
import { BarChart3, Gauge } from "lucide-react";
import { Link } from "react-router";

import { buttonVariants } from "@/components/ui/button";
import type { Fundamentals } from "@/lib/api";
import {
  cn,
  formatCompactUsd,
  formatPercent,
  formatRatio,
  formatRelativeTime,
} from "@/lib/utils";

function Metric({
  label,
  value,
  tint,
}: {
  label: string;
  value: string;
  tint?: string;
}) {
  return (
    <div className="flex flex-col gap-1 rounded-lg bg-[var(--color-surface-1)] px-3 py-2.5">
      <span className="font-mono text-2xs uppercase tracking-[0.14em] text-[var(--color-fg-subtle)]">
        {label}
      </span>
      <span
        className="font-mono text-base font-semibold tabular-nums leading-none"
        style={{ color: tint ?? "var(--color-fg)" }}
      >
        {value}
      </span>
    </div>
  );
}

/** Tint a signed fraction by direction (positive bull, negative bear, 0 muted). */
function signedTint(v: number | null): string {
  if (v == null || v === 0) return "var(--color-fg)";
  return v > 0 ? "var(--color-bull)" : "var(--color-bear)";
}

export function FundamentalsPanel({
  ticker,
  data,
  isLoading,
  notFound,
}: {
  ticker: string;
  data: Fundamentals | null;
  isLoading: boolean;
  /** A 404 (no snapshot) is the expected empty path, not an error. */
  notFound: boolean;
}) {
  return (
    <section className="glass space-y-4 rounded-2xl p-5 sm:p-6">
      <div className="flex items-center justify-between gap-3">
        <p className="flex items-center gap-2 font-mono text-2xs font-medium uppercase tracking-[0.18em] text-[var(--color-accent)]">
          <Gauge className="size-3.5" aria-hidden="true" />
          Fundamentals
        </p>
        {data && (
          <span className="font-mono text-2xs text-[var(--color-fg-subtle)]">
            snapshot {formatRelativeTime(data.ts)}
          </span>
        )}
      </div>

      {isLoading ? (
        <div className="grid grid-cols-2 gap-2 sm:grid-cols-3" aria-hidden="true">
          {Array.from({ length: 5 }).map((_, i) => (
            <div
              key={i}
              className="h-16 animate-shimmer rounded-lg bg-[var(--color-surface-1)]"
            />
          ))}
        </div>
      ) : notFound || !data ? (
        <div className="flex flex-col items-center gap-2 rounded-xl border border-dashed border-[var(--color-line)] px-5 py-8 text-center">
          <BarChart3 className="size-5 text-[var(--color-fg-subtle)]" aria-hidden="true" />
          <p className="text-sm font-medium text-[var(--color-fg)]">
            No fundamentals snapshot yet
          </p>
          <p className="max-w-xs text-xs leading-relaxed text-[var(--color-fg-muted)]">
            The fundamentals analyst captures P/E, EPS, growth, and margins on
            its first run over {ticker}.
          </p>
          <Link
            to="/"
            state={{ ticker }}
            className={cn(buttonVariants({ variant: "outline", size: "sm" }), "mt-1")}
          >
            Analyze {ticker}
          </Link>
        </div>
      ) : (
        <dl className="grid grid-cols-2 gap-2 sm:grid-cols-3">
          <Metric label="Market cap" value={formatCompactUsd(data.market_cap)} />
          <Metric label="P / E" value={formatRatio(data.pe_ratio)} />
          <Metric label="EPS" value={formatRatio(data.eps)} />
          <Metric
            label="Rev growth"
            value={formatPercent(data.revenue_growth, { signed: true })}
            tint={signedTint(data.revenue_growth)}
          />
          <Metric
            label="Profit margin"
            value={formatPercent(data.profit_margin, { signed: true })}
            tint={signedTint(data.profit_margin)}
          />
        </dl>
      )}
    </section>
  );
}

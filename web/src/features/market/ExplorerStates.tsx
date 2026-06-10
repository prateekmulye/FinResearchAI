/**
 * ExplorerStates — the lane chrome and its loading/empty states, plus the
 * keyword-fallback honesty banner and the coverage stats strip. The page
 * composes these so its render stays a thin state machine (mirrors the library
 * page's LibraryStates split).
 */
import { type LucideIcon, Sparkles, TriangleAlert } from "lucide-react";
import { type ReactNode } from "react";

import { cn } from "@/lib/utils";

/** A lane heading: a mono kicker + a tabular count of what's in the lane. */
export function LaneHeader({
  kicker,
  count,
}: {
  kicker: string;
  count?: number;
}) {
  return (
    <div className="mb-3 flex items-baseline justify-between px-1">
      <h2 className="font-mono text-2xs font-medium uppercase tracking-[0.18em] text-[var(--color-accent)]">
        {kicker}
      </h2>
      {count != null && (
        <span className="font-mono text-2xs tabular-nums text-[var(--color-fg-subtle)]">
          {count}
        </span>
      )}
    </div>
  );
}

/** Glass-shimmer placeholders that match the explorer row silhouette. */
export function LaneSkeleton({ rows = 4 }: { rows?: number }) {
  return (
    <ul className="space-y-2.5" aria-hidden="true">
      {Array.from({ length: rows }).map((_, i) => (
        <li
          key={i}
          className="glass animate-shimmer flex items-center gap-3 overflow-hidden rounded-xl px-4 py-3.5"
        >
          <span className="size-2.5 shrink-0 rounded-full bg-[var(--color-surface-3)]" />
          <span className="h-4 w-20 rounded bg-[var(--color-surface-3)]" />
          <span className="ml-auto h-3 w-32 rounded bg-[var(--color-surface-3)]" />
        </li>
      ))}
    </ul>
  );
}

/** A compact, in-lane empty/error notice (not the full-page EmptyState). */
export function LaneNotice({
  icon: Icon,
  title,
  description,
  children,
}: {
  icon: LucideIcon;
  title: string;
  description: ReactNode;
  children?: ReactNode;
}) {
  return (
    <div className="glass flex flex-col items-center gap-2 rounded-xl px-5 py-8 text-center">
      <Icon className="size-5 text-[var(--color-fg-subtle)]" aria-hidden="true" />
      <p className="text-sm font-medium text-[var(--color-fg)]">{title}</p>
      <p className="max-w-xs text-xs leading-relaxed text-[var(--color-fg-muted)]">
        {description}
      </p>
      {children}
    </div>
  );
}

/**
 * KeywordModeBanner — the honesty cue. When /api/search answers in "keyword"
 * mode the semantic index was unavailable, so we say so plainly in amber (the
 * degraded/hold signal) rather than passing keyword hits off as semantic. Only
 * rendered in keyword mode; semantic mode shows nothing (the happy path is
 * silent).
 */
export function KeywordModeBanner() {
  return (
    <div
      className="flex items-center gap-2 rounded-lg border px-3 py-1.5"
      style={{
        borderColor: "var(--color-hold)",
        background: "var(--color-hold-dim)",
      }}
      role="status"
    >
      <TriangleAlert
        className="size-3.5 shrink-0 text-[var(--color-hold)]"
        aria-hidden="true"
      />
      <p className="font-mono text-2xs tracking-wide text-[var(--color-fg-muted)]">
        keyword fallback — semantic index offline; matching on text, not meaning
      </p>
    </div>
  );
}

/** Pre-search hint for the research lane (before the user types). */
export function ResearchLanePrompt() {
  return (
    <LaneNotice
      icon={Sparkles}
      title="Search the system’s memory"
      description="Type a theme, ticker, or thesis to surface the news the analysts ingested and the past runs that reasoned over it."
    />
  );
}

/* ----------------------------------------------------------- coverage strip */

/**
 * CoverageStrip — three terminal stat tiles derived from the default
 * instruments fetch (shown only when there's no query). Honest by construction:
 * the counts describe the *fetched page*, not the whole universe, so the
 * footnote says "top N shown" — never an inflated total the backend didn't
 * promise.
 */
export function CoverageStrip({
  instruments,
  watched,
  exchanges,
  capped,
}: {
  instruments: number;
  watched: number;
  exchanges: number;
  /** True when the fetch hit its limit, so counts are a floor, not a total. */
  capped: boolean;
}) {
  return (
    <div>
      <dl className="grid grid-cols-3 gap-3">
        <CoverageStat
          label="Instruments"
          value={instruments}
          hint={capped ? "top shown" : "covered"}
        />
        <CoverageStat label="Watched" value={watched} hint="analyzed" accent />
        <CoverageStat label="Exchanges" value={exchanges} hint="venues" />
      </dl>
      {capped && (
        <p className="mt-2 px-1 font-mono text-2xs text-[var(--color-fg-subtle)]">
          Showing the top {instruments} instruments — search to reach the rest.
        </p>
      )}
    </div>
  );
}

function CoverageStat({
  label,
  value,
  hint,
  accent,
}: {
  label: string;
  value: number;
  hint: string;
  accent?: boolean;
}) {
  return (
    <div className="glass rounded-xl px-4 py-3">
      <dt className="font-mono text-2xs uppercase tracking-[0.16em] text-[var(--color-fg-subtle)]">
        {label}
      </dt>
      <dd
        className={cn(
          "mt-1 font-mono text-2xl font-semibold tabular-nums leading-none",
          accent ? "text-[var(--color-bull)]" : "text-[var(--color-fg)]",
        )}
      >
        {value.toLocaleString("en-US")}
      </dd>
      <dd className="mt-1 font-mono text-2xs text-[var(--color-fg-subtle)]">
        {hint}
      </dd>
    </div>
  );
}

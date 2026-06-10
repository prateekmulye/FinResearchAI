import { clsx, type ClassValue } from "clsx";
import { twMerge } from "tailwind-merge";

/** shadcn-standard class combiner: clsx for conditionals, tailwind-merge to dedupe. */
export function cn(...inputs: ClassValue[]) {
  return twMerge(clsx(inputs));
}

/** Format a USD cost with sensible precision for tiny inference costs. */
export function formatUsd(value: number | null | undefined): string {
  if (value == null || Number.isNaN(value)) return "—";
  if (value === 0) return "$0.00";
  if (value < 0.01) return `$${value.toFixed(4)}`;
  return `$${value.toFixed(2)}`;
}

/** Compact latency: ms under a second, otherwise seconds with one decimal. */
export function formatLatency(seconds: number | null | undefined): string {
  if (seconds == null || Number.isNaN(seconds)) return "—";
  if (seconds < 1) return `${Math.round(seconds * 1000)}ms`;
  return `${seconds.toFixed(1)}s`;
}

/** Thousands-grouped integer for token counts. */
export function formatInt(value: number | null | undefined): string {
  if (value == null || Number.isNaN(value)) return "—";
  return value.toLocaleString("en-US");
}

/** Abbreviate a large number to a compact $-prefixed magnitude (market cap):
 *  1.23e12 -> "$1.23T", 4.5e9 -> "$4.50B", 8.1e6 -> "$8.10M". Sub-million
 *  values fall through to grouped dollars so small caps still read precisely. */
export function formatCompactUsd(value: number | null | undefined): string {
  if (value == null || Number.isNaN(value)) return "—";
  const abs = Math.abs(value);
  const sign = value < 0 ? "-" : "";
  const units: [number, string][] = [
    [1e12, "T"],
    [1e9, "B"],
    [1e6, "M"],
  ];
  for (const [scale, suffix] of units) {
    if (abs >= scale) return `${sign}$${(abs / scale).toFixed(2)}${suffix}`;
  }
  return `${sign}$${Math.round(abs).toLocaleString("en-US")}`;
}

/** Format a numeric metric to a fixed precision, or "—" when absent. */
export function formatRatio(
  value: number | null | undefined,
  digits = 2,
): string {
  if (value == null || Number.isNaN(value)) return "—";
  return value.toFixed(digits);
}

/** Format a fraction (0.18) as a signed percentage ("+18.0%"). The backend
 *  stores revenue_growth / profit_margin as fractions; signed so a contraction
 *  reads as negative at a glance (Von Restorff via the leading +/−). */
export function formatPercent(
  value: number | null | undefined,
  { signed = false, digits = 1 }: { signed?: boolean; digits?: number } = {},
): string {
  if (value == null || Number.isNaN(value)) return "—";
  const pct = value * 100;
  const sign = signed && pct > 0 ? "+" : "";
  return `${sign}${pct.toFixed(digits)}%`;
}

/** Relative time like "2m ago" / "3h ago"; falls back to a date for old runs. */
export function formatRelativeTime(iso: string | null | undefined): string {
  if (!iso) return "—";
  const then = new Date(iso).getTime();
  if (Number.isNaN(then)) return "—";
  const diffMs = Date.now() - then;
  const sec = Math.round(diffMs / 1000);
  if (sec < 60) return "just now";
  const min = Math.round(sec / 60);
  if (min < 60) return `${min}m ago`;
  const hr = Math.round(min / 60);
  if (hr < 24) return `${hr}h ago`;
  const day = Math.round(hr / 24);
  if (day < 7) return `${day}d ago`;
  return new Date(then).toLocaleDateString("en-US", {
    month: "short",
    day: "numeric",
  });
}

/**
 * InstrumentRow — one covered instrument as a glass-framed terminal tile. The
 * mono ticker is the hero identity (Von Restorff isolation via the watched
 * dot), the name reads as the human label, and the exchange / sector / country
 * trail as metadata. The whole row is the click target (Fitts) and deep-links
 * to the dossier at /market/:ticker?exchange= — exchange is threaded so a
 * suffix-ambiguous symbol resolves to the right venue.
 */
import { ChevronRight } from "lucide-react";
import { Link } from "react-router";

import type { Instrument } from "@/lib/api";

import { ExchangeChip, WatchedDot } from "./marketChips";

export function InstrumentRow({ instrument }: { instrument: Instrument }) {
  const to = `/market/${encodeURIComponent(instrument.ticker)}${
    instrument.exchange
      ? `?exchange=${encodeURIComponent(instrument.exchange)}`
      : ""
  }`;
  const meta = [instrument.sector, instrument.country].filter(Boolean).join(" · ");

  return (
    <Link
      to={to}
      aria-label={`Open ${instrument.ticker} dossier${
        instrument.name ? ` — ${instrument.name}` : ""
      }`}
      className="group block focus-visible:outline-none"
    >
      <div className="glass flex items-center gap-3 overflow-hidden rounded-xl px-4 py-3 transition-[transform,box-shadow,border-color] duration-[200ms] ease-[var(--ease-spring)] group-hover:-translate-y-0.5 group-hover:shadow-[var(--shadow-raised)] group-focus-visible:outline-2 group-focus-visible:outline-offset-2 group-focus-visible:outline-[var(--color-accent)]">
        <WatchedDot watched={instrument.watched} />

        <div className="min-w-0 flex-1">
          <div className="flex items-center gap-2">
            <span className="truncate font-mono text-sm font-semibold tracking-tight text-[var(--color-fg)]">
              {instrument.ticker}
            </span>
            <ExchangeChip exchange={instrument.exchange} />
          </div>
          <p className="mt-0.5 truncate text-xs text-[var(--color-fg-muted)]">
            {instrument.name ?? "—"}
            {meta && (
              <span className="text-[var(--color-fg-subtle)]"> · {meta}</span>
            )}
          </p>
        </div>

        <ChevronRight
          className="size-4 shrink-0 text-[var(--color-fg-subtle)] transition-[transform,color] duration-[200ms] group-hover:translate-x-0.5 group-hover:text-[var(--color-accent)]"
          aria-hidden="true"
        />
      </div>
    </Link>
  );
}

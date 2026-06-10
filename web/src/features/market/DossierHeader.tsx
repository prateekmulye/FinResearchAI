/**
 * DossierHeader — the instrument identity bar (Peak-End: the "who" is stated up
 * front, above the dense panels). Mono ticker hero, the human name, exchange /
 * sector / country chips, the watched indicator, and the "Analyze live" CTA that
 * deep-links to / with the ticker prefilled via router state (the WP-8 pattern).
 * `instrument` may be null when the symbol resolved to bars but isn't in the
 * coverage list yet — the header still renders from the ticker alone.
 */
import { ArrowLeft, Radio } from "lucide-react";
import { Link } from "react-router";

import { buttonVariants } from "@/components/ui/button";
import type { Instrument } from "@/lib/api";

import { ExchangeChip, WatchedChip } from "./marketChips";

export function DossierHeader({
  ticker,
  exchange,
  instrument,
}: {
  ticker: string;
  /** Exchange from the URL / resolved bars; falls back to the instrument's. */
  exchange?: string;
  instrument: Instrument | null;
}) {
  const venue = exchange || instrument?.exchange;
  const meta = [instrument?.sector, instrument?.country].filter(Boolean);

  return (
    <div className="space-y-4">
      <Link
        to="/market"
        className="inline-flex items-center gap-1.5 text-sm font-medium text-[var(--color-fg-muted)] transition-colors hover:text-[var(--color-fg)]"
      >
        <ArrowLeft className="size-4" aria-hidden="true" />
        Back to explorer
      </Link>

      <div className="flex flex-col gap-4 sm:flex-row sm:items-start sm:justify-between">
        <div className="space-y-2">
          <p className="font-mono text-2xs font-medium uppercase tracking-[0.18em] text-[var(--color-accent)]">
            Instrument dossier
          </p>
          <div className="flex flex-wrap items-center gap-3">
            <h1 className="font-mono text-3xl font-semibold tracking-tight text-[var(--color-fg)] sm:text-4xl">
              {ticker}
            </h1>
            {venue && <ExchangeChip exchange={venue} className="text-xs" />}
            {instrument?.watched && <WatchedChip watched />}
          </div>
          <div className="flex flex-wrap items-center gap-x-2 gap-y-1 text-sm text-[var(--color-fg-muted)]">
            <span className="font-medium text-[var(--color-fg)]">
              {instrument?.name ?? "Coverage instrument"}
            </span>
            {meta.length > 0 && (
              <span className="text-[var(--color-fg-subtle)]">
                · {meta.join(" · ")}
              </span>
            )}
          </div>
        </div>

        <Link
          to="/"
          state={{ ticker }}
          className={`${buttonVariants({ variant: "primary", size: "md" })} shrink-0`}
        >
          <Radio className="size-4" aria-hidden="true" />
          Analyze {ticker} live
        </Link>
      </div>
    </div>
  );
}

/**
 * DossierPage — the instrument deep-dive (/market/:ticker?exchange=). An
 * asymmetric bento (NotebookLM): the candlestick chart is the hero spanning the
 * top (the "every exchange, every ticker" proof screen), then fundamentals and
 * the news feed sit side-by-side below. Each surface owns its own query keyed by
 * (ticker, exchange[, days]) and its own loading / empty / error state, so a
 * missing fundamentals snapshot never blanks the chart and vice-versa
 * (independent degradation, mirroring the agent graph's per-node resilience).
 *
 * The chart libs (lightweight-charts) are imported eagerly here; because the
 * page is lazy-loaded by the router, Vite co-locates them in THIS chunk — they
 * never touch the initial bundle.
 */
import { useQuery } from "@tanstack/react-query";
import { FileSearch } from "lucide-react";
import { useState } from "react";
import { Link, useParams, useSearchParams } from "react-router";

import { EmptyState } from "@/components/ui/empty-state";
import { DossierHeader } from "@/features/market/DossierHeader";
import { DEFAULT_RANGE, daysForRange, type RangeKey } from "@/features/market/dossierRange";
import { FundamentalsPanel } from "@/features/market/FundamentalsPanel";
import { NewsFeed } from "@/features/market/NewsFeed";
import { PricePanel } from "@/features/market/PricePanel";
import { ApiError, api } from "@/lib/api";

/** Duck-typed HTTP status off any error (ApiError or otherwise). */
function statusOf(err: unknown): number | null {
  return err instanceof ApiError
    ? err.status
    : err && typeof err === "object" && typeof (err as { status?: unknown }).status === "number"
      ? (err as { status: number }).status
      : null;
}

export function DossierPage() {
  const { ticker = "" } = useParams<{ ticker: string }>();
  const [params] = useSearchParams();
  const exchange = params.get("exchange") ?? undefined;
  const symbol = ticker.toUpperCase();

  const [range, setRange] = useState<RangeKey>(DEFAULT_RANGE);
  const days = daysForRange(range);

  // Resolve the instrument metadata (name/sector/country/watched) by searching
  // coverage for the exact ticker. EXACT match only — a near-miss (AAPL for
  // /market/APP) must never masquerade as this instrument; an unresolved ticker
  // is what lets the unknown-ticker dead-end below fire. When ?exchange= is
  // present, prefer the exchange-qualified listing among exact-ticker matches.
  // Best-effort: the dossier renders without it.
  const instrumentQuery = useQuery({
    queryKey: ["instrument", symbol],
    queryFn: ({ signal }) => api.instruments({ q: symbol, limit: 10 }, signal),
  });
  const tickerMatches =
    instrumentQuery.data?.instruments.filter(
      (i) => i.ticker.toUpperCase() === symbol,
    ) ?? [];
  const instrument =
    (exchange
      ? tickerMatches.find(
          (i) => i.exchange.toUpperCase() === exchange.toUpperCase(),
        )
      : undefined) ??
    tickerMatches[0] ??
    null;

  const pricesQuery = useQuery({
    queryKey: ["prices", symbol, exchange, days],
    queryFn: ({ signal }) => api.prices(symbol, { exchange, days }, signal),
    retry: (count, err) => statusOf(err) !== 404 && count < 1,
  });

  const fundamentalsQuery = useQuery({
    queryKey: ["fundamentals", symbol, exchange],
    queryFn: ({ signal }) => api.fundamentals(symbol, { exchange }, signal),
    // A 404 means "no snapshot" — terminal, never retry; surface as empty.
    retry: (count, err) => statusOf(err) !== 404 && count < 1,
  });

  const newsQuery = useQuery({
    queryKey: ["news", symbol, exchange],
    queryFn: ({ signal }) => api.news(symbol, { exchange, limit: 12 }, signal),
    retry: (count, err) => statusOf(err) !== 404 && count < 1,
  });

  // An unknown ticker 404s on EVERY market endpoint. If prices 404 AND the
  // instrument didn't resolve, it's genuinely uncovered — a designed dead-end.
  const pricesNotFound = statusOf(pricesQuery.error) === 404;
  const fundamentalsNotFound = statusOf(fundamentalsQuery.error) === 404;
  const newsNotFound = statusOf(newsQuery.error) === 404;
  const unknownTicker =
    pricesNotFound &&
    fundamentalsNotFound &&
    newsNotFound &&
    !instrumentQuery.isLoading &&
    instrument == null;

  if (unknownTicker) {
    return (
      <div className="space-y-8">
        <DossierHeader ticker={symbol} exchange={exchange} instrument={null} />
        <EmptyState
          icon={FileSearch}
          title={`${symbol} isn’t in coverage`}
          description="No instrument resolves to this symbol — it may be mistyped, or the wrong exchange suffix. Search the explorer for what’s covered, or analyze it live to add it."
        >
          <Link
            to="/"
            state={{ ticker: symbol }}
            className="rounded-md bg-[var(--color-accent)] px-4 py-2 text-sm font-semibold text-[var(--color-accent-fg)] transition-colors hover:bg-[var(--color-accent-strong)]"
          >
            Analyze {symbol} live
          </Link>
        </EmptyState>
      </div>
    );
  }

  const bars = pricesNotFound ? [] : (pricesQuery.data?.bars ?? []);

  return (
    <div className="space-y-6">
      <DossierHeader ticker={symbol} exchange={exchange} instrument={instrument} />

      {/* Hero: the price panel spans the bento's full width. */}
      <PricePanel
        ticker={symbol}
        bars={bars}
        range={range}
        onRange={setRange}
        isLoading={pricesQuery.isLoading}
        isError={pricesQuery.isError && !pricesNotFound}
        onRetry={() => void pricesQuery.refetch()}
      />

      {/* Below: fundamentals + news, side-by-side on wide screens. */}
      <div className="grid gap-6 lg:grid-cols-2">
        <FundamentalsPanel
          ticker={symbol}
          data={fundamentalsNotFound ? null : (fundamentalsQuery.data ?? null)}
          isLoading={fundamentalsQuery.isLoading}
          notFound={fundamentalsNotFound}
        />
        <NewsFeed
          ticker={symbol}
          items={newsNotFound ? [] : (newsQuery.data?.items ?? [])}
          isLoading={newsQuery.isLoading}
        />
      </div>
    </div>
  );
}

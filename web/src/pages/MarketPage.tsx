/**
 * MarketPage — the Market Explorer (WP-9). Search-first: one mono command line
 * drives TWO lanes from t=0 — covered Instruments (/api/market/instruments) and
 * Research memory (/api/search, semantic with an honest keyword fallback). The
 * URL is the source of truth (?q=), so /market?q=NVDA is deep-linkable; the
 * input is debounced before it writes back to the URL, and keepPreviousData
 * keeps both lanes from flashing as the query changes (Doherty).
 *
 * With no query, a coverage stats strip stands in for the research lane — "what
 * the system has learned" at a glance — derived cheaply from the default
 * instruments fetch.
 */
import { keepPreviousData, useQuery } from "@tanstack/react-query";
import { AlertTriangle, SearchX, TrendingUp } from "lucide-react";
import { useEffect, useMemo, useState } from "react";
import { useSearchParams } from "react-router";

import { PageHeader } from "@/components/ui/page-header";
import { ExplorerSearch } from "@/features/market/ExplorerSearch";
import {
  CoverageStrip,
  KeywordModeBanner,
  LaneHeader,
  LaneNotice,
  LaneSkeleton,
  ResearchLanePrompt,
} from "@/features/market/ExplorerStates";
import { InstrumentRow } from "@/features/market/InstrumentRow";
import { ResearchHitRow } from "@/features/market/ResearchHitRow";
import { api } from "@/lib/api";

/** Default instruments page size — high enough to power an honest coverage
 *  strip, capped so the lane stays scannable (Miller / Hick). */
const COVERAGE_LIMIT = 60;
const SEARCH_LIMIT = 12;
/** /api/search 422s on a query under 2 chars — don't fire below the floor. */
const MIN_SEARCH_LEN = 2;

export function MarketPage() {
  const [params, setParams] = useSearchParams();
  const urlQuery = params.get("q") ?? "";

  // The input mirrors the URL but debounces before writing back (300ms, like
  // the library ticker filter — one debounce drives both lane queries).
  const [input, setInput] = useState(urlQuery);
  useEffect(() => setInput(urlQuery), [urlQuery]);

  useEffect(() => {
    const trimmed = input.trim();
    if (trimmed === urlQuery) return;
    const id = setTimeout(() => {
      setParams(
        (prev) => {
          const next = new URLSearchParams(prev);
          if (trimmed) next.set("q", trimmed);
          else next.delete("q");
          return next;
        },
        { replace: true },
      );
    }, 300);
    return () => clearTimeout(id);
  }, [input, urlQuery, setParams]);

  const hasQuery = urlQuery.length > 0;
  const searchable = urlQuery.trim().length >= MIN_SEARCH_LEN;

  // Lane 1 — instruments. Empty q returns the coverage set; a q substring-
  // searches ticker OR name. limit varies so the no-query view can derive the
  // coverage strip without a second request.
  const instrumentsQuery = useQuery({
    queryKey: ["instruments", urlQuery],
    queryFn: ({ signal }) =>
      api.instruments(
        { q: urlQuery || undefined, limit: hasQuery ? SEARCH_LIMIT : COVERAGE_LIMIT },
        signal,
      ),
    placeholderData: keepPreviousData,
  });

  // Lane 2 — research memory. Only fires once the query clears the 2-char floor
  // (the backend 422s below it); disabled otherwise so the lane shows a prompt.
  const searchQuery = useQuery({
    queryKey: ["search", urlQuery],
    queryFn: ({ signal }) =>
      api.searchResearch({ q: urlQuery.trim(), limit: SEARCH_LIMIT }, signal),
    enabled: searchable,
    placeholderData: keepPreviousData,
  });

  const instrumentsData = instrumentsQuery.data?.instruments;
  const instruments = useMemo(
    () => instrumentsData ?? [],
    [instrumentsData],
  );
  const hits = searchQuery.data?.hits ?? [];

  // Coverage strip derivation (no-query view only) — honest "page" counts.
  const coverage = useMemo(() => {
    const watched = instruments.filter((i) => i.watched).length;
    const exchanges = new Set(instruments.map((i) => i.exchange)).size;
    return {
      instruments: instruments.length,
      watched,
      exchanges,
      capped: instruments.length >= COVERAGE_LIMIT,
    };
  }, [instruments]);

  return (
    <div className="space-y-8">
      <PageHeader
        eyebrow="Market explorer"
        title="Everything the system knows."
        description="Search any covered instrument and its research memory in one line — coverage across every exchange the router resolves, plus the news the analysts ingested and the past runs that reasoned over it."
      />

      <ExplorerSearch
        value={input}
        onChange={setInput}
        resultCount={hasQuery ? instruments.length + hits.length : undefined}
      />

      {!hasQuery && (
        <CoverageStrip
          instruments={coverage.instruments}
          watched={coverage.watched}
          exchanges={coverage.exchanges}
          capped={coverage.capped}
        />
      )}

      <div className="grid gap-8 lg:grid-cols-2">
        {/* Lane 1 — Instruments */}
        <section aria-labelledby="lane-instruments">
          <LaneHeader
            kicker="Instruments"
            count={instrumentsQuery.isSuccess ? instruments.length : undefined}
          />
          <span id="lane-instruments" className="sr-only">
            Instrument coverage
          </span>
          {instrumentsQuery.isLoading ? (
            <LaneSkeleton />
          ) : instrumentsQuery.isError ? (
            <LaneNotice
              icon={AlertTriangle}
              title="Couldn’t load instruments"
              description="The coverage index didn’t respond — usually a cold backend. Retry in a moment."
            >
              <button
                type="button"
                onClick={() => void instrumentsQuery.refetch()}
                className="mt-1 rounded-md bg-[var(--color-accent)] px-3 py-1.5 text-xs font-semibold text-[var(--color-accent-fg)] transition-colors hover:bg-[var(--color-accent-strong)]"
              >
                Retry
              </button>
            </LaneNotice>
          ) : instruments.length === 0 ? (
            <LaneNotice
              icon={SearchX}
              title="No instruments match"
              description={
                hasQuery
                  ? `Nothing covered matches “${urlQuery}”. Run an analysis on it and it’ll be backfilled into coverage.`
                  : "No instruments are covered yet — run an analysis to seed the index."
              }
            />
          ) : (
            <ul className="space-y-2.5">
              {instruments.map((inst) => (
                <li key={`${inst.ticker}:${inst.exchange}`}>
                  <InstrumentRow instrument={inst} />
                </li>
              ))}
            </ul>
          )}
        </section>

        {/* Lane 2 — Research memory */}
        <section aria-labelledby="lane-research">
          <LaneHeader
            kicker="Research memory"
            count={searchable && searchQuery.isSuccess ? hits.length : undefined}
          />
          <span id="lane-research" className="sr-only">
            Research memory hits
          </span>
          <div className="space-y-2.5">
            {searchable && searchQuery.data?.mode === "keyword" && (
              <KeywordModeBanner />
            )}
            {!searchable ? (
              <ResearchLanePrompt />
            ) : searchQuery.isLoading ? (
              <LaneSkeleton />
            ) : searchQuery.isError ? (
              <LaneNotice
                icon={AlertTriangle}
                title="Search is unavailable"
                description="The research index didn’t respond. Instruments above still work — retry the search shortly."
              >
                <button
                  type="button"
                  onClick={() => void searchQuery.refetch()}
                  className="mt-1 rounded-md bg-[var(--color-accent)] px-3 py-1.5 text-xs font-semibold text-[var(--color-accent-fg)] transition-colors hover:bg-[var(--color-accent-strong)]"
                >
                  Retry
                </button>
              </LaneNotice>
            ) : hits.length === 0 ? (
              <LaneNotice
                icon={TrendingUp}
                title="No research memory yet"
                description={`Nothing the analysts have ingested matches “${urlQuery}”. Run an analysis and its news + verdict become searchable here.`}
              />
            ) : (
              <ul className="space-y-2.5">
                {hits.map((hit) => (
                  <li key={`${hit.kind}:${hit.ref}`}>
                    <ResearchHitRow hit={hit} />
                  </li>
                ))}
              </ul>
            )}
          </div>
        </section>
      </div>
    </div>
  );
}

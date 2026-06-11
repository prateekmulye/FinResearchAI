/**
 * LibraryPage — the searchable, filterable run history (GET /api/library).
 *
 * URL is the source of truth (ticker/status/page in the query string), so a
 * filtered view like /library?ticker=NVDA is deep-linkable and shareable. The
 * ticker input is debounced before it hits the URL/query; status + pagination
 * are immediate. keepPreviousData keeps the list from flashing during a page
 * turn (Doherty: the surface never goes blank under the user).
 */
import { keepPreviousData, useQuery } from "@tanstack/react-query";
import { AlertTriangle, Library } from "lucide-react";
import { useEffect, useMemo, useState } from "react";
import { Link, useSearchParams } from "react-router";

import { EmptyState } from "@/components/ui/empty-state";
import { PageHeader } from "@/components/ui/page-header";
import {
  LibraryControls,
  type StatusFilter,
} from "@/features/library/LibraryControls";
import { LibraryRow } from "@/features/library/LibraryRow";
import {
  LibraryPager,
  LibrarySkeleton,
  QuotaExhaustedBanner,
} from "@/features/library/LibraryStates";
import { useQuota } from "@/hooks/useQuota";
import { api, type RunStatus } from "@/lib/api";

const PAGE_SIZE = 10;
const VALID_STATUS: StatusFilter[] = [
  "all",
  "running",
  "finished",
  "error",
  "aborted",
];

export function LibraryPage() {
  const [params, setParams] = useSearchParams();

  // URL-derived query inputs.
  const urlTicker = params.get("ticker") ?? "";
  const statusParam = (params.get("status") ?? "all") as StatusFilter;
  const status = VALID_STATUS.includes(statusParam) ? statusParam : "all";
  const page = Math.max(0, Number.parseInt(params.get("page") ?? "0", 10) || 0);
  const offset = page * PAGE_SIZE;

  // The input mirrors the URL but is debounced before writing back to it.
  const [tickerInput, setTickerInput] = useState(urlTicker);
  useEffect(() => setTickerInput(urlTicker), [urlTicker]);

  useEffect(() => {
    const trimmed = tickerInput.trim().toUpperCase();
    if (trimmed === urlTicker) return;
    const id = setTimeout(() => {
      setParams(
        (prev) => {
          const next = new URLSearchParams(prev);
          if (trimmed) next.set("ticker", trimmed);
          else next.delete("ticker");
          next.delete("page"); // a new filter resets to page 0
          return next;
        },
        { replace: true },
      );
    }, 300);
    return () => clearTimeout(id);
  }, [tickerInput, urlTicker, setParams]);

  const setStatus = (s: StatusFilter) =>
    setParams((prev) => {
      const next = new URLSearchParams(prev);
      if (s === "all") next.delete("status");
      else next.set("status", s);
      next.delete("page");
      return next;
    });

  const setPage = (p: number) =>
    setParams((prev) => {
      const next = new URLSearchParams(prev);
      if (p <= 0) next.delete("page");
      else next.set("page", String(p));
      return next;
    });

  const queryParams = useMemo(
    () => ({
      ticker: urlTicker || undefined,
      status: status === "all" ? undefined : (status as RunStatus),
      limit: PAGE_SIZE,
      offset,
    }),
    [urlTicker, status, offset],
  );

  const { data, isLoading, isFetching, isError, refetch } = useQuery({
    queryKey: ["library", urlTicker, status, page],
    queryFn: ({ signal }) => api.library(queryParams, signal),
    placeholderData: keepPreviousData,
  });

  // An out-of-range page (e.g. /library?page=99 against 25 runs) would render
  // as an empty archive. When data shows the offset is past the end, clamp the
  // URL (replace, so Back isn't polluted) to the last valid page.
  useEffect(() => {
    if (!data || data.total <= 0 || offset < data.total) return;
    const lastPage = Math.max(0, Math.ceil(data.total / PAGE_SIZE) - 1);
    setParams(
      (prev) => {
        const next = new URLSearchParams(prev);
        if (lastPage <= 0) next.delete("page");
        else next.set("page", String(lastPage));
        return next;
      },
      { replace: true },
    );
  }, [data, offset, setParams]);

  const { quota } = useQuota();
  const quotaExhausted = quota.kind === "replay-only";

  const runs = data?.runs ?? [];
  const total = data?.total ?? 0;
  const hasFilters = Boolean(urlTicker) || status !== "all";

  return (
    <div className="space-y-8">
      <PageHeader
        eyebrow="Research library"
        title="Every run, replayable."
        description="A searchable archive of past analyses. Filter by ticker or status, scan the verdict and cost at a glance, and open any run to replay the full agent stream exactly as it happened — even when your live quota is spent."
      />

      {quotaExhausted && <QuotaExhaustedBanner />}

      <div className="space-y-5">
        <LibraryControls
          ticker={tickerInput}
          onTicker={setTickerInput}
          status={status}
          onStatus={setStatus}
        />

        {isLoading ? (
          <LibrarySkeleton />
        ) : isError ? (
          <EmptyState
            icon={AlertTriangle}
            title="Couldn’t load the library"
            description="The run archive didn’t respond. This is usually a cold backend — retry in a moment."
          >
            <button
              type="button"
              onClick={() => void refetch()}
              className="rounded-md bg-[var(--color-accent)] px-4 py-2 text-sm font-semibold text-[var(--color-accent-fg)] transition-colors hover:bg-[var(--color-accent-strong)]"
            >
              Retry
            </button>
          </EmptyState>
        ) : runs.length === 0 ? (
          <EmptyState
            icon={Library}
            title={hasFilters ? "No runs match those filters" : "No research yet"}
            description={
              hasFilters
                ? "Clear the ticker or status filter to see the full archive — or run a fresh analysis on this ticker."
                : "Run your first analysis and it lands here newest-first with its verdict, conviction, token cost, and latency — one click to replay the stream."
            }
          >
            <Link
              to={hasFilters ? "/library" : "/"}
              className="rounded-md bg-[var(--color-accent)] px-4 py-2 text-sm font-semibold text-[var(--color-accent-fg)] transition-colors hover:bg-[var(--color-accent-strong)]"
            >
              {hasFilters ? "Clear filters" : "Run your first analysis"}
            </Link>
          </EmptyState>
        ) : (
          <>
            <ul className="space-y-3">
              {runs.map((run) => (
                <li key={run.run_id}>
                  <LibraryRow run={run} />
                </li>
              ))}
            </ul>
            <LibraryPager
              offset={offset}
              pageSize={PAGE_SIZE}
              total={total}
              onPrev={() => setPage(page - 1)}
              onNext={() => setPage(page + 1)}
              isFetching={isFetching}
            />
          </>
        )}
      </div>
    </div>
  );
}

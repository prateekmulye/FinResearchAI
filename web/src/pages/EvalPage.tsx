/**
 * EvalPage — WP-10: "the ablation the paper omits". Visualizes the debate-ON vs
 * debate-OFF A/B (GET /api/eval/results) as a methodology cockpit with one
 * reading axis: VERDICT → EVIDENCE → RECEIPTS.
 *
 *   Run rail        — pick a stored eval run; ?label= deep-links it.
 *   Verdict band    — the headline claim: judge-prefers-debate (hero), + deltas.
 *   Methodology tape— the PROXY honesty cue, framed as rigor not fine print.
 *   Cost/quality    — the spatial proof: is the debate worth its cost per ticker?
 *   Per-ticker table— the auditable receipts, sortable by score / cost delta.
 *
 * URL-as-source-of-truth (?label=) mirrors Library + Market. recharts is lazily
 * loaded via the CostQualityScatter chunk so it never weighs the initial bundle.
 */
import { useQuery } from "@tanstack/react-query";
import { Suspense, lazy, useMemo } from "react";
import { useSearchParams } from "react-router";

import { GlassCard } from "@/components/ui/glass-card";
import { PageHeader } from "@/components/ui/page-header";
import {
  EvalEmpty,
  EvalError,
  EvalSkeleton,
  EvalUnavailable,
} from "@/features/eval/EvalStates";
import { readPairs, readSummary } from "@/features/eval/evalFormat";
import { JudgeLegend } from "@/features/eval/JudgeBadges";
import { MethodologyTape } from "@/features/eval/MethodologyTape";
import { PairTable } from "@/features/eval/PairTable";
import { RunRail } from "@/features/eval/RunRail";
import { VerdictBand } from "@/features/eval/VerdictBand";
import { ApiError, api, type EvalResult } from "@/lib/api";

// recharts rides in this lazy chunk, co-located with the page chunk — never in
// the initial entry (the WP-7/8/9 chunking rule: don't manualChunk it).
const CostQualityScatter = lazy(() =>
  import("@/features/eval/CostQualityScatter").then((m) => ({
    default: m.CostQualityScatter,
  })),
);

const RESULTS_LIMIT = 20;

export function EvalPage() {
  const [params] = useSearchParams();
  const labelParam = params.get("label");

  const query = useQuery({
    queryKey: ["eval-results"],
    queryFn: ({ signal }) => api.evalResults({ limit: RESULTS_LIMIT }, signal),
  });

  const runs = useMemo(() => query.data?.results ?? [], [query.data]);

  // The selected run: ?label= if it matches one, else the newest (results are
  // newest-first from the backend). A stale ?label= falls back gracefully.
  const active: EvalResult | undefined = useMemo(() => {
    if (runs.length === 0) return undefined;
    if (labelParam) {
      const match = runs.find((r) => r.label === labelParam);
      if (match) return match;
    }
    return runs[0];
  }, [runs, labelParam]);

  const summary = useMemo(
    () => (active ? readSummary(active.summary) : null),
    [active],
  );
  const pairs = useMemo(
    () => (active ? readPairs(active.pairs) : []),
    [active],
  );

  return (
    <div className="space-y-8">
      <PageHeader
        eyebrow="Ablation harness"
        title="Does the debate earn its cost?"
        description="A side-by-side A/B of the pipeline with the bull–bear debate ON versus OFF — the ablation the source paper skipped. Decision agreement, conviction shift, and the extra cost, latency, and tokens the debate spends, measured run by run."
      />

      {/* 503 from the warehouse guard → a distinct config state, not "no runs". */}
      {query.isError && query.error instanceof ApiError && query.error.status === 503 ? (
        <EvalUnavailable />
      ) : query.isError ? (
        <EvalError onRetry={() => void query.refetch()} />
      ) : query.isLoading ? (
        <EvalSkeleton />
      ) : runs.length === 0 || !active || !summary ? (
        <EvalEmpty />
      ) : (
        <div className="space-y-8">
          <RunRail runs={runs} activeLabel={active.label} />

          <VerdictBand summary={summary} />

          <MethodologyTape />

          {/* The spatial proof. */}
          <GlassCard className="space-y-4">
            <div className="flex flex-col gap-3 sm:flex-row sm:items-end sm:justify-between">
              <div>
                <h2 className="font-mono text-2xs font-medium uppercase tracking-[0.18em] text-[var(--color-accent)]">
                  Cost vs. quality, per ticker
                </h2>
                <p className="mt-1 max-w-xl text-sm leading-relaxed text-[var(--color-fg-muted)]">
                  Each point is one ticker. Up and to the right, the debate
                  decided better and cost more — it earned its place. Down and to
                  the left, the cheaper baseline was the better call.
                </p>
              </div>
              <JudgeLegend />
            </div>

            <Suspense
              fallback={
                <div className="glass animate-shimmer h-[24rem] overflow-hidden rounded-xl" />
              }
            >
              <CostQualityScatter pairs={pairs} />
            </Suspense>
          </GlassCard>

          {/* The receipts. */}
          <section aria-labelledby="receipts-heading">
            <div className="mb-3 flex items-baseline justify-between px-1">
              <h2
                id="receipts-heading"
                className="font-mono text-2xs font-medium uppercase tracking-[0.18em] text-[var(--color-accent)]"
              >
                Per-ticker receipts
              </h2>
              <span className="font-mono text-2xs tabular-nums text-[var(--color-fg-subtle)]">
                {pairs.length} {pairs.length === 1 ? "ticker" : "tickers"}
              </span>
            </div>
            {pairs.length === 0 ? (
              <GlassCard className="text-center text-sm text-[var(--color-fg-muted)]">
                This run recorded a summary but no per-ticker rows.
              </GlassCard>
            ) : (
              <PairTable pairs={pairs} />
            )}
          </section>
        </div>
      )}
    </div>
  );
}

/**
 * Cockpit — the live multi-agent research surface, assembled from the pipeline
 * canvas + intelligence panels + the decision reveal. It is a PURE FUNCTION of
 * the stream-reducer state (AnalysisStreamState): the same tree renders whether
 * that state came from a live SSE run (useAnalysisStream) or, later, a WP-8
 * replay driver feeding recorded events through the same reducer. See
 * eventPlayer.ts for the seam.
 *
 * xyflow + the markdown renderer (marked/dompurify) only load with this module,
 * which is itself reachable only from the lazy Analyze route chunk.
 *
 * PERF — two memo layers, both load-bearing:
 *   1. The component itself is React.memo'd: the replay theater re-renders its
 *      page ~60fps while the rAF playhead advances, but between recorded events
 *      every Cockpit prop is identity-stable, so the whole tree skips.
 *   2. `statuses` identity is pinned to a per-node lifecycle fingerprint: a
 *      token event produces a new `state` object (so the Cockpit body re-runs)
 *      but an identical fingerprint, so PipelineCanvas's React.memo holds and
 *      the canvas never re-renders on token storms.
 */
import { memo, useMemo } from "react";

import { LiveFeed } from "@/features/analyze/LiveFeed";
import type { AnalysisStreamState } from "@/hooks/useAnalysisStream";

import { AnalystTrio } from "./AnalystTrio";
import { CostTicker } from "./CostTicker";
import { DebateTheater } from "./DebateTheater";
import { DecisionReveal } from "./DecisionReveal";
import { PipelineCanvas } from "./PipelineCanvas";
import { StatusAnnouncer } from "./StatusAnnouncer";
import { TradeRisk } from "./TradeRisk";
import {
  type DebateTopology,
  analystPanel,
  debatePanel,
  nodeStatuses,
  resolveTopology,
  riskPanel,
  tradePanel,
} from "./pipeline";

export const Cockpit = memo(function Cockpit({
  state,
  modeHint = null,
  replayElapsedMs = null,
  replayNodeLatencies = null,
}: {
  state: AnalysisStreamState;
  /**
   * The debate mode the user explicitly requested (AnalyzeForm). Lets the
   * canvas render the right topology from t=0; absent (replay), the topology
   * is inferred from the wire. See resolveTopology.
   */
  modeHint?: DebateTopology | null;
  /**
   * REPLAY only: the original run's recorded elapsed ms at the playhead
   * (useEventPlayer.recordedElapsedMs), forwarded to the cost ticker so
   * ELAPSED reflects the recorded timeline, never the playback wall clock.
   */
  replayElapsedMs?: number | null;
  /**
   * REPLAY only: per-node latency (s) from the recorded run's own ts_ms deltas
   * (useEventPlayer.recordedNodeLatencies). The transcript reads these instead
   * of the reducer's synthetic fold-tick stamps (which render "1ms" rows).
   */
  replayNodeLatencies?: Record<string, number> | null;
}) {
  const isReplay = replayElapsedMs != null;
  const { topology, mode } = useMemo(
    () => resolveTopology(state, modeHint),
    [state, modeHint],
  );
  // `statuses` must keep a STABLE IDENTITY across token-only state changes so
  // PipelineCanvas (React.memo) — and its internal node/edge useMemos — skip.
  // nodeStatuses is cheap (≤12 nodes), so we recompute it per render and pin
  // the returned identity to a fingerprint of the per-node lifecycle values.
  const fresh = nodeStatuses(state, topology);
  const fingerprint = topology.nodes.map((n) => fresh[n.id]).join("|");
  // eslint-disable-next-line react-hooks/exhaustive-deps -- the fingerprint captures every value of `fresh`; an identical fingerprint MUST return the previous object identity (that is the point).
  const statuses = useMemo(() => fresh, [fingerprint]);

  const news = analystPanel(state, statuses, "news_analyst");
  const fundamentals = analystPanel(state, statuses, "fundamentals_analyst");
  const technicals = analystPanel(state, statuses, "technicals_analyst");
  const debate = debatePanel(state, statuses, mode);
  const trade = tradePanel(state, statuses);
  const risk = riskPanel(state, statuses);

  const showReveal = state.phase === "done" && state.done;

  return (
    <div className="space-y-6">
      {/* Pipeline canvas — the hero. Header carries the live cost ticker. */}
      <section
        aria-label="Agent pipeline"
        className="glass space-y-4 rounded-2xl p-4 sm:p-5"
      >
        <div className="flex flex-wrap items-center justify-between gap-3">
          <div className="flex items-center gap-2.5">
            <span className="font-mono text-2xs uppercase tracking-[0.18em] text-[var(--color-accent)]">
              Pipeline
            </span>
            <span className="font-mono text-2xs tabular-nums text-[var(--color-fg-subtle)]">
              {topology.nodes.length} nodes · debate {mode}
            </span>
          </div>
          <CostTicker state={state} replayElapsedMs={replayElapsedMs} />
        </div>

        <PipelineCanvas topology={topology} statuses={statuses} />

        {/* The ONE polite live region. It must stay a direct child of the
            section — inside the collapsed <details> below it would be removed
            from the a11y tree and every announcement muted. */}
        <StatusAnnouncer state={state} isReplay={isReplay} />

        {/* The aria-hidden canvas is shadowed by this semantic status spine:
            the per-node list is a textual transcript, collapsed so it
            complements (not competes with) the canvas. Tab order:
            Input -> Transcript -> Result. */}
        {state.order.length > 0 && (
          <details className="group rounded-xl border border-[var(--color-line)] bg-[var(--color-surface-1)]/40">
            <summary className="flex cursor-pointer select-none items-center gap-2 px-3.5 py-2.5 font-mono text-2xs uppercase tracking-[0.16em] text-[var(--color-fg-subtle)] marker:content-none">
              <span className="transition-transform group-open:rotate-90">›</span>
              Status transcript · {state.order.length} nodes
            </summary>
            <div className="px-3.5 pb-3.5">
              <LiveFeed state={state} replayLatencies={replayNodeLatencies} />
            </div>
          </details>
        )}
      </section>

      {/* Intelligence panels — pure functions of the same state. */}
      <AnalystTrio
        news={news}
        fundamentals={fundamentals}
        technicals={technicals}
      />
      <DebateTheater panel={debate} />
      <TradeRisk trade={trade} risk={risk} />

      {/* Decision reveal — the Peak. Lands when `done` arrives. */}
      {showReveal && <DecisionReveal done={state.done!} ticker={state.ticker} />}
    </div>
  );
});

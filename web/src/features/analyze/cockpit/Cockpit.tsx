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
 */
import { useMemo } from "react";

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

export function Cockpit({
  state,
  modeHint = null,
}: {
  state: AnalysisStreamState;
  /**
   * The debate mode the user explicitly requested (AnalyzeForm). Lets the
   * canvas render the right topology from t=0; absent (replay), the topology
   * is inferred from the wire. See resolveTopology.
   */
  modeHint?: DebateTopology | null;
}) {
  const { topology, mode } = useMemo(
    () => resolveTopology(state, modeHint),
    [state, modeHint],
  );
  // Memoized so PipelineCanvas (React.memo) skips re-rendering — and its
  // internal node/edge useMemos hold — whenever neither input changed.
  const statuses = useMemo(() => nodeStatuses(state, topology), [state, topology]);

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
          <CostTicker state={state} />
        </div>

        <PipelineCanvas topology={topology} statuses={statuses} />

        {/* The ONE polite live region. It must stay a direct child of the
            section — inside the collapsed <details> below it would be removed
            from the a11y tree and every announcement muted. */}
        <StatusAnnouncer state={state} />

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
              <LiveFeed state={state} />
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
}

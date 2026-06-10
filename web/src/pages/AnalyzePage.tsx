import { AlertTriangle, Sparkles } from "lucide-react";

import { GlassCard } from "@/components/ui/glass-card";
import { PageHeader } from "@/components/ui/page-header";
import { SignalBadge } from "@/components/ui/signal-badge";
import { AnalyzeForm } from "@/features/analyze/AnalyzeForm";
import { LiveFeed } from "@/features/analyze/LiveFeed";
import { useAnalysisStream } from "@/hooks/useAnalysisStream";

/**
 * AnalyzePage — the home cockpit. WP-6 ships the command bar + a styled live
 * feed wired end-to-end to the SSE hook (the plumbing proof). WP-7 grows this
 * into the full graph cockpit (xyflow canvas, token stream, verdict card).
 */
export function AnalyzePage() {
  const { state, isActive, start, stop } = useAnalysisStream();
  const verdict = state.done?.finalDecision ?? null;

  return (
    <div className="space-y-8">
      <PageHeader
        eyebrow="Live multi-agent research"
        title={
          <>
            Run a verdict in{" "}
            <span className="text-[var(--color-accent)]">real time</span>.
          </>
        }
        description="Enter a ticker and watch a 12-node agent graph resolve it into a BUY / SELL / HOLD call — streaming each analyst, the bull-bear debate, the trader, and the risk arbiter as they decide, with live cost and latency."
      />

      <GlassCard>
        <AnalyzeForm
          onSubmit={(v) =>
            start({
              ticker: v.ticker,
              investorMode: v.investorMode,
              ...(v.debateMode ? { debateMode: v.debateMode } : {}),
            })
          }
          onStop={stop}
          isActive={isActive}
          disabled={state.phase === "connecting"}
        />
      </GlassCard>

      {/* Verdict — the peak. Renders as soon as `done` lands. */}
      {verdict && (
        <GlassCard className="flex flex-col gap-4 sm:flex-row sm:items-center sm:justify-between">
          <div className="flex items-center gap-4">
            <SignalBadge action={verdict.action} score={verdict.score} size="lg" />
            <div>
              <p className="font-mono text-2xs uppercase tracking-[0.18em] text-[var(--color-fg-subtle)]">
                {state.ticker} · conviction
              </p>
              <p className="font-mono text-2xl font-semibold tabular-nums text-[var(--color-fg)]">
                {(verdict.conviction * 100).toFixed(0)}
                <span className="text-base text-[var(--color-fg-subtle)]">%</span>
              </p>
            </div>
          </div>
          <p className="max-w-md text-sm leading-relaxed text-[var(--color-fg-muted)]">
            {verdict.rationale}
          </p>
        </GlassCard>
      )}

      {/* Error band — clean, never a raw 500. */}
      {state.phase === "error" && state.error && (
        <div
          role="alert"
          className="flex items-start gap-3 rounded-2xl border px-5 py-4"
          style={{
            borderColor: "var(--color-bear)",
            background: "var(--color-bear-dim)",
          }}
        >
          <AlertTriangle
            className="mt-0.5 size-5 shrink-0 text-[var(--color-bear)]"
            aria-hidden="true"
          />
          <div>
            <p className="text-sm font-medium text-[var(--color-fg)]">
              Analysis interrupted
            </p>
            <p className="mt-0.5 font-mono text-xs text-[var(--color-fg-muted)]">
              {state.error}
            </p>
          </div>
        </div>
      )}

      {/* Live feed (or a resting hint) */}
      {state.order.length > 0 ? (
        <section aria-label="Pipeline" className="space-y-3">
          <h2 className="font-mono text-2xs uppercase tracking-[0.18em] text-[var(--color-fg-subtle)]">
            Pipeline · {state.order.length} nodes
          </h2>
          <LiveFeed state={state} />
        </section>
      ) : (
        state.phase === "idle" && (
          <div className="flex items-center gap-2 px-1 text-sm text-[var(--color-fg-subtle)]">
            <Sparkles
              className="size-4 text-[var(--color-accent)]"
              aria-hidden="true"
            />
            The graph streams here the moment you run an analysis.
          </div>
        )
      )}
    </div>
  );
}

import { useQueryClient } from "@tanstack/react-query";
import { AlertTriangle, Sparkles } from "lucide-react";
import { useEffect, useState } from "react";
import { useLocation } from "react-router";

import { GlassCard } from "@/components/ui/glass-card";
import { PageHeader } from "@/components/ui/page-header";
import { AnalyzeForm } from "@/features/analyze/AnalyzeForm";
import { Cockpit } from "@/features/analyze/cockpit/Cockpit";
import { QuotaBlocked } from "@/features/analyze/cockpit/QuotaBlocked";
import { isQuotaError } from "@/features/analyze/cockpit/quota";
import { useAnalysisStream } from "@/hooks/useAnalysisStream";
import type { DebateMode } from "@/lib/api";

/**
 * AnalyzePage — the live cockpit (WP-7). The command bar kicks off a run; the
 * Cockpit renders the 12-node agent graph, the streaming intelligence panels,
 * the bull/bear debate theater, and the final verdict reveal — all as a pure
 * function of the SSE stream state. A quota refusal steers to Library replays.
 */
export function AnalyzePage() {
  const { state, isActive, start, stop } = useAnalysisStream();
  // The debate mode the user explicitly requested for the CURRENT run — lets
  // the cockpit lay out the right topology from t=0 (null = server default).
  const [modeHint, setModeHint] = useState<DebateMode | null>(null);
  // A replay's "Run this ticker live" CTA deep-links here with the ticker in
  // router state; prefill the command bar so the recruiter just hits Run.
  const location = useLocation();
  const prefillTicker =
    location.state && typeof (location.state as { ticker?: unknown }).ticker === "string"
      ? (location.state as { ticker: string }).ticker
      : undefined;

  // A run consumes quota the moment it starts, and a terminal phase (done,
  // error — including a 429 refusal) is when the backend's counters have
  // settled: refetch ["quota"] at both edges so the nav pill never shows a
  // stale "N runs left" after a run. The useQuota poll alone is 60s behind.
  const queryClient = useQueryClient();
  const phase = state.phase;
  useEffect(() => {
    if (phase === "connecting" || phase === "done" || phase === "error") {
      void queryClient.invalidateQueries({ queryKey: ["quota"] });
    }
  }, [phase, queryClient]);

  const quotaBlocked =
    state.phase === "error" && isQuotaError(state.error, state.errorStatus);
  const hardError = state.phase === "error" && !quotaBlocked;
  const hasRun = state.order.length > 0 || state.phase !== "idle";

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
          initialTicker={prefillTicker}
          onSubmit={(v) => {
            setModeHint(v.debateMode ?? null);
            void start({
              ticker: v.ticker,
              investorMode: v.investorMode,
              ...(v.debateMode ? { debateMode: v.debateMode } : {}),
            });
          }}
          onStop={stop}
          isActive={isActive}
          disabled={state.phase === "connecting"}
        />
      </GlassCard>

      {/* Quota refusal — a designed steer to replays, never a dead wall. */}
      {quotaBlocked && <QuotaBlocked />}

      {/* A real failure (not quota) — clean, never a raw 500. */}
      {hardError && state.error && (
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

      {/* The cockpit. Renders the moment a run begins; persists after done. */}
      {hasRun && !quotaBlocked ? (
        <Cockpit state={state} modeHint={modeHint} />
      ) : (
        state.phase === "idle" &&
        !quotaBlocked && (
          <div className="flex items-center gap-2 px-1 text-sm text-[var(--color-fg-subtle)]">
            <Sparkles
              className="size-4 text-[var(--color-accent)]"
              aria-hidden="true"
            />
            The agent graph streams here the moment you run an analysis.
          </div>
        )
      )}
    </div>
  );
}

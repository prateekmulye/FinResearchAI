/**
 * EvalStates — the page-level loading / error / empty chrome for the eval
 * dashboard, kept out of the page so its render stays a thin state machine
 * (mirrors LibraryStates / ExplorerStates).
 *
 * The empty state is the one that matters: a recruiter who lands here before any
 * eval has run must see EXACTLY how to produce one — so it's a designed, on-brand
 * mono code tile with the real command, not a dead end.
 */
import { AlertTriangle, FlaskConical } from "lucide-react";

import { Button } from "@/components/ui/button";
import { EmptyState } from "@/components/ui/empty-state";
import { GlassCard } from "@/components/ui/glass-card";

/** Full-page glass-shimmer skeleton matching the verdict-band → scatter rhythm. */
export function EvalSkeleton() {
  return (
    <div className="space-y-6" aria-hidden="true">
      {/* Run rail */}
      <div className="flex gap-3">
        {Array.from({ length: 3 }).map((_, i) => (
          <div
            key={i}
            className="glass animate-shimmer h-16 w-40 overflow-hidden rounded-xl"
          />
        ))}
      </div>
      {/* Verdict band */}
      <div className="grid grid-cols-2 gap-3 lg:grid-cols-6">
        <div className="glass-strong animate-shimmer col-span-2 h-40 overflow-hidden rounded-2xl lg:row-span-2" />
        {Array.from({ length: 5 }).map((_, i) => (
          <div
            key={i}
            className="glass animate-shimmer h-[4.75rem] overflow-hidden rounded-xl"
          />
        ))}
      </div>
      {/* Scatter */}
      <div className="glass animate-shimmer h-[24rem] overflow-hidden rounded-2xl" />
    </div>
  );
}

/** The eval read failed (not a 503 — the page guards that separately). */
export function EvalError({ onRetry }: { onRetry: () => void }) {
  return (
    <EmptyState
      icon={AlertTriangle}
      badge="Could not load eval results"
      title="The eval index didn’t respond"
      description="Usually a cold backend. The A/B results live in the warehouse — retry in a moment, or check that the API is up."
    >
      <Button variant="primary" onClick={onRetry}>
        Retry
      </Button>
    </EmptyState>
  );
}

/** The honest empty state: there are no stored eval runs yet. Shows the exact
 *  command, in a designed mono code tile, so the path forward is obvious. */
export function EvalEmpty() {
  return (
    <EmptyState
      icon={FlaskConical}
      badge="No eval runs yet"
      title="Run the ablation to see it here"
      description="The debate-on vs debate-off A/B hasn’t been recorded yet. Run the harness against the curated ticker snapshot and its summary + per-ticker comparison land on this screen."
    >
      <GlassCard className="terminal-tile mt-1 w-full max-w-lg !rounded-lg p-0 text-left">
        <div className="flex items-center justify-between border-b border-[var(--color-line)] px-4 py-2">
          <span className="font-mono text-2xs uppercase tracking-[0.16em] text-[var(--color-fg-subtle)]">
            run the eval
          </span>
          <span className="flex gap-1" aria-hidden="true">
            <span className="size-2 rounded-full bg-[var(--color-bear)] opacity-60" />
            <span className="size-2 rounded-full bg-[var(--color-hold)] opacity-60" />
            <span className="size-2 rounded-full bg-[var(--color-bull)] opacity-60" />
          </span>
        </div>
        <pre className="overflow-x-auto px-4 py-3 font-mono text-xs leading-relaxed text-[var(--color-fg)]">
          <span className="select-none text-[var(--color-accent)]">$ </span>
          python -m src.eval.run \{"\n"}
          {"    "}--tickers evals/tickers.json \{"\n"}
          {"    "}--label demo
        </pre>
      </GlassCard>
    </EmptyState>
  );
}

/** The warehouse is disabled (the API guard returns 503): the eval store can’t
 *  exist at all. Distinct from "no runs yet" — it's a config state, not a
 *  do-this-next state. */
export function EvalUnavailable() {
  return (
    <EmptyState
      icon={FlaskConical}
      badge="Eval store offline"
      title="The results warehouse is disabled"
      description="This deployment is running without a database (DATABASE_URL unset), so stored eval runs can’t be served. The live Analyze pipeline still works — eval persistence needs the warehouse enabled."
    />
  );
}

/**
 * CostTicker — the live cost/latency readout in the cockpit header. Cumulative
 * tokens · USD cost · elapsed, all mono + tabular so the digits never jitter as
 * they tick up. Token/cost increments are collision-driven: they advance only
 * when a node_complete metric lands (welding the number to a real event, NLM),
 * while elapsed ticks on a 1Hz clock while the run is active.
 */
import { Clock, Coins, Hash } from "lucide-react";
import { useEffect, useState } from "react";

import type { AnalysisStreamState } from "@/hooks/useAnalysisStream";
import { formatInt, formatUsd } from "@/lib/utils";

import { costTotals, elapsedSeconds } from "./pipeline";

function Stat({
  icon: Icon,
  label,
  value,
  flash,
}: {
  icon: typeof Hash;
  label: string;
  value: string;
  flash?: boolean;
}) {
  return (
    <div
      className={flash ? "animate-accent-flash" : undefined}
      style={{ transformOrigin: "center" }}
    >
      <div className="flex items-center gap-1 font-mono text-2xs uppercase tracking-[0.14em] text-[var(--color-fg-subtle)]">
        <Icon className="size-3" aria-hidden="true" />
        {label}
      </div>
      <div className="font-mono text-sm font-semibold tabular-nums text-[var(--color-fg)]">
        {value}
      </div>
    </div>
  );
}

export function CostTicker({ state }: { state: AnalysisStreamState }) {
  const totals = costTotals(state);
  const active = state.phase === "connecting" || state.phase === "streaming";

  // 1Hz wall clock only while active, so elapsed advances without re-rendering
  // the whole cockpit on every frame.
  const [now, setNow] = useState(() => Date.now());
  useEffect(() => {
    if (!active) return;
    const id = setInterval(() => setNow(Date.now()), 1000);
    return () => clearInterval(id);
  }, [active]);

  // Wall-clock elapsed while live; at done, prefer the summed node latency
  // (the honest agent compute time) when the wall clock was trivially short
  // (e.g. a near-instant cached/fake run).
  const wall = elapsedSeconds(state, now);
  const elapsed =
    state.phase === "done" && wall < totals.latencyS ? totals.latencyS : wall;

  // Flash the token/cost stats whenever a new node reports (collision-driven).
  return (
    <div
      className="flex items-center gap-5"
      role="status"
      aria-label="Live run cost"
    >
      <Stat
        icon={Hash}
        label="tokens"
        value={formatInt(totals.totalTokens)}
        flash={active && totals.nodesReporting > 0}
        key={`tok-${totals.nodesReporting}`}
      />
      <Stat
        icon={Coins}
        label="cost"
        value={formatUsd(totals.costUsd)}
        flash={active && totals.nodesReporting > 0}
        key={`cost-${totals.nodesReporting}`}
      />
      <Stat
        icon={Clock}
        label="elapsed"
        value={`${elapsed.toFixed(elapsed < 10 ? 1 : 0)}s`}
      />
    </div>
  );
}

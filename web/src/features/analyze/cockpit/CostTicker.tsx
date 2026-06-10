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

  // Wall-clock elapsed while live and at done. Only a trivially short wall
  // clock (< 2s — a near-instant cached/fake run) is substituted with the
  // summed per-node latency: on a real run parallel nodes routinely make that
  // sum EXCEED the wall time, so it must never replace it.
  const wall = elapsedSeconds(state, now);
  const elapsed =
    state.phase === "done" && wall < 2 && totals.latencyS > wall
      ? totals.latencyS
      : wall;

  // Flash the token/cost stats whenever a new node reports (collision-driven).
  // role="group", NOT a live region: the 1Hz clock would announce every second.
  // The terminal cost summary is announced once by the StatusAnnouncer.
  return (
    <div className="flex items-center gap-5" role="group" aria-label="Run cost">
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

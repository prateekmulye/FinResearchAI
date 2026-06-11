/**
 * StatusAnnouncer — the cockpit's ONE polite live region.
 *
 * It must be mounted unconditionally as a direct child of the cockpit section:
 * a live region inside a collapsed <details> (where the LiveFeed transcript
 * lives) is removed from the accessibility tree, muting every announcement.
 *
 * It announces only meaningful transitions — node completions while streaming,
 * and the terminal cost summary exactly once on done. Token streaming never
 * touches the announcement text, so screen readers are never spammed.
 */
import { nodeLabel } from "@/features/analyze/nodeLabels";
import type { AnalysisStreamState } from "@/hooks/useAnalysisStream";
import { formatInt, formatUsd } from "@/lib/utils";

import { costTotals, elapsedSeconds } from "./pipeline";

function announcement(state: AnalysisStreamState, isReplay: boolean): string {
  if (state.phase === "idle") return "";

  if (state.phase === "done") {
    const totals = costTotals(state);
    // REPLAY: node stamps are synthetic fold ticks, so elapsedSeconds would
    // announce a bogus "0s elapsed" — state the cost summary without it.
    if (isReplay) {
      return `Analysis complete — ${formatInt(totals.totalTokens)} tokens, ${formatUsd(totals.costUsd)}`;
    }
    const elapsed = Math.round(elapsedSeconds(state, Date.now()));
    return `Analysis complete — ${formatInt(totals.totalTokens)} tokens, ${formatUsd(totals.costUsd)}, ${elapsed}s elapsed`;
  }

  // Most recently completed node — the only thing worth announcing mid-run.
  const lastCompleted = state.order
    .map((id) => state.nodes[id]!)
    .filter((n) => n.completedAt != null)
    .sort((a, b) => a.completedAt! - b.completedAt!)
    .at(-1);

  return lastCompleted
    ? `${nodeLabel(lastCompleted.node)} complete`
    : "Analysis started";
}

export function StatusAnnouncer({
  state,
  isReplay = false,
}: {
  state: AnalysisStreamState;
  /** REPLAY: suppress wall-clock claims the synthetic timeline can't back. */
  isReplay?: boolean;
}) {
  return (
    <p role="status" className="sr-only">
      {announcement(state, isReplay)}
    </p>
  );
}

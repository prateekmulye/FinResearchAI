import { Check, CircleDashed, Loader2 } from "lucide-react";

import { nodeLabel, nodePhase } from "@/features/analyze/nodeLabels";
import { type AnalysisStreamState } from "@/hooks/useAnalysisStream";
import { cn, formatLatency } from "@/lib/utils";

/**
 * LiveFeed — the WP-6 proof-of-plumbing surface (WP-7 replaces it with the full
 * graph cockpit). Renders a "status spine": one terminal-tile row per node as it
 * streams, completed rows fire the luminous-accent flash, the active row
 * breathes. The list itself is NOT a live region — token streaming mutates it
 * many times per second, which would spam screen readers. Announcements are
 * scoped to a visually-hidden polite status element that only changes on node
 * completions (and the final analysis-complete transition).
 */
export function LiveFeed({ state }: { state: AnalysisStreamState }) {
  if (state.order.length === 0) return null;

  // Most recently completed node — the only thing worth announcing.
  const lastCompleted = state.order
    .map((id) => state.nodes[id]!)
    .filter((n) => n.completedAt != null)
    .sort((a, b) => a.completedAt! - b.completedAt!)
    .at(-1);

  const announcement =
    state.phase === "done"
      ? "Analysis complete"
      : lastCompleted
        ? `${nodeLabel(lastCompleted.node)} complete`
        : "Analysis started";

  return (
    <>
      <p role="status" className="sr-only">
        {announcement}
      </p>
      <ol aria-label="Pipeline progress" className="space-y-1.5">
        {state.order.map((nodeId) => {
          const node = state.nodes[nodeId]!;
          const done = node.completedAt != null;
          const elapsed = done ? (node.completedAt! - node.startedAt) / 1000 : null;

          return (
            <li
              key={nodeId}
              className={cn(
                "terminal-tile flex items-center gap-3 px-3.5 py-2.5",
                done && "animate-accent-flash",
              )}
              style={{ transformOrigin: "left center" }}
            >
              <span className="flex size-5 shrink-0 items-center justify-center">
                {done ? (
                  <Check
                    className="size-4 text-[var(--color-bull)]"
                    aria-hidden="true"
                  />
                ) : (
                  <Loader2
                    className="size-4 animate-spin text-[var(--color-accent)]"
                    aria-hidden="true"
                  />
                )}
              </span>

              <span className="min-w-0 flex-1">
                <span className="text-sm font-medium text-[var(--color-fg)]">
                  {nodeLabel(nodeId)}
                </span>
                <span className="ml-2 font-mono text-2xs uppercase tracking-wide text-[var(--color-fg-subtle)]">
                  {nodePhase(nodeId)}
                </span>
                {node.text && (
                  <span className="mt-0.5 block truncate font-mono text-xs text-[var(--color-fg-muted)]">
                    {node.text.slice(-120)}
                  </span>
                )}
              </span>

              <span className="shrink-0 font-mono text-2xs tabular-nums text-[var(--color-fg-subtle)]">
                {done ? formatLatency(elapsed) : "streaming"}
              </span>
            </li>
          );
        })}

        {state.phase === "connecting" && (
          <li className="flex items-center gap-3 px-3.5 py-2.5 font-mono text-xs text-[var(--color-fg-subtle)]">
            <CircleDashed className="size-4 animate-spin" aria-hidden="true" />
            Opening stream…
          </li>
        )}
      </ol>
    </>
  );
}

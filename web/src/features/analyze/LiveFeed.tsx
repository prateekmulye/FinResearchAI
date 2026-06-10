import { Check, CircleDashed, Loader2 } from "lucide-react";

import { nodeLabel, nodePhase } from "@/features/analyze/nodeLabels";
import { type AnalysisStreamState } from "@/hooks/useAnalysisStream";
import { cn, formatLatency } from "@/lib/utils";

/**
 * LiveFeed — the VISUAL transcript only: one terminal-tile row per node as it
 * streams, completed rows fire the luminous-accent flash, the active row
 * breathes. The list is NOT a live region — token streaming mutates it many
 * times per second, which would spam screen readers. Announcements live in the
 * always-mounted cockpit StatusAnnouncer instead: this transcript renders
 * inside a collapsed <details>, which removes it from the a11y tree.
 */
export function LiveFeed({ state }: { state: AnalysisStreamState }) {
  if (state.order.length === 0) return null;

  return (
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
                <Check className="size-4 text-[var(--color-bull)]" aria-hidden="true" />
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
  );
}

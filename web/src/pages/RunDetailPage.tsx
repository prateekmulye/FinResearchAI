/**
 * RunDetailPage — the replay theater (GET /api/runs/:runId).
 *
 * The whole point of WP-8: a recorded run replays through the EXACT same
 * cockpit the live page uses. We fetch the run, feed its events to
 * useEventPlayer (which reduces them on a timer through the shared reducer),
 * and hand the resulting state to <Cockpit/> — zero cockpit changes. The
 * transport bar scrubs the synthetic timeline; the dossier states the outcome.
 *
 * Error/aborted runs still replay (the events up to the failure are there); a
 * banner explains the outcome. A 404 gets a designed dead-end, not a crash.
 */
import { useQuery } from "@tanstack/react-query";
import { AlertTriangle, ArrowLeft, FileSearch } from "lucide-react";
import { Link, useParams } from "react-router";

import { EmptyState } from "@/components/ui/empty-state";
import { Cockpit } from "@/features/analyze/cockpit/Cockpit";
import { useEventPlayer } from "@/features/analyze/cockpit/eventPlayer";
import { TransportBar } from "@/features/analyze/cockpit/TransportBar";
import { formatMs } from "@/features/analyze/cockpit/transportTime";
import type { DebateTopology } from "@/features/analyze/cockpit/pipeline";
import { RunDossier } from "@/features/library/RunDossier";
import { api, type RunDetail } from "@/lib/api";

/** Duck-typed HTTP status off any error (ApiError or otherwise). */
function statusOf(err: unknown): number | null {
  return err && typeof err === "object" && typeof (err as { status?: unknown }).status === "number"
    ? (err as { status: number }).status
    : null;
}

function BackLink() {
  return (
    <Link
      to="/library"
      className="inline-flex items-center gap-1.5 text-sm font-medium text-[var(--color-fg-muted)] transition-colors hover:text-[var(--color-fg)]"
    >
      <ArrowLeft className="size-4" aria-hidden="true" />
      Back to library
    </Link>
  );
}

export function RunDetailPage() {
  const { runId } = useParams<{ runId: string }>();

  const { data, isLoading, isError, error } = useQuery<RunDetail>({
    queryKey: ["run", runId],
    queryFn: ({ signal }) => api.run(runId!, signal),
    enabled: Boolean(runId),
    // A 404 is terminal (the run id is wrong/pruned) — never retry it; any other
    // failure retries once for a cold backend.
    retry: (count, err) => statusOf(err) !== 404 && count < 1,
  });

  if (isLoading) {
    return (
      <div className="space-y-8">
        <BackLink />
        <div className="glass h-40 animate-shimmer rounded-2xl" aria-hidden="true" />
        <div className="glass h-72 animate-shimmer rounded-2xl" aria-hidden="true" />
      </div>
    );
  }

  if (isError || !data) {
    const notFound = statusOf(error) === 404;
    return (
      <div className="space-y-8">
        <BackLink />
        <EmptyState
          icon={notFound ? FileSearch : AlertTriangle}
          title={notFound ? "That run isn’t in the archive" : "Couldn’t load this run"}
          description={
            notFound
              ? "The run id doesn’t match any recorded analysis — it may have been pruned, or the link is mistyped. Browse the library for runs you can replay."
              : "The replay record didn’t load. This is usually a cold backend — head back and try again."
          }
        >
          <Link
            to="/library"
            className="rounded-md bg-[var(--color-accent)] px-4 py-2 text-sm font-semibold text-[var(--color-accent-fg)] transition-colors hover:bg-[var(--color-accent-strong)]"
          >
            Browse the library
          </Link>
        </EmptyState>
      </div>
    );
  }

  return <ReplayTheater run={data} />;
}

/** The hydrated theater — split out so the player hooks only run with data. */
function ReplayTheater({ run }: { run: RunDetail }) {
  const player = useEventPlayer(run.events);
  const modeHint =
    run.debate_mode === "on" || run.debate_mode === "off"
      ? (run.debate_mode as DebateTopology)
      : null;

  const failed = run.status === "error" || run.status === "aborted";

  return (
    <div className="space-y-6">
      <BackLink />

      <RunDossier run={run} durationLabel={formatMs(player.durationMs)} />

      {/* Error/aborted outcome banner — replay still works up to the failure. */}
      {failed && (
        <div
          role="note"
          className="flex items-start gap-3 rounded-2xl border px-5 py-4"
          style={{
            borderColor:
              run.status === "error" ? "var(--color-bear)" : "var(--color-hold)",
            background:
              run.status === "error"
                ? "var(--color-bear-dim)"
                : "var(--color-hold-dim)",
          }}
        >
          <AlertTriangle
            className="mt-0.5 size-5 shrink-0"
            style={{
              color:
                run.status === "error" ? "var(--color-bear)" : "var(--color-hold)",
            }}
            aria-hidden="true"
          />
          <div>
            <p className="text-sm font-medium text-[var(--color-fg)]">
              This run {run.status === "error" ? "failed" : "was aborted"} mid-stream
            </p>
            <p className="mt-0.5 text-sm text-[var(--color-fg-muted)]">
              The replay still plays every event that was recorded before it
              stopped — scrub to the end to see where the pipeline halted.
            </p>
          </div>
        </div>
      )}

      {/* The transport sits above the cockpit so play/scrub is the first thing
          the eye lands on, then the graph it drives. Emptiness keys on the
          DECODED STEP COUNT, never durationMs: offsets are inter-event gaps,
          so a single-event run has durationMs 0 yet is absolutely replayable. */}
      {player.stepCount > 0 ? (
        <TransportBar player={player} />
      ) : (
        <p className="px-1 font-mono text-2xs text-[var(--color-fg-subtle)]">
          This run has no replayable events recorded.
        </p>
      )}

      {/* The cockpit — driven entirely by the replay state. ELAPSED + per-node
          latencies read the recorded run's own timing at the playhead, never
          the playback wall clock or the reducer's synthetic fold stamps. */}
      <Cockpit
        state={player.state}
        modeHint={modeHint}
        replayElapsedMs={player.recordedElapsedMs}
        replayNodeLatencies={player.recordedNodeLatencies}
      />
    </div>
  );
}

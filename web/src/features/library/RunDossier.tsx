/**
 * RunDossier — the replay theater header. A flight-recorder card: ticker +
 * verdict badge as the identity (Peak-End: the outcome is stated up front so a
 * paused mid-replay still carries its resolution), a mono metrics strip (score ·
 * cost · tokens · duration · date · source), and the "Run this ticker live" CTA
 * that deep-links to / with the ticker prefilled via router state.
 *
 * React.memo'd: the replay theater re-renders ~60fps while the playhead moves,
 * but this header's props (the fetched run + the fixed duration label) never
 * change after load — it must not re-render per frame.
 */
import { Radio } from "lucide-react";
import { memo } from "react";
import { Link } from "react-router";

import { buttonVariants } from "@/components/ui/button";
import { SignalBadge } from "@/components/ui/signal-badge";
import type { RunDetail } from "@/lib/api";
import { formatInt, formatRelativeTime, formatUsd } from "@/lib/utils";

import { DebateChip, StatusChip } from "./runChips";

export const RunDossier = memo(function RunDossier({
  run,
  durationLabel,
}: {
  run: RunDetail;
  /** Synthetic replay duration, e.g. "0:12" — the timeline length, not wall time. */
  durationLabel: string;
}) {
  const fd = run.final_decision;
  const ticker = run.ticker ?? "—";

  return (
    <div className="glass space-y-4 rounded-2xl p-5 sm:p-6">
      <div className="flex flex-col gap-4 sm:flex-row sm:items-start sm:justify-between">
        <div className="space-y-2">
          <p className="font-mono text-2xs font-medium uppercase tracking-[0.18em] text-[var(--color-accent)]">
            Run replay
          </p>
          <div className="flex flex-wrap items-center gap-3">
            <h1 className="font-mono text-3xl font-semibold tracking-tight text-[var(--color-fg)]">
              {ticker}
            </h1>
            {fd && <SignalBadge action={fd.action} score={fd.score} size="lg" />}
          </div>
          <div className="flex flex-wrap items-center gap-2 pt-1">
            {run.debate_mode && <DebateChip mode={run.debate_mode} />}
            {run.status && <StatusChip status={run.status} />}
            <span className="rounded-full border border-[var(--color-line)] px-2 py-0.5 font-mono text-2xs lowercase tracking-wide text-[var(--color-fg-subtle)]">
              {run.source}
            </span>
          </div>
        </div>

        {ticker !== "—" && (
          <Link
            to="/"
            state={{ ticker }}
            className={`${buttonVariants({ variant: "primary", size: "md" })} shrink-0`}
          >
            <Radio className="size-4" aria-hidden="true" />
            Run {ticker} live
          </Link>
        )}
      </div>

      {/* Metrics strip — the recorder readout. */}
      <dl className="grid grid-cols-2 gap-x-6 gap-y-3 border-t border-[var(--color-line)] pt-4 font-mono text-sm sm:grid-cols-4">
        <Stat label="Score" value={fd ? String(fd.score) : "—"} />
        <Stat label="Cost" value={formatUsd(run.cost?.cost_usd)} />
        <Stat label="Tokens" value={formatInt(run.cost?.total_tokens)} />
        <Stat label="Replay" value={durationLabel} />
        <Stat
          label="Run id"
          value={run.run_id.slice(0, 12)}
          className="col-span-2 sm:col-span-2"
          subtle
        />
        <Stat
          label="Recorded"
          value={formatRelativeTime(run.started_at)}
          className="col-span-2 sm:col-span-2"
          subtle
        />
      </dl>
    </div>
  );
});

function Stat({
  label,
  value,
  className,
  subtle,
}: {
  label: string;
  value: string;
  className?: string;
  subtle?: boolean;
}) {
  return (
    <div className={className}>
      <dt className="text-2xs uppercase tracking-[0.16em] text-[var(--color-fg-subtle)]">
        {label}
      </dt>
      <dd
        className={
          subtle
            ? "tabular-nums text-[var(--color-fg-muted)]"
            : "tabular-nums text-[var(--color-fg)]"
        }
      >
        {value}
      </dd>
    </div>
  );
}

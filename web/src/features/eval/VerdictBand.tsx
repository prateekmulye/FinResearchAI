/**
 * VerdictBand — the headline claim of the screen, as an asymmetric bento of
 * mono stat tiles (NotebookLM "Asymmetric Bento Verdict Band"). The hero tile —
 * judge-prefers-debate rate — is isolated by SIZE (spans two columns) and a slow
 * breathing oscillation (Von Restorff + "this feed is live"); the five
 * supporting deltas are smaller, each color-encoded by OUTCOME UTILITY with a
 * directional arrow (Functional Signal Inversion) so a recruiter reads
 * cost-up-as-penalty without reading the label.
 *
 * `aria-live="polite"` on the band so a screen reader announces the verdict.
 * Null-safe throughout: when nothing was judged the hero shows the honest
 * "no verdicts judged" state instead of a fake 0%.
 */
import { ArrowDownRight, ArrowUpRight, Minus } from "lucide-react";

import { useReducedMotion } from "@/hooks/useReducedMotion";
import { cn } from "@/lib/utils";

import {
  type DeltaPolarity,
  type EvalSummary,
  deltaArrow,
  deltaTone,
  formatRate,
  toneColor,
} from "./evalFormat";

export function VerdictBand({ summary }: { summary: EvalSummary }) {
  const reduced = useReducedMotion();

  return (
    <section
      aria-label="Debate-on versus debate-off verdict"
      aria-live="polite"
      className="grid grid-cols-2 gap-3 sm:grid-cols-3 lg:grid-cols-6"
    >
      {/* HERO — judge prefers debate. Spans 2 cols, breathes. */}
      <div
        className={cn(
          "glass-strong relative col-span-2 flex flex-col justify-between overflow-hidden rounded-2xl p-5 sm:row-span-1 lg:col-span-2 lg:row-span-2",
          !reduced && "animate-breathe-tile",
        )}
        style={{ animationDuration: "3200ms" }}
      >
        <div className="flex items-center gap-2">
          <span
            aria-hidden="true"
            className="size-1.5 rounded-full"
            style={{ background: "var(--color-bull)" }}
          />
          <p className="font-mono text-2xs font-medium uppercase tracking-[0.18em] text-[var(--color-fg-muted)]">
            Judge prefers debate
          </p>
        </div>

        {summary.judged ? (
          <div className="mt-4">
            <p
              className="font-mono text-5xl font-semibold leading-none tracking-tight tabular-nums sm:text-6xl"
              style={{ color: "var(--color-fg)", letterSpacing: "0.01em" }}
            >
              {formatRate(summary.judgePrefersOnRate)}
            </p>
            <p className="mt-3 max-w-[22ch] text-xs leading-relaxed text-[var(--color-fg-muted)]">
              of {summary.nJudged} refereed{" "}
              {summary.nJudged === 1 ? "ticker" : "tickers"}, the deep-model judge
              picked the debate pipeline over the single-pass baseline.
            </p>
          </div>
        ) : (
          <div className="mt-4">
            <p className="font-mono text-3xl font-semibold leading-none tabular-nums text-[var(--color-fg-subtle)]">
              n/a
            </p>
            <p className="mt-3 max-w-[24ch] text-xs leading-relaxed text-[var(--color-fg-muted)]">
              No verdicts were refereed in this run — the judge was skipped or
              unavailable, so the preference rate can&rsquo;t be computed.
            </p>
          </div>
        )}
      </div>

      {/* Supporting tiles — rates (neutral, no polarity) then signed deltas. */}
      <RateTile
        label="Action agreement"
        rate={summary.actionAgreementRate}
        hint="on vs off picked the same verdict"
      />
      <RateTile
        label="Judge agreement"
        rate={summary.judgeAgreementRate}
        hint={summary.judged ? "referee concurred with the call" : "no verdicts judged"}
      />
      <DeltaTile
        label="Mean score Δ"
        value={summary.meanScoreDelta}
        polarity="more-is-better"
        format={(v) => (v > 0 ? `+${v.toFixed(1)}` : v.toFixed(1))}
        hint="conviction score, on − off"
      />
      <DeltaTile
        label="Mean cost Δ"
        value={summary.meanCostDelta}
        polarity="less-is-better"
        format={formatUsdDelta}
        hint="the debate's price, on − off"
      />
      <DeltaTile
        label="Mean latency Δ"
        value={summary.meanLatencyDelta}
        polarity="less-is-better"
        format={(v) => (v > 0 ? `+${v.toFixed(1)}s` : `${v.toFixed(1)}s`)}
        hint="wall-clock, on − off"
      />
    </section>
  );
}

function formatUsdDelta(v: number): string {
  const sign = v > 0 ? "+" : v < 0 ? "-" : "";
  const abs = Math.abs(v);
  return `${sign}$${abs < 0.01 ? abs.toFixed(4) : abs.toFixed(2)}`;
}

/** A neutral 0..1 rate tile (no good/bad polarity — agreement isn't a win or a
 *  loss, it's context). Null-safe. */
function RateTile({
  label,
  rate,
  hint,
}: {
  label: string;
  rate: number | null;
  hint: string;
}) {
  return (
    <div className="glass flex flex-col justify-between rounded-xl p-4">
      <p className="font-mono text-2xs uppercase tracking-[0.16em] text-[var(--color-fg-subtle)]">
        {label}
      </p>
      <p className="mt-2 font-mono text-2xl font-semibold leading-none tabular-nums text-[var(--color-fg)]">
        {formatRate(rate)}
      </p>
      <p className="mt-2 text-2xs leading-snug text-[var(--color-fg-subtle)]">
        {hint}
      </p>
    </div>
  );
}

/** A signed-delta tile with Functional Signal Inversion: the value AND its arrow
 *  are tinted by outcome utility (green=helps, amber=friction). */
function DeltaTile({
  label,
  value,
  polarity,
  format,
  hint,
}: {
  label: string;
  value: number | null;
  polarity: DeltaPolarity;
  format: (v: number) => string;
  hint: string;
}) {
  const tone = deltaTone(value, polarity);
  const color = toneColor(tone);
  const dir = deltaArrow(value);
  const Arrow = dir === "up" ? ArrowUpRight : dir === "down" ? ArrowDownRight : Minus;

  return (
    <div className="glass flex flex-col justify-between rounded-xl p-4">
      <p className="font-mono text-2xs uppercase tracking-[0.16em] text-[var(--color-fg-subtle)]">
        {label}
      </p>
      <p
        className="mt-2 flex items-center gap-1 font-mono text-2xl font-semibold leading-none tabular-nums"
        style={{ color: value == null ? "var(--color-fg-subtle)" : color }}
      >
        <Arrow className="size-4 shrink-0" aria-hidden="true" />
        {value == null ? "—" : format(value)}
      </p>
      <p className="mt-2 text-2xs leading-snug text-[var(--color-fg-subtle)]">
        {hint}
      </p>
    </div>
  );
}

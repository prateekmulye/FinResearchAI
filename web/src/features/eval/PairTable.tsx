/**
 * PairTable — the receipts. Every ticker as a dense terminal row (the
 * LibraryRow tape vocabulary), so the verdict band's aggregate claim is fully
 * auditable. Reading order per row: ticker · verdict (on → off SignalBadge pair
 * + an agree/diverge cue) · score on/off/Δ · the cost/latency/token delta tape
 * (each tinted by OUTCOME UTILITY) · the judge preference chip with confidence.
 *
 * Sortable by score delta or cost delta (client-side, two keys) — the two
 * questions a skeptic asks: "where did it decide better?" and "where did it cost
 * more?". On mobile the row stacks; on wide screens it's a single scan line.
 */
import { ArrowDown, ArrowUp, ArrowUpDown } from "lucide-react";
import { useMemo, useState } from "react";

import { SignalBadge } from "@/components/ui/signal-badge";
import { cn } from "@/lib/utils";

import {
  type EvalPair,
  deltaTone,
  formatSignedInt,
  formatSignedSeconds,
  formatSignedUsd,
  toneColor,
} from "./evalFormat";
import { JudgePrefChip } from "./JudgeBadges";
import { type SortKey, type SortState, nextSort, sortPairs } from "./pairSort";

export function PairTable({ pairs }: { pairs: EvalPair[] }) {
  const [sort, setSort] = useState<SortState>({ key: "scoreDelta", dir: "desc" });
  const rows = useMemo(() => sortPairs(pairs, sort), [pairs, sort]);

  return (
    <div>
      {/* Column legend / sort controls. Hidden as a grid on mobile (rows stack
          with inline labels there). */}
      <div className="mb-2 hidden grid-cols-[7rem_minmax(9rem,1fr)_8rem_1fr_8rem] items-center gap-4 px-4 font-mono text-2xs uppercase tracking-wider text-[var(--color-fg-subtle)] lg:grid">
        <SortButton label="Ticker" col="ticker" sort={sort} onSort={setSort} />
        <span>verdict on → off</span>
        <SortButton label="Score Δ" col="scoreDelta" sort={sort} onSort={setSort} />
        <span className="inline-flex items-center gap-1">
          <SortButton label="Cost Δ" col="costDelta" sort={sort} onSort={setSort} />
          <span className="text-[var(--color-fg-subtle)]">· lat · tok</span>
        </span>
        <span className="text-right">judge</span>
      </div>

      <ul className="space-y-1.5">
        {rows.map((pair) => (
          <li key={pair.ticker}>
            <Row pair={pair} />
          </li>
        ))}
      </ul>
    </div>
  );
}

function SortButton({
  label,
  col,
  sort,
  onSort,
}: {
  label: string;
  col: SortKey;
  sort: SortState;
  onSort: (s: SortState) => void;
}) {
  const active = sort.key === col;
  const Icon = !active ? ArrowUpDown : sort.dir === "desc" ? ArrowDown : ArrowUp;
  return (
    <button
      type="button"
      onClick={() => onSort(nextSort(sort, col))}
      aria-label={`Sort by ${label}${active ? `, ${sort.dir}ending` : ""}`}
      className={cn(
        "inline-flex items-center gap-1 uppercase tracking-wider transition-colors hover:text-[var(--color-fg)]",
        active ? "text-[var(--color-accent)]" : "text-[var(--color-fg-subtle)]",
      )}
    >
      {label}
      <Icon className="size-3" aria-hidden="true" />
    </button>
  );
}

function Row({ pair }: { pair: EvalPair }) {
  return (
    <div className="glass grid grid-cols-1 gap-3 rounded-xl p-4 lg:grid-cols-[7rem_minmax(9rem,1fr)_8rem_1fr_8rem] lg:items-center lg:gap-4 lg:py-3">
      {/* Ticker */}
      <span className="font-mono text-base font-semibold tracking-tight text-[var(--color-fg)]">
        {pair.ticker}
      </span>

      {/* Verdict on → off */}
      <div className="flex items-center gap-2">
        <Verdict action={pair.actionOn} score={pair.scoreOn} />
        <span
          aria-hidden="true"
          className="font-mono text-2xs"
          style={{
            color: pair.actionsAgree
              ? "var(--color-fg-subtle)"
              : "var(--color-hold)",
          }}
          title={pair.actionsAgree ? "verdicts agree" : "verdicts diverge"}
        >
          {pair.actionsAgree ? "→" : "≠"}
        </span>
        {/* The glyph is aria-hidden and a title isn't reliably exposed — the
            agree/diverge judgement must also exist as text. */}
        <span className="sr-only">
          {pair.actionsAgree ? "verdicts agree" : "verdicts diverge"}
        </span>
        <Verdict action={pair.actionOff} score={pair.scoreOff} muted />
      </div>

      {/* Score delta */}
      <div className="flex items-center gap-2 lg:block">
        <LabelMobile>score Δ</LabelMobile>
        <ScoreDelta value={pair.scoreDelta} />
      </div>

      {/* Cost / latency / tokens delta tape */}
      <div className="flex flex-wrap items-center gap-x-4 gap-y-1 font-mono text-2xs tabular-nums">
        <DeltaCell
          label="cost"
          value={pair.costDelta}
          polarity="less-is-better"
          fmt={formatSignedUsd}
        />
        <DeltaCell
          label="lat"
          value={pair.latencyDelta}
          polarity="less-is-better"
          fmt={formatSignedSeconds}
        />
        <DeltaCell
          label="tok"
          value={pair.tokenDelta}
          polarity="less-is-better"
          fmt={formatSignedInt}
        />
      </div>

      {/* Judge */}
      <div className="flex items-center gap-2 lg:justify-end">
        <LabelMobile>judge</LabelMobile>
        <JudgePrefChip pref={pair.judgePreferred} confidence={pair.judgeConfidence} />
      </div>
    </div>
  );
}

function Verdict({
  action,
  score,
  muted,
}: {
  action: EvalPair["actionOn"];
  score: number | null;
  muted?: boolean;
}) {
  if (!action) {
    return (
      <span className="rounded-full border border-[var(--color-line)] px-2 py-0.5 font-mono text-2xs text-[var(--color-fg-subtle)]">
        —
      </span>
    );
  }
  return (
    <span className={muted ? "opacity-60" : undefined}>
      <SignalBadge action={action} score={score ?? undefined} size="sm" />
    </span>
  );
}

function ScoreDelta({ value }: { value: number | null }) {
  const tone = deltaTone(value, "more-is-better");
  return (
    <span
      className="font-mono text-sm font-semibold tabular-nums"
      style={{ color: value == null ? "var(--color-fg-subtle)" : toneColor(tone) }}
    >
      {value == null ? "—" : value > 0 ? `+${value}` : `${value}`}
    </span>
  );
}

function DeltaCell({
  label,
  value,
  polarity,
  fmt,
}: {
  label: string;
  value: number | null;
  polarity: "less-is-better";
  fmt: (v: number | null) => string;
}) {
  const tone = deltaTone(value, polarity);
  return (
    <span className="flex items-baseline gap-1">
      <span className="text-[10px] uppercase tracking-wider text-[var(--color-fg-subtle)]">
        {label}
      </span>
      <span style={{ color: value == null ? "var(--color-fg-subtle)" : toneColor(tone) }}>
        {fmt(value)}
      </span>
    </span>
  );
}

/** A mobile-only inline label (the grid header is hidden under lg). */
function LabelMobile({ children }: { children: React.ReactNode }) {
  return (
    <span className="font-mono text-[10px] uppercase tracking-wider text-[var(--color-fg-subtle)] lg:hidden">
      {children}
    </span>
  );
}

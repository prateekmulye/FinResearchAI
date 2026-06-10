/**
 * CostQualityScatter — the spatial proof of the screen. One point per ticker:
 * x = cost delta (the debate's price), y = score delta (the debate's payoff).
 * The (0,0) origin is the ABLATION BASELINE — the system with the debate OFF
 * (NotebookLM "Zero-Point Crosshair"). Quadrant tints turn position into a
 * literal verdict: top-right faint green = "debate earns its place" (better
 * score, and yes it cost more); bottom-left faint red = "ablate" (worse score
 * AND cheaper off). Points are colored by which pipeline the judge preferred so
 * the A/B semantic is readable at a glance. Hover = a glass Onion-Peel tooltip
 * with the full per-ticker tape (mono).
 *
 * recharts is themed entirely to DESIGN tokens — no default recharts look.
 * CSS-var fills resolve in SVG (unlike the canvas chart lib in WP-9), so we can
 * use OKLCH tokens directly. recharts is lazy-co-located in the EvalPage chunk.
 */
import {
  CartesianGrid,
  Cell,
  ReferenceArea,
  ReferenceLine,
  ResponsiveContainer,
  Scatter,
  ScatterChart,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";

import {
  type EvalPair,
  formatSignedInt,
  formatSignedSeconds,
  formatSignedUsd,
} from "./evalFormat";
import { judgeColor } from "./judgeChrome";

interface Point {
  ticker: string;
  x: number; // cost delta
  y: number; // score delta
  pair: EvalPair;
}

/** Only points with BOTH deltas present can be plotted. */
function toPoints(pairs: EvalPair[]): Point[] {
  return pairs.flatMap((p) =>
    p.costDelta != null && p.scoreDelta != null
      ? [{ ticker: p.ticker, x: p.costDelta, y: p.scoreDelta, pair: p }]
      : [],
  );
}

/** A symmetric axis domain padded around the data so the origin crosshair sits
 *  inside the frame and no point hugs the edge. */
function domain(values: number[], pad = 1.2): [number, number] {
  const max = Math.max(0.0001, ...values.map((v) => Math.abs(v)));
  const m = max * pad;
  return [-m, m];
}

export function CostQualityScatter({ pairs }: { pairs: EvalPair[] }) {
  const points = toPoints(pairs);
  const plotted = points.length;
  const dropped = pairs.length - plotted;

  if (plotted === 0) {
    return (
      <div className="flex h-[360px] flex-col items-center justify-center gap-2 rounded-xl border border-[var(--color-line)] text-center">
        <p className="text-sm font-medium text-[var(--color-fg)]">
          No plottable tickers
        </p>
        <p className="max-w-xs text-xs leading-relaxed text-[var(--color-fg-muted)]">
          A point needs both a cost delta and a score delta. This run didn&rsquo;t
          record paired metrics for any ticker.
        </p>
      </div>
    );
  }

  const xDomain = domain(points.map((p) => p.x));
  const yDomain = domain(points.map((p) => p.y));

  return (
    <div>
      <div className="relative h-[360px] w-full">
        <ResponsiveContainer width="100%" height="100%">
          <ScatterChart margin={{ top: 16, right: 24, bottom: 36, left: 8 }}>
            {/* Quadrant tints — position becomes a verdict (NotebookLM). */}
            {/* Top-right: better score AND costs more → "earns its place". */}
            <ReferenceArea
              x1={0}
              x2={xDomain[1]}
              y1={0}
              y2={yDomain[1]}
              fill="var(--color-bull)"
              fillOpacity={0.05}
              stroke="none"
            />
            {/* Bottom-left: worse score AND cheaper off → "ablate". */}
            <ReferenceArea
              x1={xDomain[0]}
              x2={0}
              y1={yDomain[0]}
              y2={0}
              fill="var(--color-bear)"
              fillOpacity={0.05}
              stroke="none"
            />

            <CartesianGrid
              stroke="var(--color-line)"
              strokeDasharray="2 5"
              vertical
              horizontal
            />

            <XAxis
              type="number"
              dataKey="x"
              domain={xDomain}
              tick={{
                fill: "var(--color-fg-subtle)",
                fontSize: 11,
                fontFamily: "var(--font-mono)",
              }}
              tickFormatter={(v: number) => formatSignedUsd(v)}
              stroke="var(--color-line-strong)"
              tickLine={false}
              axisLine={false}
            />
            <YAxis
              type="number"
              dataKey="y"
              domain={yDomain}
              tick={{
                fill: "var(--color-fg-subtle)",
                fontSize: 11,
                fontFamily: "var(--font-mono)",
              }}
              tickFormatter={(v: number) => (v > 0 ? `+${v}` : `${v}`)}
              stroke="var(--color-line-strong)"
              tickLine={false}
              axisLine={false}
              width={44}
            />

            {/* The Ablation Baseline crosshair through (0,0). */}
            <ReferenceLine
              x={0}
              stroke="var(--color-fg-muted)"
              strokeOpacity={0.5}
              strokeWidth={1}
            />
            <ReferenceLine
              y={0}
              stroke="var(--color-fg-muted)"
              strokeOpacity={0.5}
              strokeWidth={1}
            />

            <Tooltip
              cursor={{ stroke: "var(--color-accent)", strokeOpacity: 0.3 }}
              content={<ScatterTooltip />}
            />

            <Scatter data={points} isAnimationActive={false}>
              {points.map((p) => (
                <Cell
                  key={p.ticker}
                  fill={judgeColor(p.pair.judgePreferred)}
                  stroke="var(--color-base)"
                  strokeWidth={1.5}
                />
              ))}
            </Scatter>
          </ScatterChart>
        </ResponsiveContainer>

        {/* Quadrant corner captions — pure annotation, aria-hidden (the data is
            in the tooltip + table). Absolutely positioned over the plot. */}
        <span
          aria-hidden="true"
          className="pointer-events-none absolute right-3 top-2 font-mono text-[10px] uppercase tracking-wider"
          style={{ color: "var(--color-bull)" }}
        >
          earns its place ↗
        </span>
        <span
          aria-hidden="true"
          className="pointer-events-none absolute bottom-12 left-3 font-mono text-[10px] uppercase tracking-wider"
          style={{ color: "var(--color-bear)" }}
        >
          ↙ ablate
        </span>
      </div>

      {/* Axis intent + dropped-row honesty footnote. */}
      <div className="mt-2 flex flex-wrap items-center justify-between gap-x-4 gap-y-1 px-1 font-mono text-2xs text-[var(--color-fg-subtle)]">
        <span>
          x: debate adds cost → &nbsp;·&nbsp; y: debate adds score ↑ &nbsp;·&nbsp;
          origin = debate OFF baseline
        </span>
        {dropped > 0 && (
          <span style={{ color: "var(--color-hold)" }}>
            {dropped} ticker{dropped === 1 ? "" : "s"} not plotted (missing paired
            metrics)
          </span>
        )}
      </div>
    </div>
  );
}

/** A glass Onion-Peel tooltip: the full per-ticker tape in mono. */
function ScatterTooltip({
  active,
  payload,
}: {
  active?: boolean;
  payload?: Array<{ payload: Point }>;
}) {
  const first = active ? payload?.[0] : undefined;
  if (!first) return null;
  const { pair } = first.payload;
  return (
    <div className="glass-strong min-w-[12rem] rounded-lg p-3 font-mono text-2xs shadow-[var(--shadow-raised)]">
      <div className="mb-2 flex items-center justify-between gap-3">
        <span className="text-sm font-semibold tracking-tight text-[var(--color-fg)]">
          {pair.ticker}
        </span>
        <JudgePref pref={pair.judgePreferred} />
      </div>
      <TooltipRow
        label="verdict"
        value={`${pair.actionOn ?? "—"} → ${pair.actionOff ?? "—"}`}
        agree={pair.actionsAgree}
      />
      <TooltipRow
        label="score"
        value={`${pair.scoreOn ?? "—"} → ${pair.scoreOff ?? "—"} (${
          pair.scoreDelta != null
            ? (pair.scoreDelta > 0 ? "+" : "") + pair.scoreDelta
            : "—"
        })`}
      />
      <TooltipRow label="cost Δ" value={formatSignedUsd(pair.costDelta)} />
      <TooltipRow label="latency Δ" value={formatSignedSeconds(pair.latencyDelta)} />
      <TooltipRow label="tokens Δ" value={formatSignedInt(pair.tokenDelta)} />
    </div>
  );
}

function TooltipRow({
  label,
  value,
  agree,
}: {
  label: string;
  value: string;
  agree?: boolean;
}) {
  return (
    <div className="flex items-baseline justify-between gap-4 py-0.5">
      <span className="text-[var(--color-fg-subtle)]">{label}</span>
      <span className="flex items-center gap-1.5 tabular-nums text-[var(--color-fg)]">
        {value}
        {agree != null && (
          <span
            style={{ color: agree ? "var(--color-bull)" : "var(--color-hold)" }}
          >
            {agree ? "✓" : "≠"}
          </span>
        )}
      </span>
    </div>
  );
}

function JudgePref({ pref }: { pref: EvalPair["judgePreferred"] }) {
  if (pref == null) {
    return (
      <span className="text-[var(--color-fg-subtle)]">unjudged</span>
    );
  }
  return (
    <span
      className="rounded-full px-1.5 py-0.5 text-[10px] uppercase tracking-wide"
      style={{
        color: judgeColor(pref),
        background: "var(--color-glass)",
        border: `1px solid ${judgeColor(pref)}`,
      }}
    >
      {pref === "tie" ? "tie" : `prefers ${pref}`}
    </span>
  );
}

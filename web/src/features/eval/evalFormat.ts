/**
 * evalFormat — the pure, null-safe heart of the eval dashboard. It turns the
 * loose `summary` / `pairs` JSON (backend src/eval/report.py: aggregate() +
 * _per_ticker_rows) into typed view models, and encodes the ONE non-obvious
 * design rule of the screen: **Functional Signal Inversion** — color a signed
 * delta by its OUTCOME UTILITY, not its math sign (NotebookLM). A recruiter must
 * read "cost went up" as a penalty (amber, up-arrow) and "score went up" as a
 * win (green, up-arrow) without reading the label.
 *
 * Everything here is framework-free and exhaustively tested — the page stays a
 * thin renderer over these shapes.
 */
import type { Action } from "@/lib/api";

/* ---------------------------------------------------------------- summary */

/** Normalized headline stats. All fields null-safe: the warehouse summary is a
 *  loose dict, and when `n_judged === 0` the judge rates are reported as 0.0 by
 *  the backend, which we must NOT show as "0% prefer debate" — it's "nothing was
 *  refereed". `judged` carries that distinction up to the band. */
export interface EvalSummary {
  nTickers: number;
  nJudged: number;
  /** True only when at least one pair was actually judged. Gates the hero %. */
  judged: boolean;
  judgePrefersOnRate: number | null; // 0..1, null when nothing judged
  judgeAgreementRate: number | null; // 0..1
  actionAgreementRate: number | null; // 0..1
  meanScoreDelta: number | null;
  scoreDeltaStdev: number | null;
  meanCostDelta: number | null; // USD
  meanLatencyDelta: number | null; // seconds
  meanTokenDelta: number | null;
}

function num(v: unknown): number | null {
  return typeof v === "number" && Number.isFinite(v) ? v : null;
}

/**
 * Read a warehouse `summary` dict into the typed EvalSummary. Tolerant of the
 * long backend key names (mean_*_on_minus_off) AND missing keys — a partial or
 * legacy row degrades to nulls rather than throwing.
 */
export function readSummary(summary: Record<string, unknown>): EvalSummary {
  const nTickers = num(summary.n_tickers) ?? 0;
  const nJudged = num(summary.n_judged) ?? 0;
  const judged = nJudged > 0;
  return {
    nTickers,
    nJudged,
    judged,
    // The judge rates are meaningless with nothing judged — surface null so the
    // UI shows "—" / "no verdicts judged" instead of a fake 0%.
    judgePrefersOnRate: judged ? num(summary.judge_prefers_on_rate) : null,
    judgeAgreementRate: judged ? num(summary.judge_agreement_rate) : null,
    actionAgreementRate: num(summary.action_agreement_rate),
    meanScoreDelta: num(summary.mean_score_delta_on_minus_off),
    scoreDeltaStdev: num(summary.score_delta_stdev),
    meanCostDelta: num(summary.mean_cost_delta_on_minus_off),
    meanLatencyDelta: num(summary.mean_latency_delta_on_minus_off),
    meanTokenDelta: num(summary.mean_token_delta_on_minus_off),
  };
}

/* ------------------------------------------------------------------ pairs */

/** Judge preference is normalized to the pipeline name (src/eval/judge.py):
 *  "on" | "off" | "tie", or null when the pair was never refereed. */
export type JudgePreferred = "on" | "off" | "tie" | null;

export interface EvalPair {
  ticker: string;
  actionOn: Action | null;
  actionOff: Action | null;
  actionsAgree: boolean;
  scoreOn: number | null;
  scoreOff: number | null;
  scoreDelta: number | null;
  costOn: number | null;
  costOff: number | null;
  costDelta: number | null;
  latencyOn: number | null;
  latencyOff: number | null;
  latencyDelta: number | null;
  tokensOn: number | null;
  tokensOff: number | null;
  tokenDelta: number | null;
  judgePreferred: JudgePreferred;
  judgeAgreement: boolean | null;
  judgeConfidence: number | null; // 0..1
}

function action(v: unknown): Action | null {
  return v === "BUY" || v === "SELL" || v === "HOLD" ? v : null;
}

function delta(a: number | null, b: number | null): number | null {
  return a != null && b != null ? a - b : null;
}

function preferred(v: unknown): JudgePreferred {
  return v === "on" || v === "off" || v === "tie" ? v : null;
}

/** Read the loose `pairs` JSON (Any on the wire) into typed EvalPair rows.
 *  Non-array or malformed payloads degrade to []. Each row is independently
 *  null-tolerant so one bad ticker can't blank the table. */
export function readPairs(pairs: unknown): EvalPair[] {
  if (!Array.isArray(pairs)) return [];
  return pairs.map((raw) => {
    const r = (raw ?? {}) as Record<string, unknown>;
    const scoreOn = num(r.score_on);
    const scoreOff = num(r.score_off);
    const costOn = num(r.cost_on);
    const costOff = num(r.cost_off);
    const latOn = num(r.latency_on);
    const latOff = num(r.latency_off);
    const tokOn = num(r.tokens_on);
    const tokOff = num(r.tokens_off);
    return {
      ticker: typeof r.ticker === "string" ? r.ticker : "—",
      actionOn: action(r.action_on),
      actionOff: action(r.action_off),
      // Trust the backend's own equality flag, but fall back to comparing the
      // actions if it's absent (older rows).
      actionsAgree:
        typeof r.actions_agree === "boolean"
          ? r.actions_agree
          : action(r.action_on) === action(r.action_off),
      scoreOn,
      scoreOff,
      scoreDelta: num(r.score_delta) ?? delta(scoreOn, scoreOff),
      costOn,
      costOff,
      costDelta: delta(costOn, costOff),
      latencyOn: latOn,
      latencyOff: latOff,
      latencyDelta: delta(latOn, latOff),
      tokensOn: tokOn,
      tokensOff: tokOff,
      tokenDelta: delta(tokOn, tokOff),
      judgePreferred: preferred(r.judge_preferred),
      judgeAgreement:
        typeof r.judge_agreement === "boolean" ? r.judge_agreement : null,
      judgeConfidence: num(r.judge_confidence),
    };
  });
}

/* ------------------------------------------------ functional signal inversion */

/** Which way a delta is "good". Score: more is better. Cost/latency/tokens:
 *  less is better (the debate's price). */
export type DeltaPolarity = "more-is-better" | "less-is-better";

export type DeltaTone = "good" | "bad" | "neutral";

/** A delta's tone by OUTCOME UTILITY, not math sign (NotebookLM Functional
 *  Signal Inversion). Zero is neutral; null is neutral (no data). */
export function deltaTone(
  value: number | null,
  polarity: DeltaPolarity,
): DeltaTone {
  if (value == null || value === 0) return "neutral";
  const helps = polarity === "more-is-better" ? value > 0 : value < 0;
  return helps ? "good" : "bad";
}

/** The OKLCH token for a delta tone. good→bull green, bad→amber friction,
 *  neutral→muted. We use amber (hold) for "bad cost/latency" deliberately:
 *  it's a friction/penalty signal, not a SELL — red would over-alarm. */
export function toneColor(tone: DeltaTone): string {
  if (tone === "good") return "var(--color-bull)";
  if (tone === "bad") return "var(--color-hold)";
  return "var(--color-fg-muted)";
}

/** Arrow direction for a signed delta (paired with color so meaning never rests
 *  on hue alone). Returns "up" | "down" | "flat". */
export function deltaArrow(value: number | null): "up" | "down" | "flat" {
  if (value == null || value === 0) return "flat";
  return value > 0 ? "up" : "down";
}

/* ----------------------------------------------------------- presentation */

/** A signed percentage from a 0..1 rate. "73%" (unsigned by default). */
export function formatRate(rate: number | null, digits = 0): string {
  if (rate == null || Number.isNaN(rate)) return "—";
  return `${(rate * 100).toFixed(digits)}%`;
}

/** A signed fixed-precision number ("+12.5", "-3.0", "0.0"). */
export function formatSigned(
  value: number | null,
  digits = 1,
): string {
  if (value == null || Number.isNaN(value)) return "—";
  const sign = value > 0 ? "+" : "";
  return `${sign}${value.toFixed(digits)}`;
}

/** A signed USD delta ("+$0.0240", "-$0.0100"). Tiny inference costs need 4dp;
 *  the sign leads so direction reads before magnitude. */
export function formatSignedUsd(value: number | null): string {
  if (value == null || Number.isNaN(value)) return "—";
  const sign = value > 0 ? "+" : value < 0 ? "-" : "";
  const abs = Math.abs(value);
  const body = abs < 0.01 ? abs.toFixed(4) : abs.toFixed(2);
  return `${sign}$${body}`;
}

/** A signed latency delta in seconds ("+2.5s", "-1.0s"). */
export function formatSignedSeconds(value: number | null): string {
  if (value == null || Number.isNaN(value)) return "—";
  const sign = value > 0 ? "+" : "";
  return `${sign}${value.toFixed(1)}s`;
}

/** A signed integer delta with thousands grouping ("+1,240", "-90"). */
export function formatSignedInt(value: number | null): string {
  if (value == null || Number.isNaN(value)) return "—";
  const sign = value > 0 ? "+" : "";
  return `${sign}${value.toLocaleString("en-US")}`;
}

/* ------------------------------------------------------- the proxy disclaimer */

/** The honesty signature of the whole portfolio. Mirrors the SPIRIT of
 *  src/eval/report.py::PROXY_DISCLAIMER (we don't import Python) — kept short
 *  enough to read as a confident methodology note, not fine print. */
export const PROXY_HEADLINE = "This is a judge-preference proxy — not realized P&L.";
export const PROXY_BODY =
  "The harness measures whether the debate pipeline reasons better and/or decides differently than a single-pass baseline, and at what cost, latency, and token premium. It runs no backtest and reports no trading returns. A deep-model referee scores the two verdicts in a fixed A=on / B=off position, so a small positional bias may flatter the debate. Regime coverage is limited to the curated ticker snapshot.";

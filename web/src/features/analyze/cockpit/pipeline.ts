/**
 * pipeline.ts — the pure, framework-free core of the Analyze cockpit.
 *
 * Everything the cockpit renders is a function of the stream-reducer state
 * (AnalysisStreamState) plus the chosen topology. Keeping this pure is what
 * makes the cockpit *replay-ready*: WP-8 can feed a recorded `run_events[]`
 * list through the same reducer and this same mapping with zero UI changes
 * (see useEventPlayer seam in eventPlayer.ts).
 *
 * Two things live here:
 *   1. The static topology (node positions + edges) for both debate modes,
 *      pre-allocated so the xyflow canvas never reflows mid-run (no CLS — NLM).
 *   2. The state mapping: stream state -> per-node visual status + the decoded
 *      structured payloads (analyst reports, theses, trade proposal, stances,
 *      verdicts) the intelligence panels render.
 */
import type { AnalysisStreamState } from "@/hooks/useAnalysisStream";
import type { Action } from "@/lib/api";

/* ----------------------------------------------------------- topology types */

export type DebateTopology = "on" | "off";

/** Visual lifecycle of a single pipeline node. `halted` = the run stopped
 *  (user abort / terminal phase) while this node had started but never
 *  completed — it must stop claiming "running". */
export type NodeStatus = "pending" | "running" | "complete" | "error" | "halted";

/** A stage column in the left->right pipeline (drives the canvas grid). */
export interface StageNode {
  /** Wire node id (matches SSE `node`). */
  id: string;
  /** Column index (0-based, left->right) for canvas layout. */
  col: number;
  /** Row within the column (0-based, top->bottom) for stacked stages. */
  row: number;
}

export interface PipelineEdge {
  from: string;
  to: string;
}

export interface Topology {
  nodes: StageNode[];
  edges: PipelineEdge[];
  /** Total column count, for canvas width math. */
  cols: number;
}

/* ------------------------------------------------------- the two topologies */

// Columns: 0 router · 1 analysts(3 rows) · 2 research(2 rows) · 3 facilitator
//          · 4 trader · 5 risk(2 rows) · 6 arbiter · 7 reporter
const TOPOLOGY_ON: Topology = {
  cols: 8,
  nodes: [
    { id: "router", col: 0, row: 1 },
    { id: "news_analyst", col: 1, row: 0 },
    { id: "fundamentals_analyst", col: 1, row: 1 },
    { id: "technicals_analyst", col: 1, row: 2 },
    { id: "bull", col: 2, row: 0 },
    { id: "bear", col: 2, row: 2 },
    { id: "facilitator", col: 3, row: 1 },
    { id: "trader", col: 4, row: 1 },
    { id: "risk_conservative", col: 5, row: 0 },
    { id: "risk_aggressive", col: 5, row: 2 },
    { id: "risk_arbiter", col: 6, row: 1 },
    { id: "reporter", col: 7, row: 1 },
  ],
  edges: [
    { from: "router", to: "news_analyst" },
    { from: "router", to: "fundamentals_analyst" },
    { from: "router", to: "technicals_analyst" },
    { from: "news_analyst", to: "bull" },
    { from: "fundamentals_analyst", to: "bull" },
    { from: "technicals_analyst", to: "bull" },
    { from: "news_analyst", to: "bear" },
    { from: "fundamentals_analyst", to: "bear" },
    { from: "technicals_analyst", to: "bear" },
    { from: "bull", to: "facilitator" },
    { from: "bear", to: "facilitator" },
    { from: "facilitator", to: "trader" },
    { from: "trader", to: "risk_conservative" },
    { from: "trader", to: "risk_aggressive" },
    { from: "risk_conservative", to: "risk_arbiter" },
    { from: "risk_aggressive", to: "risk_arbiter" },
    { from: "risk_arbiter", to: "reporter" },
  ],
};

// Debate-off: bull/bear/facilitator collapse to a single research_synthesis.
const TOPOLOGY_OFF: Topology = {
  cols: 7,
  nodes: [
    { id: "router", col: 0, row: 1 },
    { id: "news_analyst", col: 1, row: 0 },
    { id: "fundamentals_analyst", col: 1, row: 1 },
    { id: "technicals_analyst", col: 1, row: 2 },
    { id: "research_synthesis", col: 2, row: 1 },
    { id: "trader", col: 3, row: 1 },
    { id: "risk_conservative", col: 4, row: 0 },
    { id: "risk_aggressive", col: 4, row: 2 },
    { id: "risk_arbiter", col: 5, row: 1 },
    { id: "reporter", col: 6, row: 1 },
  ],
  edges: [
    { from: "router", to: "news_analyst" },
    { from: "router", to: "fundamentals_analyst" },
    { from: "router", to: "technicals_analyst" },
    { from: "news_analyst", to: "research_synthesis" },
    { from: "fundamentals_analyst", to: "research_synthesis" },
    { from: "technicals_analyst", to: "research_synthesis" },
    { from: "research_synthesis", to: "trader" },
    { from: "trader", to: "risk_conservative" },
    { from: "trader", to: "risk_aggressive" },
    { from: "risk_conservative", to: "risk_arbiter" },
    { from: "risk_aggressive", to: "risk_arbiter" },
    { from: "risk_arbiter", to: "reporter" },
  ],
};

/**
 * Pick the topology to render.
 *
 * When the caller knows the requested debate mode (the Analyze form passes it
 * as `modeHint`), that wins — an explicit debate-off run renders the synthesis
 * topology from t=0 instead of re-laying-out 12 -> 10 nodes mid-run when
 * `research_synthesis` first appears.
 *
 * Without a hint (the replay case, or a server-default run), we never see
 * `debate_mode` on the wire, so we INFER it from the nodes the stream has
 * actually produced: a `research_synthesis` node means the off-topology. Until
 * research nodes appear we default to the on-topology (the common case and the
 * larger graph, so the canvas can't grow a column mid-run).
 */
export function resolveTopology(
  state: AnalysisStreamState,
  modeHint?: DebateTopology | null,
): {
  topology: Topology;
  mode: DebateTopology;
} {
  if (modeHint === "off") return { topology: TOPOLOGY_OFF, mode: "off" };
  if (modeHint === "on") return { topology: TOPOLOGY_ON, mode: "on" };

  const seen = state.nodes;
  if (seen["research_synthesis"]) return { topology: TOPOLOGY_OFF, mode: "off" };
  if (seen["bull"] || seen["bear"] || seen["facilitator"]) {
    return { topology: TOPOLOGY_ON, mode: "on" };
  }
  return { topology: TOPOLOGY_ON, mode: "on" };
}

/* --------------------------------------------------------- node status map */

/**
 * Derive each topology node's visual status from the stream.
 *
 *  - not seen yet                -> pending
 *  - seen, no completedAt        -> running (while the stream is alive)
 *  - completedAt set             -> complete (or error if the run errored on it)
 *
 * When the whole run errors, the node that was still running flips to `error`
 * so the canvas shows *where* it broke rather than a silent freeze. When the
 * stream is no longer advancing for any other reason (user abort lands the
 * phase back at "idle"; a terminal "done" with a straggler), a started-but-
 * never-completed node renders `halted` — nothing may claim "running" once no
 * more events can arrive.
 */
export function nodeStatuses(
  state: AnalysisStreamState,
  topology: Topology,
): Record<string, NodeStatus> {
  const out: Record<string, NodeStatus> = {};
  const errored = state.phase === "error";
  const alive = state.phase === "streaming" || state.phase === "connecting";

  for (const { id } of topology.nodes) {
    const run = state.nodes[id];
    if (!run) {
      out[id] = "pending";
    } else if (run.completedAt != null) {
      out[id] = "complete";
    } else if (errored) {
      out[id] = "error";
    } else {
      out[id] = alive ? "running" : "halted";
    }
  }
  return out;
}

/**
 * An edge is "live" (animated traveling-signal + marching ants) when its
 * upstream node has completed AND its downstream node is currently running —
 * i.e. data is actively flowing across it. An edge whose downstream is already
 * complete is "settled" (solid, no animation). This welds edge motion to real
 * causality rather than animating everything forever (NLM).
 */
export type EdgeFlow = "idle" | "live" | "settled";

export function edgeFlow(
  edge: PipelineEdge,
  statuses: Record<string, NodeStatus>,
): EdgeFlow {
  const from = statuses[edge.from];
  const to = statuses[edge.to];
  if (from === "complete" && (to === "running" || to === "error")) return "live";
  if (from === "complete" && to === "complete") return "settled";
  return "idle";
}

/* ------------------------------------------------- decoded panel payloads */

export interface AnalystPanel {
  node: string;
  status: NodeStatus;
  /** Streaming token text (may be empty in fake mode — fall back to summary). */
  text: string;
  summary: string | null;
  keyPoints: string[];
  confidence: number | null;
}

export interface DebatePanel {
  mode: DebateTopology;
  bull: { status: NodeStatus; text: string; thesis: string | null };
  bear: { status: NodeStatus; text: string; thesis: string | null };
  /** Facilitator (on) or synthesis (off) verdict text + status. */
  verdict: { status: NodeStatus; text: string };
}

export interface TradePanel {
  status: NodeStatus;
  text: string;
  action: Action | null;
  conviction: number | null;
  score: number | null;
  rationale: string | null;
}

export interface RiskPanel {
  conservative: { status: NodeStatus; text: string; stance: string | null };
  aggressive: { status: NodeStatus; text: string; stance: string | null };
  arbiter: { status: NodeStatus; text: string; resolution: string | null };
}

/* -------- small typed readers over the loosely-typed `delta` blobs -------- */

function str(v: unknown): string | null {
  return typeof v === "string" && v.trim() !== "" ? v : null;
}
function num(v: unknown): number | null {
  return typeof v === "number" && Number.isFinite(v) ? v : null;
}
function strList(v: unknown): string[] {
  return Array.isArray(v) ? v.filter((x): x is string => typeof x === "string") : [];
}
function obj(v: unknown): Record<string, unknown> {
  return v && typeof v === "object" && !Array.isArray(v)
    ? (v as Record<string, unknown>)
    : {};
}

/** The decoded delta a node accumulated (last node_complete wins). */
function delta(state: AnalysisStreamState, node: string): Record<string, unknown> {
  return obj(state.nodes[node]?.delta);
}

export function analystPanel(
  state: AnalysisStreamState,
  statuses: Record<string, NodeStatus>,
  node: string,
): AnalystPanel {
  // analyst delta shape: { analyst_reports: { news|fundamentals|technicals: {...} } }
  const reports = obj(delta(state, node).analyst_reports);
  const key = node.replace(/_analyst$/, ""); // news_analyst -> news
  const report = obj(reports[key]);
  return {
    node,
    status: statuses[node] ?? "pending",
    text: state.nodes[node]?.text ?? "",
    summary: str(report.summary),
    keyPoints: strList(report.key_points),
    confidence: num(report.confidence),
  };
}

export function debatePanel(
  state: AnalysisStreamState,
  statuses: Record<string, NodeStatus>,
  mode: DebateTopology,
): DebatePanel {
  if (mode === "off") {
    const rd = obj(delta(state, "research_synthesis").research_debate);
    return {
      mode,
      bull: { status: "pending", text: "", thesis: null },
      bear: { status: "pending", text: "", thesis: null },
      verdict: {
        status: statuses["research_synthesis"] ?? "pending",
        text:
          str(rd.facilitator_verdict) ??
          state.nodes["research_synthesis"]?.text ??
          "",
      },
    };
  }
  const bullRd = obj(delta(state, "bull").research_debate);
  const bearRd = obj(delta(state, "bear").research_debate);
  const facRd = obj(delta(state, "facilitator").research_debate);
  return {
    mode,
    bull: {
      status: statuses["bull"] ?? "pending",
      text: state.nodes["bull"]?.text ?? "",
      thesis: str(bullRd.bull_thesis),
    },
    bear: {
      status: statuses["bear"] ?? "pending",
      text: state.nodes["bear"]?.text ?? "",
      thesis: str(bearRd.bear_thesis),
    },
    verdict: {
      status: statuses["facilitator"] ?? "pending",
      text: str(facRd.facilitator_verdict) ?? state.nodes["facilitator"]?.text ?? "",
    },
  };
}

export function tradePanel(
  state: AnalysisStreamState,
  statuses: Record<string, NodeStatus>,
): TradePanel {
  const tp = obj(delta(state, "trader").trade_proposal);
  const action = tp.action;
  return {
    status: statuses["trader"] ?? "pending",
    text: state.nodes["trader"]?.text ?? "",
    action:
      action === "BUY" || action === "SELL" || action === "HOLD" ? action : null,
    conviction: num(tp.conviction),
    score: num(tp.score),
    rationale: str(tp.rationale),
  };
}

export function riskPanel(
  state: AnalysisStreamState,
  statuses: Record<string, NodeStatus>,
): RiskPanel {
  const consRd = obj(delta(state, "risk_conservative").risk_debate);
  const aggRd = obj(delta(state, "risk_aggressive").risk_debate);
  const arbRd = obj(delta(state, "risk_arbiter").risk_debate);
  return {
    conservative: {
      status: statuses["risk_conservative"] ?? "pending",
      text: state.nodes["risk_conservative"]?.text ?? "",
      stance: str(consRd.conservative),
    },
    aggressive: {
      status: statuses["risk_aggressive"] ?? "pending",
      text: state.nodes["risk_aggressive"]?.text ?? "",
      stance: str(aggRd.aggressive),
    },
    arbiter: {
      status: statuses["risk_arbiter"] ?? "pending",
      text: state.nodes["risk_arbiter"]?.text ?? "",
      resolution: str(arbRd.arbiter_decision),
    },
  };
}

/* ------------------------------------------------------ cost ticker totals */

export interface CostTotals {
  totalTokens: number;
  costUsd: number;
  /** How many nodes have reported a metric (drives the "live" feel). */
  nodesReporting: number;
  /** Summed per-node compute latency (s) — the honest agent time. */
  latencyS: number;
}

/**
 * Accumulate the live cost ticker.
 *
 * Per-node metrics ride in two places depending on stream stage:
 *   - DURING the run, each node_complete `delta` carries a `run_metrics` array
 *     fragment (the node's own metric line, appended by the operator.add
 *     reducer). We sum those as they land — collision-driven, not a timer.
 *   - AT `done`, the terminal payload carries the full accumulated
 *     `run_metrics`; we prefer that authoritative total once present.
 *
 * Either way the total is a pure function of state, so a replay reproduces the
 * exact same ticker trajectory.
 */
export function costTotals(state: AnalysisStreamState): CostTotals {
  // Prefer the authoritative terminal metrics once the run is done.
  if (state.done) return sumMetrics(state.done.runMetrics);

  // Otherwise accumulate from the per-node delta fragments seen so far.
  const fragments: unknown[] = [];
  for (const id of state.order) {
    const rm = delta(state, id).run_metrics;
    if (Array.isArray(rm)) fragments.push(...rm);
  }
  return sumMetrics(fragments as Record<string, unknown>[]);
}

function sumMetrics(metrics: ReadonlyArray<Record<string, unknown>>): CostTotals {
  let totalTokens = 0;
  let costUsd = 0;
  let nodesReporting = 0;
  let latencyS = 0;
  for (const m of metrics) {
    // Prefer an explicit total_tokens; otherwise derive it from the
    // prompt/completion split (the backend's metric records carry the split,
    // not always a precomputed total).
    const explicit = num(m?.["total_tokens"]);
    const prompt = num(m?.["prompt_tokens"]);
    const completion = num(m?.["completion_tokens"]);
    const t =
      explicit != null
        ? explicit
        : prompt != null || completion != null
          ? (prompt ?? 0) + (completion ?? 0)
          : null;
    const c = num(m?.["cost_usd"]);
    const l = num(m?.["latency_s"]);
    if (t != null || c != null) nodesReporting += 1;
    if (t != null) totalTokens += t;
    if (c != null) costUsd += c;
    if (l != null) latencyS += l;
  }
  return { totalTokens, costUsd, nodesReporting, latencyS };
}

/* ------------------------------------------------------- elapsed wall time */

/** Elapsed seconds from the first node start to the last activity (or now). */
export function elapsedSeconds(state: AnalysisStreamState, now: number): number {
  const starts = state.order
    .map((id) => state.nodes[id]?.startedAt)
    .filter((x): x is number => typeof x === "number");
  if (starts.length === 0) return 0;
  const first = Math.min(...starts);
  if (state.phase === "done" || state.phase === "error") {
    const ends = state.order
      .map((id) => state.nodes[id]?.completedAt)
      .filter((x): x is number => typeof x === "number");
    const last = ends.length ? Math.max(...ends) : now;
    return Math.max(0, (last - first) / 1000);
  }
  return Math.max(0, (now - first) / 1000);
}

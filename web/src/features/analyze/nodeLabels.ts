/**
 * Human labels + phase grouping for the 12 graph nodes (10 in debate-off).
 * Keeps the cockpit readable without leaking raw node ids to the user.
 * Mirrors the topology in src/graph.py.
 */
export interface NodeMeta {
  label: string;
  phase: "Resolve" | "Analysts" | "Debate" | "Trade" | "Risk" | "Report";
}

export const NODE_META: Record<string, NodeMeta> = {
  router: { label: "Router", phase: "Resolve" },
  news_analyst: { label: "News Analyst", phase: "Analysts" },
  fundamentals_analyst: { label: "Fundamentals Analyst", phase: "Analysts" },
  technicals_analyst: { label: "Technicals Analyst", phase: "Analysts" },
  bull: { label: "Bull Researcher", phase: "Debate" },
  bear: { label: "Bear Researcher", phase: "Debate" },
  facilitator: { label: "Facilitator", phase: "Debate" },
  research_synthesis: { label: "Research Synthesis", phase: "Debate" },
  trader: { label: "Trader", phase: "Trade" },
  risk_conservative: { label: "Conservative Risk", phase: "Risk" },
  risk_aggressive: { label: "Aggressive Risk", phase: "Risk" },
  risk_arbiter: { label: "Risk Arbiter", phase: "Risk" },
  reporter: { label: "Reporter", phase: "Report" },
};

export function nodeLabel(node: string): string {
  return NODE_META[node]?.label ?? node;
}

export function nodePhase(node: string): string {
  return NODE_META[node]?.phase ?? "Pipeline";
}

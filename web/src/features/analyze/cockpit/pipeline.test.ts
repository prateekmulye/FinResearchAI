/**
 * pipeline.test.ts — the cockpit's pure core. These cover the contract the rest
 * of the cockpit (canvas + panels + ticker) renders from, for BOTH topologies.
 */
import { describe, expect, it } from "vitest";

import type { AnalysisStreamState, NodeRun } from "@/hooks/useAnalysisStream";

import {
  analystPanel,
  costTotals,
  debatePanel,
  edgeFlow,
  nodeStatuses,
  resolveTopology,
  riskPanel,
  tradePanel,
} from "./pipeline";

function state(overrides: Partial<AnalysisStreamState> = {}): AnalysisStreamState {
  return {
    phase: "streaming",
    runId: "r1",
    ticker: "AAPL",
    investorMode: "Neutral",
    order: [],
    nodes: {},
    done: null,
    error: null,
    errorStatus: null,
    ...overrides,
  };
}

function node(n: string, o: Partial<NodeRun> = {}): NodeRun {
  return { node: n, startedAt: 1000, completedAt: null, text: "", delta: {}, ...o };
}

function withNodes(map: Record<string, NodeRun>, over: Partial<AnalysisStreamState> = {}) {
  return state({ order: Object.keys(map), nodes: map, ...over });
}

describe("resolveTopology", () => {
  it("defaults to the on-topology (12 nodes) before research nodes appear", () => {
    const { topology, mode } = resolveTopology(state());
    expect(mode).toBe("on");
    expect(topology.nodes).toHaveLength(12);
  });

  it("selects the off-topology (10 nodes) once research_synthesis is seen", () => {
    const s = withNodes({ research_synthesis: node("research_synthesis") });
    const { topology, mode } = resolveTopology(s);
    expect(mode).toBe("off");
    expect(topology.nodes).toHaveLength(10);
    expect(topology.nodes.find((n) => n.id === "research_synthesis")).toBeTruthy();
    expect(topology.nodes.find((n) => n.id === "bull")).toBeUndefined();
  });

  it("stays on-topology when bull/bear are present", () => {
    const s = withNodes({ bull: node("bull"), bear: node("bear") });
    expect(resolveTopology(s).mode).toBe("on");
  });

  it("prefers an explicit off-hint from t=0 (no mid-run 12 -> 10 re-layout)", () => {
    const { topology, mode } = resolveTopology(state(), "off");
    expect(mode).toBe("off");
    expect(topology.nodes).toHaveLength(10);
  });

  it("prefers an explicit on-hint", () => {
    const { topology, mode } = resolveTopology(state(), "on");
    expect(mode).toBe("on");
    expect(topology.nodes).toHaveLength(12);
  });

  it("falls back to wire inference when no hint is given (replay case)", () => {
    const s = withNodes({ research_synthesis: node("research_synthesis") });
    expect(resolveTopology(s, null).mode).toBe("off");
    expect(resolveTopology(s).mode).toBe("off");
  });
});

describe("nodeStatuses", () => {
  it("maps unseen -> pending, seen -> running, completed -> complete", () => {
    const { topology } = resolveTopology(state());
    const s = withNodes({
      router: node("router", { completedAt: 2000 }),
      news_analyst: node("news_analyst"), // running
    });
    const st = nodeStatuses(s, topology);
    expect(st["router"]).toBe("complete");
    expect(st["news_analyst"]).toBe("running");
    expect(st["bull"]).toBe("pending"); // unseen
  });

  it("flips the still-running node to error when the run errors", () => {
    const { topology } = resolveTopology(state());
    const s = withNodes(
      {
        router: node("router", { completedAt: 2000 }),
        news_analyst: node("news_analyst"), // was running when it broke
      },
      { phase: "error", error: "boom" },
    );
    const st = nodeStatuses(s, topology);
    expect(st["router"]).toBe("complete");
    expect(st["news_analyst"]).toBe("error");
  });

  it("post-abort (phase idle): no node reports running — incomplete nodes halt", () => {
    // A user Stop lands the reducer back at "idle" with the node map intact.
    // The cockpit stays mounted, so a started-but-never-completed node must
    // stop claiming "running" — nothing more can ever arrive for it.
    const { topology } = resolveTopology(state());
    const s = withNodes(
      {
        router: node("router", { completedAt: 2000 }),
        news_analyst: node("news_analyst"), // was mid-flight when stopped
      },
      { phase: "idle" },
    );
    const st = nodeStatuses(s, topology);
    expect(st["router"]).toBe("complete");
    expect(st["news_analyst"]).toBe("halted");
    expect(st["bull"]).toBe("pending"); // never started — stays dim pending
    expect(Object.values(st)).not.toContain("running");
  });

  it("phase done: a straggler that never completed halts rather than runs", () => {
    const { topology } = resolveTopology(state());
    const s = withNodes(
      { reporter: node("reporter") },
      {
        phase: "done",
        done: { finalReport: "# r", finalDecision: null, runMetrics: [] },
      },
    );
    expect(nodeStatuses(s, topology)["reporter"]).toBe("halted");
  });
});

describe("edgeFlow", () => {
  const statuses = {
    router: "complete" as const,
    news_analyst: "running" as const,
    bull: "pending" as const,
  };
  it("is live when upstream complete and downstream running", () => {
    expect(edgeFlow({ from: "router", to: "news_analyst" }, statuses)).toBe("live");
  });
  it("is settled when both ends complete", () => {
    expect(
      edgeFlow(
        { from: "router", to: "news_analyst" },
        { ...statuses, news_analyst: "complete" },
      ),
    ).toBe("settled");
  });
  it("is idle when upstream not yet complete", () => {
    expect(edgeFlow({ from: "news_analyst", to: "bull" }, statuses)).toBe("idle");
  });
});

describe("analystPanel decodes the analyst_reports delta", () => {
  it("reads summary/key_points/confidence keyed by the analyst name", () => {
    const s = withNodes({
      news_analyst: node("news_analyst", {
        completedAt: 2000,
        delta: {
          analyst_reports: {
            news: {
              summary: "Coverage skews constructive.",
              key_points: ["beat consensus", "targets drifting up"],
              confidence: 0.78,
            },
          },
        },
      }),
    });
    const { topology } = resolveTopology(s);
    const st = nodeStatuses(s, topology);
    const p = analystPanel(s, st, "news_analyst");
    expect(p.status).toBe("complete");
    expect(p.summary).toBe("Coverage skews constructive.");
    expect(p.keyPoints).toEqual(["beat consensus", "targets drifting up"]);
    expect(p.confidence).toBe(0.78);
  });

  it("falls back to empty fields (no crash) when the delta is absent", () => {
    const s = withNodes({ news_analyst: node("news_analyst", { text: "streaming…" }) });
    const { topology } = resolveTopology(s);
    const p = analystPanel(s, nodeStatuses(s, topology), "news_analyst");
    expect(p.summary).toBeNull();
    expect(p.keyPoints).toEqual([]);
    expect(p.text).toBe("streaming…");
  });
});

describe("debatePanel", () => {
  it("on-topology: reads bull/bear theses + facilitator verdict from deltas", () => {
    const s = withNodes({
      bull: node("bull", {
        completedAt: 2000,
        delta: { research_debate: { bull_thesis: "accumulate here" } },
      }),
      bear: node("bear", {
        completedAt: 2100,
        delta: { research_debate: { bear_thesis: "valuation rich" } },
      }),
      facilitator: node("facilitator", {
        completedAt: 2200,
        delta: { research_debate: { facilitator_verdict: "leans bullish" } },
      }),
    });
    const { topology, mode } = resolveTopology(s);
    const p = debatePanel(s, nodeStatuses(s, topology), mode);
    expect(p.mode).toBe("on");
    expect(p.bull.thesis).toBe("accumulate here");
    expect(p.bear.thesis).toBe("valuation rich");
    expect(p.verdict.text).toBe("leans bullish");
    expect(p.verdict.status).toBe("complete");
  });

  it("off-topology: single synthesis verdict, no bull/bear columns", () => {
    const s = withNodes({
      research_synthesis: node("research_synthesis", {
        completedAt: 2000,
        delta: { research_debate: { facilitator_verdict: "single-pass verdict" } },
      }),
    });
    const { topology, mode } = resolveTopology(s);
    const p = debatePanel(s, nodeStatuses(s, topology), mode);
    expect(p.mode).toBe("off");
    expect(p.verdict.text).toBe("single-pass verdict");
    expect(p.bull.status).toBe("pending");
  });
});

describe("tradePanel + riskPanel", () => {
  it("tradePanel decodes the trade_proposal delta", () => {
    const s = withNodes({
      trader: node("trader", {
        completedAt: 2000,
        delta: {
          trade_proposal: {
            action: "BUY",
            conviction: 0.74,
            score: 74,
            rationale: "BUY AAPL.",
          },
        },
      }),
    });
    const { topology } = resolveTopology(s);
    const p = tradePanel(s, nodeStatuses(s, topology));
    expect(p.action).toBe("BUY");
    expect(p.score).toBe(74);
    expect(p.rationale).toBe("BUY AAPL.");
  });

  it("riskPanel decodes conservative/aggressive stances + arbiter resolution", () => {
    const s = withNodes({
      risk_conservative: node("risk_conservative", {
        completedAt: 2000,
        delta: { risk_debate: { conservative: "size down" } },
      }),
      risk_aggressive: node("risk_aggressive", {
        completedAt: 2100,
        delta: { risk_debate: { aggressive: "lean in" } },
      }),
      risk_arbiter: node("risk_arbiter", {
        completedAt: 2200,
        delta: { risk_debate: { arbiter_decision: "sized between" } },
      }),
    });
    const { topology } = resolveTopology(s);
    const st = nodeStatuses(s, topology);
    const p = riskPanel(s, st);
    expect(p.conservative.stance).toBe("size down");
    expect(p.aggressive.stance).toBe("lean in");
    expect(p.arbiter.resolution).toBe("sized between");
  });

  it("ignores an invalid action value rather than rendering garbage", () => {
    const s = withNodes({
      trader: node("trader", {
        completedAt: 2000,
        delta: { trade_proposal: { action: "MAYBE", score: 50 } },
      }),
    });
    const { topology } = resolveTopology(s);
    expect(tradePanel(s, nodeStatuses(s, topology)).action).toBeNull();
  });
});

describe("costTotals — accumulation", () => {
  it("sums per-node run_metrics fragments from deltas during the run", () => {
    const s = withNodes({
      router: node("router", {
        completedAt: 2000,
        delta: { run_metrics: [{ node: "router", total_tokens: 100, cost_usd: 0.001 }] },
      }),
      news_analyst: node("news_analyst", {
        completedAt: 2100,
        delta: {
          run_metrics: [{ node: "news_analyst", total_tokens: 250, cost_usd: 0.002 }],
        },
      }),
    });
    const totals = costTotals(s);
    expect(totals.totalTokens).toBe(350);
    expect(totals.costUsd).toBeCloseTo(0.003, 6);
    expect(totals.nodesReporting).toBe(2);
  });

  it("prefers the authoritative terminal run_metrics once done", () => {
    const s = withNodes(
      {
        router: node("router", {
          completedAt: 2000,
          delta: { run_metrics: [{ node: "router", total_tokens: 100 }] },
        }),
      },
      {
        phase: "done",
        done: {
          finalReport: "# r",
          finalDecision: null,
          runMetrics: [
            { node: "router", total_tokens: 100, cost_usd: 0.001 },
            { node: "reporter", total_tokens: 900, cost_usd: 0.009 },
          ],
        },
      },
    );
    const totals = costTotals(s);
    expect(totals.totalTokens).toBe(1000);
    expect(totals.costUsd).toBeCloseTo(0.01, 6);
  });

  it("derives total_tokens from prompt+completion when no total is given", () => {
    // This mirrors the real backend metric shape (prompt_tokens +
    // completion_tokens, no precomputed total_tokens).
    const s = withNodes({
      router: node("router", {
        completedAt: 2000,
        delta: {
          run_metrics: [
            {
              node: "router",
              prompt_tokens: 129,
              completion_tokens: 90,
              latency_s: 0.214,
            },
          ],
        },
      }),
    });
    const totals = costTotals(s);
    expect(totals.totalTokens).toBe(219);
    expect(totals.latencyS).toBeCloseTo(0.214, 6);
  });

  it("returns zeroes (no NaN) when no metrics have landed", () => {
    const totals = costTotals(state());
    expect(totals.totalTokens).toBe(0);
    expect(totals.costUsd).toBe(0);
    expect(totals.nodesReporting).toBe(0);
  });
});

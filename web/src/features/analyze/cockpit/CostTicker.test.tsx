/**
 * CostTicker renders cumulative tokens + cost + elapsed from stream state.
 */
import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import type { AnalysisStreamState, NodeRun } from "@/hooks/useAnalysisStream";

import { CostTicker } from "./CostTicker";

function node(n: string, o: Partial<NodeRun> = {}): NodeRun {
  return { node: n, startedAt: 1000, completedAt: null, text: "", delta: {}, ...o };
}

function state(over: Partial<AnalysisStreamState> = {}): AnalysisStreamState {
  return {
    phase: "streaming",
    runId: "r1",
    ticker: "AAPL",
    investorMode: "Neutral",
    order: [],
    nodes: {},
    done: null,
    error: null,
    ...over,
  };
}

describe("CostTicker", () => {
  it("renders the summed tokens + cost from per-node deltas", () => {
    const s = state({
      order: ["router", "news_analyst"],
      nodes: {
        router: node("router", {
          completedAt: 2000,
          delta: { run_metrics: [{ node: "router", total_tokens: 120, cost_usd: 0.001 }] },
        }),
        news_analyst: node("news_analyst", {
          completedAt: 2100,
          delta: {
            run_metrics: [{ node: "news_analyst", total_tokens: 380, cost_usd: 0.003 }],
          },
        }),
      },
    });
    render(<CostTicker state={s} />);
    expect(screen.getByText("500")).toBeInTheDocument(); // 120 + 380 tokens
    expect(screen.getByText("$0.0040")).toBeInTheDocument(); // 0.001 + 0.003
  });

  it("exposes a labelled live status region", () => {
    render(<CostTicker state={state()} />);
    expect(screen.getByRole("status", { name: /live run cost/i })).toBeInTheDocument();
  });
});

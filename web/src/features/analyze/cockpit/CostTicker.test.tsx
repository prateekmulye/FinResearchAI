/**
 * CostTicker renders cumulative tokens + cost + elapsed from stream state.
 * It must NOT be a live region (its 1Hz clock would announce every second);
 * the terminal summary is announced once by the StatusAnnouncer instead.
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
    errorStatus: null,
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

  it("is a labelled group, NOT a live region (no per-second announcements)", () => {
    render(<CostTicker state={state()} />);
    const group = screen.getByRole("group", { name: /run cost/i });
    expect(group).toBeInTheDocument();
    expect(group).not.toHaveAttribute("aria-live");
    expect(screen.queryByRole("status")).not.toBeInTheDocument();
  });

  it("shows wall time at done — parallel nodes make summed latency exceed it", () => {
    // Wall clock: 30s (1000 -> 31000). Summed per-node latency: 50s.
    const s = state({
      phase: "done",
      order: ["router"],
      nodes: { router: node("router", { startedAt: 1000, completedAt: 31000 }) },
      done: {
        finalReport: "# r",
        finalDecision: null,
        runMetrics: [
          { node: "router", latency_s: 20 },
          { node: "news_analyst", latency_s: 30 },
        ],
      },
    });
    render(<CostTicker state={s} />);
    expect(screen.getByText("30s")).toBeInTheDocument();
  });

  it("replay: elapsed comes from the recorded timeline, never the wall clock", () => {
    // Mid-replay state: lifecycle stamps are synthetic fold ticks (1, 2, 3…).
    // Date.now() minus a synthetic tick is the epoch-seconds regression
    // (ELAPSED rendered e.g. "1781139085s"); replayElapsedMs must win instead.
    const s = state({
      order: ["router"],
      nodes: { router: node("router", { startedAt: 1, completedAt: 2 }) },
    });
    render(<CostTicker state={s} replayElapsedMs={12_400} />);
    expect(screen.getByText("12s")).toBeInTheDocument();
    // No epoch-scale seconds readout anywhere in the ticker.
    expect(screen.queryByText(/\d{5,}s/)).not.toBeInTheDocument();
  });

  it("replay: a playhead parked at the start reads 0.0s", () => {
    const s = state({
      order: ["router"],
      nodes: { router: node("router", { startedAt: 1 }) },
    });
    render(<CostTicker state={s} replayElapsedMs={0} />);
    expect(screen.getByText("0.0s")).toBeInTheDocument();
  });

  it("substitutes summed node latency only for a trivially short wall clock (cached run)", () => {
    // Wall clock: 0.5s (a near-instant cached/fake run). Summed latency: 3.2s.
    const s = state({
      phase: "done",
      order: ["router"],
      nodes: { router: node("router", { startedAt: 1000, completedAt: 1500 }) },
      done: {
        finalReport: "# r",
        finalDecision: null,
        runMetrics: [{ node: "router", latency_s: 3.2 }],
      },
    });
    render(<CostTicker state={s} />);
    expect(screen.getByText("3.2s")).toBeInTheDocument();
  });
});

/**
 * StatusAnnouncer — the cockpit's single polite live region.
 *
 * Always mounted (never inside a collapsed <details>, never null), it announces
 * node completions while streaming and the terminal cost summary exactly once
 * on done. Token mutations must NOT change the announcement.
 */
import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import type { AnalysisStreamState, NodeRun } from "@/hooks/useAnalysisStream";

import { StatusAnnouncer } from "./StatusAnnouncer";

function makeState(overrides: Partial<AnalysisStreamState> = {}): AnalysisStreamState {
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

function makeNode(node: string, overrides: Partial<NodeRun> = {}): NodeRun {
  return { node, startedAt: 1000, completedAt: null, text: "", delta: {}, ...overrides };
}

describe("StatusAnnouncer", () => {
  it("stays mounted (empty announcement) even before any node streams", () => {
    render(<StatusAnnouncer state={makeState({ phase: "connecting" })} />);
    expect(screen.getByRole("status")).toBeInTheDocument();
  });

  it("announces the most recent node completion via a polite status element", () => {
    const state = makeState({
      order: ["router", "news_analyst"],
      nodes: {
        router: makeNode("router", { completedAt: 2000 }),
        news_analyst: makeNode("news_analyst", { completedAt: 3000 }),
      },
    });
    render(<StatusAnnouncer state={state} />);
    expect(screen.getByRole("status")).toHaveTextContent(/news analyst complete/i);
  });

  it("does not change the announcement when only token text mutates", () => {
    const base = makeState({
      order: ["router", "reporter"],
      nodes: {
        router: makeNode("router", { completedAt: 2000 }),
        reporter: makeNode("reporter", { text: "partial" }),
      },
    });
    const { rerender } = render(<StatusAnnouncer state={base} />);
    const before = screen.getByRole("status").textContent;

    rerender(
      <StatusAnnouncer
        state={{
          ...base,
          nodes: {
            ...base.nodes,
            reporter: makeNode("reporter", { text: "partial plus more tokens" }),
          },
        }}
      />,
    );
    expect(screen.getByRole("status").textContent).toBe(before);
  });

  it("announces completion with the terminal cost summary on done", () => {
    const state = makeState({
      phase: "done",
      order: ["reporter"],
      nodes: { reporter: makeNode("reporter", { completedAt: 2000 }) },
      done: {
        finalReport: "# R",
        finalDecision: null,
        runMetrics: [
          { node: "router", total_tokens: 100, cost_usd: 0.001 },
          { node: "reporter", total_tokens: 400, cost_usd: 0.003 },
        ],
      },
    });
    render(<StatusAnnouncer state={state} />);
    const status = screen.getByRole("status");
    expect(status).toHaveTextContent(/analysis complete/i);
    expect(status).toHaveTextContent("500 tokens");
    expect(status).toHaveTextContent("$0.0040");
  });

  it("replay: announces done WITHOUT the bogus fold-tick elapsed", () => {
    // Replay state stamps node lifecycles with synthetic fold ticks; deriving
    // elapsed from them announced "0s elapsed". In replay the announcement
    // states the cost summary and stays silent about wall time.
    const state = makeState({
      phase: "done",
      order: ["reporter"],
      nodes: { reporter: makeNode("reporter", { startedAt: 1, completedAt: 2 }) },
      done: {
        finalReport: "# R",
        finalDecision: null,
        runMetrics: [{ node: "reporter", total_tokens: 400, cost_usd: 0.003 }],
      },
    });
    render(<StatusAnnouncer state={state} isReplay />);
    const status = screen.getByRole("status");
    expect(status).toHaveTextContent(/analysis complete/i);
    expect(status).toHaveTextContent("400 tokens");
    expect(status).not.toHaveTextContent(/elapsed/i);
  });
});

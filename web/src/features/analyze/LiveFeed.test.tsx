/**
 * LiveFeed — a11y live-region contract.
 *
 * The token stream mutates list rows many times per second; that list must NOT
 * be a live region (it would spam screen readers). Announcements are scoped to
 * a visually-hidden status element that only changes on node completions.
 */
import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { LiveFeed } from "@/features/analyze/LiveFeed";
import type { AnalysisStreamState, NodeRun } from "@/hooks/useAnalysisStream";

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
    ...overrides,
  };
}

function makeNode(node: string, overrides: Partial<NodeRun> = {}): NodeRun {
  return { node, startedAt: 1000, completedAt: null, text: "", ...overrides };
}

describe("LiveFeed — live region scoping", () => {
  it("does not mark the token-mutating list as a live region", () => {
    const state = makeState({
      order: ["router"],
      nodes: { router: makeNode("router", { text: "streaming tokens…" }) },
    });
    render(<LiveFeed state={state} />);
    expect(screen.getByRole("list")).not.toHaveAttribute("aria-live");
  });

  it("announces the most recent node completion via a polite status element", () => {
    const state = makeState({
      order: ["router", "news_analyst"],
      nodes: {
        router: makeNode("router", { completedAt: 2000 }),
        news_analyst: makeNode("news_analyst", { completedAt: 3000 }),
      },
    });
    render(<LiveFeed state={state} />);
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
    const { rerender } = render(<LiveFeed state={base} />);
    const before = screen.getByRole("status").textContent;

    rerender(
      <LiveFeed
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

  it("announces completion of the whole analysis", () => {
    const state = makeState({
      phase: "done",
      order: ["reporter"],
      nodes: { reporter: makeNode("reporter", { completedAt: 2000 }) },
    });
    render(<LiveFeed state={state} />);
    expect(screen.getByRole("status")).toHaveTextContent(/analysis complete/i);
  });
});

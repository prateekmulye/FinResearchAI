/**
 * LiveFeed — visual transcript contract.
 *
 * The token stream mutates list rows many times per second; that list must NOT
 * be a live region (it would spam screen readers). Announcements live in the
 * always-mounted StatusAnnouncer (cockpit/StatusAnnouncer.tsx), NOT here — the
 * transcript renders inside a collapsed <details>, which would mute them.
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
    errorStatus: null,
    ...overrides,
  };
}

function makeNode(node: string, overrides: Partial<NodeRun> = {}): NodeRun {
  return { node, startedAt: 1000, completedAt: null, text: "", delta: {}, ...overrides };
}

describe("LiveFeed — visual transcript only", () => {
  it("does not mark the token-mutating list as a live region", () => {
    const state = makeState({
      order: ["router"],
      nodes: { router: makeNode("router", { text: "streaming tokens…" }) },
    });
    render(<LiveFeed state={state} />);
    expect(screen.getByRole("list")).not.toHaveAttribute("aria-live");
  });

  it("contains no live announcer at all (that's the StatusAnnouncer's job)", () => {
    const state = makeState({
      order: ["router", "news_analyst"],
      nodes: {
        router: makeNode("router", { completedAt: 2000 }),
        news_analyst: makeNode("news_analyst", { completedAt: 3000 }),
      },
    });
    render(<LiveFeed state={state} />);
    expect(screen.queryByRole("status")).not.toBeInTheDocument();
  });

  it("renders one row per node with its completion state", () => {
    const state = makeState({
      order: ["router", "reporter"],
      nodes: {
        router: makeNode("router", { completedAt: 2000 }),
        reporter: makeNode("reporter", { text: "partial" }),
      },
    });
    render(<LiveFeed state={state} />);
    const rows = screen.getAllByRole("listitem");
    expect(rows).toHaveLength(2);
    expect(rows[0]).toHaveTextContent(/router/i);
    expect(rows[1]).toHaveTextContent(/streaming/i);
  });
});

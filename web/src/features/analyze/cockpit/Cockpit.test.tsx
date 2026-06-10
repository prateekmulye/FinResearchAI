/**
 * Cockpit — assembly-level a11y + topology contracts.
 *
 * 1. The polite announcer must be in the accessibility tree at all times while
 *    streaming — i.e. mounted OUTSIDE the collapsed <details> transcript (a
 *    closed <details> removes its subtree from the a11y tree).
 * 2. An explicit debate-off run (modeHint="off") must render the synthesis
 *    topology from t=0 — never a mid-run 12 -> 10 node re-layout.
 */
import { render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import type { AnalysisStreamState, NodeRun } from "@/hooks/useAnalysisStream";

import { Cockpit } from "./Cockpit";

// xyflow needs real layout; the canvas is aria-hidden decoration anyway.
vi.mock("./PipelineCanvas", () => ({
  PipelineCanvas: () => <div data-testid="pipeline-canvas" />,
}));

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

describe("Cockpit — live announcer placement", () => {
  it("mounts the status announcer outside any <details> while streaming", () => {
    const state = makeState({
      order: ["router"],
      nodes: { router: makeNode("router", { completedAt: 2000 }) },
    });
    const { container } = render(<Cockpit state={state} />);

    // The collapsed transcript exists…
    expect(container.querySelector("details")).not.toBeNull();

    // …but the polite announcer must NOT live inside it.
    const status = screen.getByRole("status");
    expect(status.closest("details")).toBeNull();
    expect(status).toHaveTextContent(/router complete/i);
  });

  it("keeps the announcer mounted before any node has streamed", () => {
    const { container } = render(
      <Cockpit state={makeState({ phase: "connecting" })} />,
    );
    expect(container.querySelector("details")).toBeNull();
    expect(screen.getByRole("status")).toBeInTheDocument();
  });
});

describe("Cockpit — topology hint", () => {
  it("renders the synthesis topology from t=0 on an explicit debate-off run", () => {
    render(<Cockpit state={makeState({ phase: "connecting" })} modeHint="off" />);
    expect(screen.getByText(/10 nodes · debate off/i)).toBeInTheDocument();
  });

  it("defaults to the full debate topology without a hint", () => {
    render(<Cockpit state={makeState({ phase: "connecting" })} />);
    expect(screen.getByText(/12 nodes · debate on/i)).toBeInTheDocument();
  });
});

/**
 * Cockpit — assembly-level a11y + topology + render-economy contracts.
 *
 * 1. The polite announcer must be in the accessibility tree at all times while
 *    streaming — i.e. mounted OUTSIDE the collapsed <details> transcript (a
 *    closed <details> removes its subtree from the a11y tree).
 * 2. An explicit debate-off run (modeHint="off") must render the synthesis
 *    topology from t=0 — never a mid-run 12 -> 10 node re-layout.
 * 3. PERF: a token-only event must NOT re-render PipelineCanvas (the
 *    `statuses` prop keeps a stable identity), and a parent re-render with
 *    identity-stable props must not re-run the Cockpit body at all (React.memo
 *    — the replay theater re-renders ~60fps while the playhead advances).
 */
import { fireEvent, render, screen } from "@testing-library/react";
import { useState } from "react";
import { describe, expect, it, vi } from "vitest";

import type { AnalysisStreamState, NodeRun } from "@/hooks/useAnalysisStream";

import { Cockpit } from "./Cockpit";
import type * as PipelineNs from "./pipeline";

const probe = vi.hoisted(() => ({ canvasRenders: 0, nodeStatusCalls: 0 }));

// xyflow needs real layout; the canvas is aria-hidden decoration anyway. The
// mock is memo'd with the default shallow comparison, so its render count is
// the probe for "did Cockpit hand the canvas identity-stable props?".
vi.mock("./PipelineCanvas", async () => {
  const { memo } = await import("react");
  return {
    PipelineCanvas: memo(function PipelineCanvas() {
      probe.canvasRenders += 1;
      return <div data-testid="pipeline-canvas" />;
    }),
  };
});

// Wrap (not replace) the pure pipeline core: the Cockpit body calls
// nodeStatuses exactly once per render, so its call count is the probe for
// "did the memo'd Cockpit body actually re-run?".
vi.mock("./pipeline", async (importOriginal) => {
  const actual = await importOriginal<typeof PipelineNs>();
  return {
    ...actual,
    nodeStatuses: (...args: Parameters<typeof actual.nodeStatuses>) => {
      probe.nodeStatusCalls += 1;
      return actual.nodeStatuses(...args);
    },
  };
});

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

describe("Cockpit — render economy", () => {
  it("a token-only event does not re-render PipelineCanvas", () => {
    const base = makeState({
      order: ["router"],
      nodes: { router: makeNode("router", { text: "thin" }) },
    });
    const { rerender } = render(<Cockpit state={base} />);
    const afterMount = probe.canvasRenders;

    // A token event: NEW state identity, same per-node lifecycle. The token
    // stream produces these many times per second — the canvas must skip.
    rerender(
      <Cockpit
        state={{
          ...base,
          nodes: { router: makeNode("router", { text: "thinking…" }) },
        }}
      />,
    );
    expect(probe.canvasRenders).toBe(afterMount);

    // A lifecycle change (node completed) MUST re-render the canvas.
    rerender(
      <Cockpit
        state={{
          ...base,
          nodes: { router: makeNode("router", { text: "thinking…", completedAt: 2000 }) },
        }}
      />,
    );
    expect(probe.canvasRenders).toBe(afterMount + 1);
  });

  it("a parent re-render with identity-stable props skips the Cockpit body (memo)", () => {
    // The replay theater re-renders its page per rAF frame while the playhead
    // moves; between recorded events every Cockpit prop is identity-stable.
    const state = makeState({
      order: ["router"],
      nodes: { router: makeNode("router", { completedAt: 2000 }) },
    });
    function Host() {
      const [, setTick] = useState(0);
      return (
        <>
          <button onClick={() => setTick((t) => t + 1)}>advance playhead</button>
          <Cockpit state={state} replayElapsedMs={500} />
        </>
      );
    }
    render(<Host />);
    const afterMount = probe.nodeStatusCalls;

    fireEvent.click(screen.getByRole("button", { name: /advance playhead/i }));
    expect(probe.nodeStatusCalls).toBe(afterMount);
  });
});

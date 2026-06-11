/**
 * RunDossier — render economy. The replay theater re-renders its page ~60fps
 * while the rAF playhead advances; the dossier header's props (the fetched run
 * + the fixed duration label) never change after load, so React.memo must skip
 * it on every frame. The probe: RunDossier is the only component in this tree
 * that calls formatRelativeTime — its call count IS the dossier render count.
 */
import { fireEvent, render, screen } from "@testing-library/react";
import { useState } from "react";
import { MemoryRouter } from "react-router";
import { describe, expect, it, vi } from "vitest";

import type { RunDetail } from "@/lib/api";
import type * as UtilsNs from "@/lib/utils";

import { RunDossier } from "./RunDossier";

const probe = vi.hoisted(() => ({ relativeTimeCalls: 0 }));

vi.mock("@/lib/utils", async (importOriginal) => {
  const actual = await importOriginal<typeof UtilsNs>();
  return {
    ...actual,
    formatRelativeTime: (...args: Parameters<typeof actual.formatRelativeTime>) => {
      probe.relativeTimeCalls += 1;
      return actual.formatRelativeTime(...args);
    },
  };
});

function makeRun(): RunDetail {
  return {
    run_id: "0bd902d9d393",
    source: "warehouse",
    ticker: "AAPL",
    debate_mode: "on",
    status: "finished",
    started_at: "2026-06-09T12:00:00Z",
    finished_at: "2026-06-09T12:00:10Z",
    final_decision: { action: "BUY", conviction: 0.82, score: 86, rationale: "strong" },
    report: "# AAPL",
    metrics: [],
    cost: null,
    events: [],
  };
}

describe("RunDossier — memoized against playhead-driven parent re-renders", () => {
  it("does not re-render when the parent re-renders with identical props", () => {
    const run = makeRun();
    function Theater() {
      const [, setPlayhead] = useState(0);
      return (
        <>
          <button onClick={() => setPlayhead((t) => t + 16)}>frame</button>
          <RunDossier run={run} durationLabel="0:12" />
        </>
      );
    }
    render(
      <MemoryRouter>
        <Theater />
      </MemoryRouter>,
    );
    expect(screen.getByRole("heading", { name: "AAPL" })).toBeInTheDocument();
    const afterMount = probe.relativeTimeCalls;
    expect(afterMount).toBeGreaterThan(0);

    // Simulate the rAF playhead: parent state changes, dossier props don't.
    fireEvent.click(screen.getByRole("button", { name: "frame" }));
    fireEvent.click(screen.getByRole("button", { name: "frame" }));
    expect(probe.relativeTimeCalls).toBe(afterMount);
  });
});

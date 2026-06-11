/**
 * AnalyzePage — quota freshness. The nav QuotaPill reads the ["quota"] query on
 * a lazy 60s poll; a live run changes the backend counters immediately. The
 * page must invalidate ["quota"] when a run starts (connecting) and when it
 * lands (done / error — including a 429 refusal), so the pill never shows a
 * stale "N runs left" after a run.
 */
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render } from "@testing-library/react";
import { MemoryRouter } from "react-router";
import { beforeEach, describe, expect, it, vi } from "vitest";

import {
  initialState,
  type AnalysisStreamState,
} from "@/hooks/analysisReducer";

import { AnalyzePage } from "./AnalyzePage";

// The cockpit pulls in xyflow/markdown — irrelevant here, stub it out.
vi.mock("@/features/analyze/cockpit/Cockpit", () => ({
  Cockpit: () => <div data-testid="cockpit" />,
}));

const streamState = vi.fn<() => AnalysisStreamState>(() => initialState);
vi.mock("@/hooks/useAnalysisStream", () => ({
  useAnalysisStream: () => ({
    state: streamState(),
    isActive: false,
    start: vi.fn(),
    stop: vi.fn(),
    reset: vi.fn(),
  }),
}));

function renderPage(client: QueryClient) {
  return render(
    <QueryClientProvider client={client}>
      <MemoryRouter>
        <AnalyzePage />
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

beforeEach(() => streamState.mockReturnValue(initialState));

describe("AnalyzePage — quota invalidation", () => {
  it("invalidates ['quota'] when a run starts and again when it completes", () => {
    const client = new QueryClient();
    const invalidate = vi.spyOn(client, "invalidateQueries");

    const { rerender } = renderPage(client);
    expect(invalidate).not.toHaveBeenCalled(); // idle: nothing to refresh

    // Run starts — the backend reserves a quota slot right away.
    streamState.mockReturnValue({ ...initialState, phase: "connecting" });
    rerender(
      <QueryClientProvider client={client}>
        <MemoryRouter>
          <AnalyzePage />
        </MemoryRouter>
      </QueryClientProvider>,
    );
    expect(invalidate).toHaveBeenCalledWith({ queryKey: ["quota"] });

    // Run lands — counters are settled; refresh again.
    invalidate.mockClear();
    streamState.mockReturnValue({
      ...initialState,
      phase: "done",
      done: { finalReport: "# r", finalDecision: null, runMetrics: [] },
    });
    rerender(
      <QueryClientProvider client={client}>
        <MemoryRouter>
          <AnalyzePage />
        </MemoryRouter>
      </QueryClientProvider>,
    );
    expect(invalidate).toHaveBeenCalledWith({ queryKey: ["quota"] });
  });

  it("invalidates ['quota'] on an error landing (incl. a 429 refusal)", () => {
    const client = new QueryClient();
    const invalidate = vi.spyOn(client, "invalidateQueries");

    streamState.mockReturnValue({
      ...initialState,
      phase: "error",
      error: "Rate limited — daily live-run quota reached. Try a replay.",
      errorStatus: 429,
    });
    renderPage(client);
    expect(invalidate).toHaveBeenCalledWith({ queryKey: ["quota"] });
  });
});

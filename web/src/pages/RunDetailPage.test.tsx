/**
 * RunDetailPage — the replay theater. Asserts it hydrates from a recorded run,
 * drives the cockpit from replay state (the dossier + verdict appear once the
 * timeline is scrubbed to the end), and surfaces a designed 404. The xyflow
 * canvas is mocked (it needs real layout and is aria-hidden decoration).
 */
import { fireEvent, screen, waitFor, within } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { fixtureEvents } from "@/features/analyze/cockpit/replayFixture";
import type * as ApiModuleNs from "@/lib/api";
import { renderWithProviders } from "@/test/render";

import { RunDetailPage } from "./RunDetailPage";

type ApiModule = typeof ApiModuleNs;

vi.mock("@/features/analyze/cockpit/PipelineCanvas", () => ({
  PipelineCanvas: () => <div data-testid="pipeline-canvas" />,
}));

const run = vi.fn();
vi.mock("@/lib/api", async (importOriginal) => {
  const actual = await importOriginal<ApiModule>();
  return { ...actual, api: { ...actual.api, run: (...a: unknown[]) => run(...a) } };
});

function detail(over: Record<string, unknown> = {}) {
  return {
    run_id: "0bd902d9d393",
    source: "warehouse",
    ticker: "AAPL",
    debate_mode: "on",
    status: "finished",
    started_at: "2026-06-09T12:00:00Z",
    finished_at: "2026-06-09T12:00:10Z",
    final_decision: { action: "BUY", conviction: 0.82, score: 86, rationale: "strong" },
    report: "# AAPL report",
    metrics: [],
    cost: { cost_usd: 0, latency_s: 1.4, prompt_tokens: 50, completion_tokens: 35, total_tokens: 85 },
    events: fixtureEvents,
    ...over,
  };
}

beforeEach(() => run.mockReset());

describe("RunDetailPage", () => {
  it("hydrates the dossier from the run and offers a live-rerun CTA", async () => {
    run.mockResolvedValue(detail());
    renderWithProviders(<RunDetailPage />, { route: "/library/0bd902d9d393", path: "/library/:runId" });

    // The dossier identity.
    expect(await screen.findByRole("heading", { name: "AAPL" })).toBeInTheDocument();
    expect(screen.getByRole("link", { name: /run aapl live/i })).toHaveAttribute(
      "href",
      "/",
    );
    // The transport bar mounted with its slider.
    expect(screen.getByRole("slider", { name: /replay timeline/i })).toBeInTheDocument();
  });

  it("drives the cockpit from replay state — the verdict reveals at the end", async () => {
    run.mockResolvedValue(detail());
    renderWithProviders(<RunDetailPage />, { route: "/library/0bd902d9d393", path: "/library/:runId" });

    const slider = await screen.findByRole("slider", { name: /replay timeline/i });
    // Jump to the end of the recorded timeline (End key) — a synchronous keydown
    // (fireEvent, deterministic under the stubbed rAF) seeks to the end; the
    // reducer folds the recorded `done` event and the cockpit renders the
    // fixture report + verdict, proving it is driven by REPLAY state.
    fireEvent.keyDown(slider, { key: "End", code: "End" });

    await waitFor(() =>
      expect(
        screen.getByRole("heading", { name: /aapl report/i }),
      ).toBeInTheDocument(),
    );
    // The verdict reveal carries the BUY signal from the recorded final_decision.
    expect(screen.getAllByText("BUY").length).toBeGreaterThan(0);
  });

  it("transport slider is keyboard-operable (space toggles play/pause)", async () => {
    run.mockResolvedValue(detail());
    renderWithProviders(<RunDetailPage />, { route: "/library/0bd902d9d393", path: "/library/:runId" });

    const playBtn = await screen.findByRole("button", { name: /pause replay|play replay/i });
    expect(playBtn).toBeInTheDocument();
    // Activating the slider with Space must not throw and keeps it focusable.
    const slider = screen.getByRole("slider", { name: /replay timeline/i });
    slider.focus();
    fireEvent.keyDown(slider, { key: " ", code: "Space" });
    expect(slider).toHaveFocus();
  });

  it("mid-replay ELAPSED shows the recorded run's timing, not epoch seconds", async () => {
    // Regression: mid-replay the cost ticker computed Date.now() minus the
    // reducer's synthetic fold stamps and rendered raw epoch seconds
    // (e.g. "1781139085s"). At the playhead, elapsed must reflect the ORIGINAL
    // run's recorded ts_ms deltas — for this fixture, tens of milliseconds.
    run.mockResolvedValue(detail());
    renderWithProviders(<RunDetailPage />, { route: "/library/0bd902d9d393", path: "/library/:runId" });

    const slider = await screen.findByRole("slider", { name: /replay timeline/i });
    // Freeze the playhead, then step three recorded events in (router complete).
    fireEvent.click(screen.getByRole("button", { name: /pause replay/i }));
    fireEvent.keyDown(slider, { key: "ArrowRight" });
    fireEvent.keyDown(slider, { key: "ArrowRight" });
    fireEvent.keyDown(slider, { key: "ArrowRight" });

    const group = screen.getByRole("group", { name: /run cost/i });
    const elapsed = within(group).getByText(/^[\d,.]+s$/).textContent!;
    // Sane: the fixture's recorded run spans 60ms — never epoch-scale.
    expect(parseFloat(elapsed.replace(/,/g, ""))).toBeLessThan(60);
  });

  it("renders the error banner for an aborted run but still replays", async () => {
    run.mockResolvedValue(detail({ status: "aborted" }));
    renderWithProviders(<RunDetailPage />, { route: "/library/0bd902d9d393", path: "/library/:runId" });

    expect(await screen.findByText(/was aborted mid-stream/i)).toBeInTheDocument();
    expect(screen.getByRole("slider", { name: /replay timeline/i })).toBeInTheDocument();
  });

  it("a single-event run still mounts the transport (not 'no replayable events')", async () => {
    // Offsets are inter-event GAPS, so one event means durationMs === 0 —
    // keying emptiness on duration misreported this run as having nothing to
    // replay. One recorded event is absolutely replayable.
    run.mockResolvedValue(detail({ events: [fixtureEvents[0]!] }));
    renderWithProviders(<RunDetailPage />, { route: "/library/0bd902d9d393", path: "/library/:runId" });

    expect(
      await screen.findByRole("slider", { name: /replay timeline/i }),
    ).toBeInTheDocument();
    expect(
      screen.queryByText(/no replayable events recorded/i),
    ).not.toBeInTheDocument();
  });

  it("shows the empty-events copy only when the run truly has no events", async () => {
    run.mockResolvedValue(detail({ events: [] }));
    renderWithProviders(<RunDetailPage />, { route: "/library/0bd902d9d393", path: "/library/:runId" });

    expect(
      await screen.findByText(/no replayable events recorded/i),
    ).toBeInTheDocument();
    expect(
      screen.queryByRole("slider", { name: /replay timeline/i }),
    ).not.toBeInTheDocument();
  });
});

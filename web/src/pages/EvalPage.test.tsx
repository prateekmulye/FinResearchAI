/**
 * EvalPage — the assembler. We mock the API and the lazy recharts-bearing
 * scatter (so the page test never pulls a chart lib), then assert the state
 * machine: runs list → verdict band, ?label= deep-link selection, the empty
 * state with the seed command, the load error, the 503 "warehouse offline"
 * state, and the always-present PROXY methodology cue.
 *
 * The scatter is mocked at its module path (the RunDetailPage pattern), so the
 * Suspense boundary still resolves but with a trivial child.
 */
import { fireEvent, screen, waitFor, within } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import type * as ApiModuleNs from "@/lib/api";
import { ApiError } from "@/lib/api";
import { renderWithProviders } from "@/test/render";

import { EvalPage } from "./EvalPage";

type ApiModule = typeof ApiModuleNs;

const evalResults = vi.fn();

vi.mock("@/lib/api", async (importOriginal) => {
  const actual = await importOriginal<ApiModule>();
  return {
    ...actual,
    api: { ...actual.api, evalResults: (...a: unknown[]) => evalResults(...a) },
  };
});

vi.mock("@/features/eval/CostQualityScatter", () => ({
  CostQualityScatter: () => <div data-testid="scatter-mock" />,
}));

function run(over: Record<string, unknown> = {}) {
  return {
    id: 1,
    label: "demo",
    created_at: "2026-06-09T12:00:00Z",
    summary: {
      n_tickers: 2,
      n_judged: 2,
      judge_prefers_on_rate: 0.75,
      judge_agreement_rate: 0.5,
      action_agreement_rate: 0.5,
      mean_score_delta_on_minus_off: 12.5,
      score_delta_stdev: 3.0,
      mean_cost_delta_on_minus_off: 0.024,
      mean_latency_delta_on_minus_off: 2.5,
      mean_token_delta_on_minus_off: 1200,
    },
    pairs: [
      {
        ticker: "AAPL",
        action_on: "BUY",
        action_off: "HOLD",
        actions_agree: false,
        score_on: 80,
        score_off: 55,
        score_delta: 25,
        cost_on: 0.06,
        cost_off: 0.02,
        latency_on: 4,
        latency_off: 1.5,
        tokens_on: 150,
        tokens_off: 60,
        judge_preferred: "on",
        judge_agreement: false,
        judge_confidence: 0.7,
      },
    ],
    ...over,
  };
}

beforeEach(() => {
  evalResults.mockReset();
});

describe("EvalPage", () => {
  it("renders the verdict band hero rate and the methodology cue from the newest run", async () => {
    evalResults.mockResolvedValue({ results: [run()] });
    renderWithProviders(<EvalPage />, { route: "/eval", path: "/eval" });

    // Hero judge-prefers-debate rate.
    expect(await screen.findByText("75%")).toBeInTheDocument();
    // All four delta tiles render, token Δ included, with the stdev annotation
    // on the score tile.
    expect(screen.getByText("Mean token Δ")).toBeInTheDocument();
    expect(screen.getByText("+1,200")).toBeInTheDocument();
    expect(screen.getByText(/±3\.0 σ/)).toBeInTheDocument();
    // The PROXY honesty cue is always present.
    expect(
      screen.getByText(/judge-preference proxy — not realized p&l/i),
    ).toBeInTheDocument();
    // The A/B legend makes the on/off semantic legible (scoped to the legend
    // list — "judge prefers debate" also appears as the hero tile label).
    const legend = screen.getByRole("list", {
      name: /legend: scatter point color/i,
    });
    expect(
      within(legend).getByText(/judge prefers debate/i),
    ).toBeInTheDocument();
    expect(within(legend).getByText(/judge prefers baseline/i)).toBeInTheDocument();
  });

  it("selects the run named by ?label= over the newest", async () => {
    evalResults.mockResolvedValue({
      results: [
        run({ id: 2, label: "newest", summary: { ...run().summary, judge_prefers_on_rate: 0.9 } }),
        run({ id: 1, label: "older", summary: { ...run().summary, judge_prefers_on_rate: 0.25 } }),
      ],
    });
    renderWithProviders(<EvalPage />, {
      route: "/eval?label=older",
      path: "/eval",
    });
    // The older run's rate (25%), not the newest (90%).
    expect(await screen.findByText("25%")).toBeInTheDocument();
    expect(screen.queryByText("90%")).not.toBeInTheDocument();
  });

  it("falls back to the newest run when ?label= doesn't match", async () => {
    evalResults.mockResolvedValue({
      results: [run({ label: "real", summary: { ...run().summary, judge_prefers_on_rate: 0.6 } })],
    });
    renderWithProviders(<EvalPage />, {
      route: "/eval?label=ghost",
      path: "/eval",
    });
    expect(await screen.findByText("60%")).toBeInTheDocument();
  });

  it("shows the seed-command empty state when there are no runs", async () => {
    evalResults.mockResolvedValue({ results: [] });
    renderWithProviders(<EvalPage />, { route: "/eval", path: "/eval" });
    expect(await screen.findByText(/run the ablation to see it here/i)).toBeInTheDocument();
    expect(screen.getByText(/src\.eval\.run/)).toBeInTheDocument();
  });

  it("shows the load-error state with a retry", async () => {
    evalResults.mockRejectedValue(new Error("network down"));
    renderWithProviders(<EvalPage />, { route: "/eval", path: "/eval" });
    expect(
      await screen.findByText(/the eval index didn’t respond/i),
    ).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /retry/i })).toBeInTheDocument();
  });

  it("distinguishes a 503 (warehouse offline) from a generic error", async () => {
    evalResults.mockRejectedValue(new ApiError("GET -> 503", 503));
    renderWithProviders(<EvalPage />, { route: "/eval", path: "/eval" });
    expect(
      await screen.findByText(/the results warehouse is disabled/i),
    ).toBeInTheDocument();
  });

  it("null-safes the hero when nothing was judged (n_judged=0)", async () => {
    evalResults.mockResolvedValue({
      results: [
        run({
          summary: {
            ...run().summary,
            n_judged: 0,
            judge_prefers_on_rate: 0.0,
          },
        }),
      ],
    });
    renderWithProviders(<EvalPage />, { route: "/eval", path: "/eval" });
    // Hero shows the honest "n/a", not a fake 0%.
    expect(await screen.findByText("n/a")).toBeInTheDocument();
    expect(
      screen.getByText(/no verdicts were refereed in this run/i),
    ).toBeInTheDocument();
  });

  it("expands the methodology body on click (onion-peel disclosure)", async () => {
    evalResults.mockResolvedValue({ results: [run()] });
    renderWithProviders(<EvalPage />, { route: "/eval", path: "/eval" });
    const toggle = await screen.findByRole("button", {
      name: /what this measures/i,
    });
    expect(screen.queryByText(/runs no backtest/i)).not.toBeInTheDocument();
    fireEvent.click(toggle);
    await waitFor(() =>
      expect(screen.getByText(/runs no backtest/i)).toBeInTheDocument(),
    );
  });
});

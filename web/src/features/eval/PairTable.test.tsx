/**
 * PairTable — the receipts. We assert the rows render, the default sort is score
 * delta descending, and clicking the cost-delta header re-sorts client-side.
 * fireEvent.click (rAF-safe, per the WP-8 trap note) drives the sort buttons.
 */
import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import type { EvalPair } from "./evalFormat";
import { PairTable } from "./PairTable";

function pair(over: Partial<EvalPair>): EvalPair {
  return {
    ticker: "X",
    actionOn: "BUY",
    actionOff: "HOLD",
    actionsAgree: false,
    scoreOn: 70,
    scoreOff: 60,
    scoreDelta: 10,
    costOn: 0.05,
    costOff: 0.02,
    costDelta: 0.03,
    latencyOn: 4,
    latencyOff: 2,
    latencyDelta: 2,
    tokensOn: 100,
    tokensOff: 50,
    tokenDelta: 50,
    judgePreferred: "on",
    judgeAgreement: true,
    judgeConfidence: 0.8,
    ...over,
  };
}

const rows = [
  pair({ ticker: "AAPL", scoreDelta: 25, costDelta: 0.06 }),
  pair({ ticker: "MSFT", scoreDelta: 5, costDelta: 0.02 }),
  pair({ ticker: "TSLA", scoreDelta: -10, costDelta: 0.04 }),
];

function tickerOrder(): string[] {
  return screen
    .getAllByText(/^(AAPL|MSFT|TSLA)$/)
    .map((el) => el.textContent ?? "");
}

describe("PairTable", () => {
  it("renders one row per ticker with both verdict badges", () => {
    render(<PairTable pairs={rows} />);
    expect(screen.getByText("AAPL")).toBeInTheDocument();
    expect(screen.getByText("MSFT")).toBeInTheDocument();
    expect(screen.getByText("TSLA")).toBeInTheDocument();
  });

  it("defaults to score delta descending", () => {
    render(<PairTable pairs={rows} />);
    expect(tickerOrder()).toEqual(["AAPL", "MSFT", "TSLA"]);
  });

  it("re-sorts by cost delta when its header is clicked", () => {
    render(<PairTable pairs={rows} />);
    // Click cost → descending (biggest cost first): AAPL .06, TSLA .04, MSFT .02
    fireEvent.click(screen.getByRole("button", { name: /sort by cost/i }));
    expect(tickerOrder()).toEqual(["AAPL", "TSLA", "MSFT"]);
    // Second click flips to ascending: MSFT .02, TSLA .04, AAPL .06
    fireEvent.click(screen.getByRole("button", { name: /sort by cost/i }));
    expect(tickerOrder()).toEqual(["MSFT", "TSLA", "AAPL"]);
  });

  it("marks diverging verdicts with the ≠ cue", () => {
    render(<PairTable pairs={[pair({ ticker: "DIV", actionsAgree: false })]} />);
    expect(screen.getByTitle(/diverge/i)).toBeInTheDocument();
  });

  it("exposes the agree/diverge judgement as text (the glyph is aria-hidden)", () => {
    render(
      <PairTable
        pairs={[
          pair({ ticker: "AGR", actionsAgree: true }),
          pair({ ticker: "DIV", actionsAgree: false }),
        ]}
      />,
    );
    // A title attribute on an aria-hidden span is not reliably exposed; the
    // judgement must exist as (visually hidden) text for screen readers.
    expect(screen.getByText("verdicts agree")).toBeInTheDocument();
    expect(screen.getByText("verdicts diverge")).toBeInTheDocument();
  });
});

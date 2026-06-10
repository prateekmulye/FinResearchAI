/**
 * pairSort — the receipts-table sort. Verifies the two-key toggle behaviour and
 * the null-sinks-to-bottom rule (a ticker with missing metrics must never sort
 * as the best or worst).
 */
import { describe, expect, it } from "vitest";

import type { EvalPair } from "./evalFormat";
import { nextSort, sortPairs } from "./pairSort";

function pair(over: Partial<EvalPair>): EvalPair {
  return {
    ticker: "X",
    actionOn: "BUY",
    actionOff: "BUY",
    actionsAgree: true,
    scoreOn: null,
    scoreOff: null,
    scoreDelta: null,
    costOn: null,
    costOff: null,
    costDelta: null,
    latencyOn: null,
    latencyOff: null,
    latencyDelta: null,
    tokensOn: null,
    tokensOff: null,
    tokenDelta: null,
    judgePreferred: null,
    judgeAgreement: null,
    judgeConfidence: null,
    ...over,
  };
}

describe("nextSort", () => {
  it("toggles direction when the key is already active", () => {
    expect(nextSort({ key: "scoreDelta", dir: "desc" }, "scoreDelta")).toEqual({
      key: "scoreDelta",
      dir: "asc",
    });
    expect(nextSort({ key: "scoreDelta", dir: "asc" }, "scoreDelta")).toEqual({
      key: "scoreDelta",
      dir: "desc",
    });
  });

  it("starts numeric keys descending (biggest impact first), ticker ascending", () => {
    expect(nextSort({ key: "ticker", dir: "asc" }, "costDelta")).toEqual({
      key: "costDelta",
      dir: "desc",
    });
    expect(nextSort({ key: "scoreDelta", dir: "desc" }, "ticker")).toEqual({
      key: "ticker",
      dir: "asc",
    });
  });
});

describe("sortPairs", () => {
  const rows = [
    pair({ ticker: "AAPL", scoreDelta: 25, costDelta: 0.04 }),
    pair({ ticker: "MSFT", scoreDelta: 5, costDelta: 0.02 }),
    pair({ ticker: "TSLA", scoreDelta: -10, costDelta: 0.06 }),
  ];

  it("sorts by score delta descending", () => {
    const out = sortPairs(rows, { key: "scoreDelta", dir: "desc" });
    expect(out.map((r) => r.ticker)).toEqual(["AAPL", "MSFT", "TSLA"]);
  });

  it("sorts by cost delta ascending", () => {
    const out = sortPairs(rows, { key: "costDelta", dir: "asc" });
    expect(out.map((r) => r.ticker)).toEqual(["MSFT", "AAPL", "TSLA"]);
  });

  it("sorts by ticker alphabetically", () => {
    const out = sortPairs(rows, { key: "ticker", dir: "asc" });
    expect(out.map((r) => r.ticker)).toEqual(["AAPL", "MSFT", "TSLA"]);
  });

  it("sinks null deltas to the bottom regardless of direction", () => {
    const withNull = [
      pair({ ticker: "GOOD", scoreDelta: 10 }),
      pair({ ticker: "NULL", scoreDelta: null }),
      pair({ ticker: "BAD", scoreDelta: -10 }),
    ];
    expect(
      sortPairs(withNull, { key: "scoreDelta", dir: "desc" }).map((r) => r.ticker),
    ).toEqual(["GOOD", "BAD", "NULL"]);
    expect(
      sortPairs(withNull, { key: "scoreDelta", dir: "asc" }).map((r) => r.ticker),
    ).toEqual(["BAD", "GOOD", "NULL"]);
  });

  it("does not mutate the input array", () => {
    const input = [...rows];
    sortPairs(input, { key: "scoreDelta", dir: "asc" });
    expect(input.map((r) => r.ticker)).toEqual(["AAPL", "MSFT", "TSLA"]);
  });
});

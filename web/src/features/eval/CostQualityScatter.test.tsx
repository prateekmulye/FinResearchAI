/**
 * CostQualityScatter — recharts is mocked at the module boundary (jsdom has no
 * SVG layout engine, exactly like the lightweight-charts mock in WP-9). We
 * assert the DATA MAPPING the component owns: which pairs become points, how
 * many are dropped for missing deltas, the point coordinates (x=cost, y=score),
 * and the per-point judge color — not recharts' own rendering.
 */
import { render, screen } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import type { EvalPair } from "./evalFormat";

/** Capture the data recharts' <Scatter> receives, and the <Cell> fills. */
const scatterData = vi.fn();
const cellFills: string[] = [];

vi.mock("recharts", () => {
  const Pass = ({ children }: { children?: React.ReactNode }) => <div>{children}</div>;
  return {
    ResponsiveContainer: Pass,
    ScatterChart: Pass,
    Scatter: ({
      data,
      children,
    }: {
      data: unknown;
      children?: React.ReactNode;
    }) => {
      scatterData(data);
      return <div data-testid="scatter">{children}</div>;
    },
    Cell: ({ fill }: { fill: string }) => {
      cellFills.push(fill);
      return <div data-testid="cell" data-fill={fill} />;
    },
    XAxis: () => null,
    YAxis: () => null,
    CartesianGrid: () => null,
    Tooltip: () => null,
    ReferenceArea: () => null,
    ReferenceLine: () => null,
  };
});

// Import AFTER the mock is registered (the WP-9 chart-test recipe).
const { CostQualityScatter } = await import("./CostQualityScatter");

function pair(over: Partial<EvalPair>): EvalPair {
  return {
    ticker: "X",
    actionOn: "BUY",
    actionOff: "BUY",
    actionsAgree: true,
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

beforeEach(() => {
  scatterData.mockReset();
  cellFills.length = 0;
});

describe("CostQualityScatter", () => {
  it("maps each fully-metric'd pair to a point (x=cost Δ, y=score Δ)", () => {
    render(
      <CostQualityScatter
        pairs={[
          pair({ ticker: "AAPL", costDelta: 0.04, scoreDelta: 25 }),
          pair({ ticker: "MSFT", costDelta: 0.02, scoreDelta: 5 }),
        ]}
      />,
    );
    const data = scatterData.mock.calls[0]![0] as Array<{
      ticker: string;
      x: number;
      y: number;
    }>;
    expect(data).toHaveLength(2);
    expect(data[0]).toMatchObject({ ticker: "AAPL", x: 0.04, y: 25 });
    expect(data[1]).toMatchObject({ ticker: "MSFT", x: 0.02, y: 5 });
  });

  it("drops pairs missing a cost or score delta and footnotes the count", () => {
    render(
      <CostQualityScatter
        pairs={[
          pair({ ticker: "OK", costDelta: 0.01, scoreDelta: 3 }),
          pair({ ticker: "NOCOST", costDelta: null, scoreDelta: 3 }),
          pair({ ticker: "NOSCORE", costDelta: 0.01, scoreDelta: null }),
        ]}
      />,
    );
    const data = scatterData.mock.calls[0]![0] as unknown[];
    expect(data).toHaveLength(1);
    expect(screen.getByText(/2 tickers not plotted/i)).toBeInTheDocument();
  });

  it("colors points by judge preference (on=bull, off=bear, tie=hold, null=dim)", () => {
    render(
      <CostQualityScatter
        pairs={[
          pair({ ticker: "ON", judgePreferred: "on" }),
          pair({ ticker: "OFF", judgePreferred: "off" }),
          pair({ ticker: "TIE", judgePreferred: "tie" }),
          pair({ ticker: "NONE", judgePreferred: null }),
        ]}
      />,
    );
    expect(cellFills).toEqual([
      "var(--color-bull)",
      "var(--color-bear)",
      "var(--color-hold)",
      "var(--color-fg-subtle)",
    ]);
  });

  it("shows the no-data state when nothing is plottable", () => {
    render(
      <CostQualityScatter
        pairs={[pair({ costDelta: null, scoreDelta: null })]}
      />,
    );
    expect(screen.getByText(/no plottable tickers/i)).toBeInTheDocument();
    expect(scatterData).not.toHaveBeenCalled();
  });
});

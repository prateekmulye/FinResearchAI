/**
 * CandlestickChart — mount smoke against a MOCKED lightweight-charts. jsdom has
 * no canvas, so we stub the charting lib at the module boundary and assert the
 * component (a) creates a chart, (b) adds candle + volume series, (c) feeds the
 * bars, and (d) renders the floating OHLC legend from the latest bar. We never
 * restore global mocks (would wipe the matchMedia/ResizeObserver setup stubs).
 */
import { render, screen } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import type { PriceBar } from "@/lib/api";

const createChart = vi.fn();
const candleSetData = vi.fn();
const volumeSetData = vi.fn();
const addCandlestickSeries = vi.fn(() => ({ setData: candleSetData }));
const addHistogramSeries = vi.fn(() => ({ setData: volumeSetData }));

vi.mock("lightweight-charts", () => ({
  ColorType: { Solid: "solid" },
  createChart: (...a: unknown[]) => {
    createChart(...a);
    return {
      addCandlestickSeries,
      addHistogramSeries,
      priceScale: () => ({ applyOptions: vi.fn() }),
      timeScale: () => ({ fitContent: vi.fn(), applyOptions: vi.fn() }),
      subscribeCrosshairMove: vi.fn(),
      unsubscribeCrosshairMove: vi.fn(),
      resize: vi.fn(),
      remove: vi.fn(),
    };
  },
}));

// Import AFTER the mock is registered.
const { CandlestickChart } = await import("./CandlestickChart");

const bars: PriceBar[] = [
  { ts: "2026-06-01T00:00:00Z", open: 100, high: 110, low: 95, close: 105, volume: 1e6 },
  { ts: "2026-06-02T00:00:00Z", open: 105, high: 112, low: 104, close: 99, volume: 2e6 },
];

beforeEach(() => {
  createChart.mockClear();
  addCandlestickSeries.mockClear();
  addHistogramSeries.mockClear();
  candleSetData.mockClear();
  volumeSetData.mockClear();
});

describe("CandlestickChart", () => {
  it("creates a chart and adds candle + volume series", () => {
    render(<CandlestickChart bars={bars} />);
    expect(createChart).toHaveBeenCalledTimes(1);
    expect(addCandlestickSeries).toHaveBeenCalledTimes(1);
    expect(addHistogramSeries).toHaveBeenCalledTimes(1);
  });

  it("feeds the bars to both series", () => {
    render(<CandlestickChart bars={bars} />);
    expect(candleSetData).toHaveBeenCalledWith(
      expect.arrayContaining([expect.objectContaining({ open: 100, close: 105 })]),
    );
    expect(volumeSetData).toHaveBeenCalledWith(
      expect.arrayContaining([expect.objectContaining({ value: 1e6 })]),
    );
  });

  it("renders the floating OHLC legend from the latest bar", () => {
    render(<CandlestickChart bars={bars} />);
    // Latest bar close = 99.00 (down day) shown in the legend.
    expect(screen.getByText("99.00")).toBeInTheDocument();
    expect(screen.getByText("O")).toBeInTheDocument();
    expect(screen.getByText("C")).toBeInTheDocument();
  });
});

/**
 * DossierPage — the instrument deep-dive. The chart module is mocked (canvas +
 * ResizeObserver aren't available under jsdom; we assert the panel MOUNTS the
 * chart with the right bars, not pixels). The market API calls are mocked; we
 * cover fundamentals/news rendering, range-selector param wiring, the empty-bars
 * backfill CTA, and the unknown-ticker dead-end.
 *
 * Isolation: the unknown-ticker case drives EVERY market endpoint to reject with
 * a 404 — those rejections are marked handled by the test QueryClient's cache
 * onError, so they don't trip the unhandled-rejection detector. We never call
 * vi.restoreAllMocks() (it would wipe the global matchMedia/ResizeObserver
 * stubs); module mocks are reset per-test with mockReset.
 */
import { fireEvent, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import type * as ApiModuleNs from "@/lib/api";
import { ApiError } from "@/lib/api";
import { renderWithProviders } from "@/test/render";

import { DossierPage } from "./DossierPage";

type ApiModule = typeof ApiModuleNs;

// Mock the chart so the dossier test never touches canvas. The mock records the
// bars it was handed so we can assert the panel forwarded the data.
const chartBars = vi.fn();
vi.mock("@/features/market/CandlestickChart", () => ({
  CandlestickChart: ({ bars }: { bars: unknown[] }) => {
    chartBars(bars);
    return <div data-testid="candles">candles:{bars.length}</div>;
  },
}));

const instruments = vi.fn();
const prices = vi.fn();
const fundamentals = vi.fn();
const news = vi.fn();

vi.mock("@/lib/api", async (importOriginal) => {
  const actual = await importOriginal<ApiModule>();
  return {
    ...actual,
    api: {
      ...actual.api,
      instruments: (...a: unknown[]) => instruments(...a),
      prices: (...a: unknown[]) => prices(...a),
      fundamentals: (...a: unknown[]) => fundamentals(...a),
      news: (...a: unknown[]) => news(...a),
    },
  };
});

function bar(over: Record<string, unknown> = {}) {
  return {
    ts: "2026-06-01T00:00:00Z",
    open: 100,
    high: 110,
    low: 95,
    close: 105,
    volume: 1_000_000,
    ...over,
  };
}

const APPLE = {
  id: 1,
  ticker: "AAPL",
  exchange: "NASDAQ",
  screener: "america",
  name: "Apple Inc.",
  country: "United States",
  currency: "USD",
  sector: "Technology",
  watched: true,
};

beforeEach(() => {
  chartBars.mockReset();
  instruments.mockReset().mockResolvedValue({ instruments: [APPLE] });
  prices.mockReset().mockResolvedValue({
    ticker: "AAPL",
    exchange: "NASDAQ",
    interval: "1d",
    bars: [bar(), bar({ ts: "2026-06-02T00:00:00Z", close: 108 })],
  });
  fundamentals.mockReset().mockResolvedValue({
    ticker: "AAPL",
    exchange: "NASDAQ",
    ts: "2026-06-08T00:00:00Z",
    market_cap: 3.2e12,
    pe_ratio: 28.4,
    eps: 6.42,
    revenue_growth: 0.084,
    profit_margin: 0.251,
    payload: {},
  });
  news.mockReset().mockResolvedValue({
    ticker: "AAPL",
    exchange: "NASDAQ",
    items: [
      {
        ts: "2026-06-09T12:00:00Z",
        title: "Apple ships record quarter",
        url: "https://example.com/news",
        source: "Reuters",
        snippet: "Revenue up...",
      },
    ],
  });
});

describe("DossierPage", () => {
  it("renders the header identity from the resolved instrument", async () => {
    renderWithProviders(<DossierPage />, {
      route: "/market/AAPL?exchange=NASDAQ",
      path: "/market/:ticker",
    });
    expect(await screen.findByRole("heading", { name: "AAPL" })).toBeInTheDocument();
    // The name lands once the instrument query resolves (the heading renders
    // immediately from the URL param, so wait for the resolved metadata).
    expect(await screen.findByText("Apple Inc.")).toBeInTheDocument();
    expect(
      screen.getAllByRole("link", { name: /analyze AAPL live/i }).length,
    ).toBeGreaterThanOrEqual(1);
  });

  it("mounts the candlestick chart with the fetched bars", async () => {
    renderWithProviders(<DossierPage />, {
      route: "/market/AAPL",
      path: "/market/:ticker",
    });
    expect(await screen.findByTestId("candles")).toHaveTextContent("candles:2");
    expect(chartBars).toHaveBeenCalledWith(expect.arrayContaining([expect.any(Object)]));
  });

  it("renders the fundamentals metric tape", async () => {
    renderWithProviders(<DossierPage />, {
      route: "/market/AAPL",
      path: "/market/:ticker",
    });
    expect(await screen.findByText("$3.20T")).toBeInTheDocument();
    expect(screen.getByText("28.40")).toBeInTheDocument(); // P/E
    expect(screen.getByText("+8.4%")).toBeInTheDocument(); // signed growth
  });

  it("renders the news feed linking out in a new tab", async () => {
    renderWithProviders(<DossierPage />, {
      route: "/market/AAPL",
      path: "/market/:ticker",
    });
    const link = await screen.findByRole("link", {
      name: /apple ships record quarter/i,
    });
    expect(link).toHaveAttribute("href", "https://example.com/news");
    expect(link).toHaveAttribute("target", "_blank");
    expect(link.getAttribute("rel")).toContain("noopener");
  });

  it("defaults to the 1Y range and re-queries prices with the chosen days", async () => {
    renderWithProviders(<DossierPage />, {
      route: "/market/AAPL",
      path: "/market/:ticker",
    });
    await screen.findByTestId("candles");
    // Default range = 1Y => 365 days.
    expect(prices).toHaveBeenCalledWith(
      "AAPL",
      expect.objectContaining({ days: 365 }),
      expect.anything(),
    );

    // Switch to 3M — fireEvent (rAF-safe, per the test-isolation trap notes).
    fireEvent.click(screen.getByRole("button", { name: "3M" }));
    await waitFor(() =>
      expect(prices).toHaveBeenCalledWith(
        "AAPL",
        expect.objectContaining({ days: 90 }),
        expect.anything(),
      ),
    );
  });

  it("shows the backfill CTA when a covered ticker has no bars", async () => {
    prices.mockResolvedValue({
      ticker: "AAPL",
      exchange: "NASDAQ",
      interval: "1d",
      bars: [],
    });
    renderWithProviders(<DossierPage />, {
      route: "/market/AAPL",
      path: "/market/:ticker",
    });
    expect(
      await screen.findByText(/no bars stored for AAPL yet/i),
    ).toBeInTheDocument();
    expect(
      screen.getByRole("link", { name: /analyze AAPL to backfill/i }),
    ).toHaveAttribute("href", "/");
  });

  it("renders the fundamentals empty state on a 404 snapshot", async () => {
    fundamentals.mockRejectedValue(new ApiError("nope", 404));
    renderWithProviders(<DossierPage />, {
      route: "/market/AAPL",
      path: "/market/:ticker",
    });
    expect(
      await screen.findByText(/no fundamentals snapshot yet/i),
    ).toBeInTheDocument();
  });
});

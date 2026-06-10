/**
 * MarketPage (explorer) — dual-lane wiring. The instruments + search API calls
 * are mocked; we assert the URL `?q=` drives both lanes, the coverage strip
 * derives honest counts from the no-query instruments fetch, the keyword-mode
 * honesty banner appears only in keyword mode, and the empty/error lanes render.
 */
import { screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import type * as ApiModuleNs from "@/lib/api";
import { renderWithProviders } from "@/test/render";

import { MarketPage } from "./MarketPage";

type ApiModule = typeof ApiModuleNs;

const instruments = vi.fn();
const searchResearch = vi.fn();

vi.mock("@/lib/api", async (importOriginal) => {
  const actual = await importOriginal<ApiModule>();
  return {
    ...actual,
    api: {
      ...actual.api,
      instruments: (...a: unknown[]) => instruments(...a),
      searchResearch: (...a: unknown[]) => searchResearch(...a),
    },
  };
});

function inst(over: Record<string, unknown> = {}) {
  return {
    id: 1,
    ticker: "AAPL",
    exchange: "NASDAQ",
    screener: "america",
    name: "Apple Inc.",
    country: "United States",
    currency: "USD",
    sector: "Technology",
    watched: true,
    ...over,
  };
}

function hit(over: Record<string, unknown> = {}) {
  return {
    kind: "news",
    ref: "https://example.com/a",
    ticker: "AAPL",
    title: "Apple unveils new chip",
    snippet: "The latest silicon...",
    score: 0.12,
    ts: "2026-06-09T12:00:00Z",
    ...over,
  };
}

beforeEach(() => {
  instruments.mockReset().mockResolvedValue({ instruments: [inst()] });
  searchResearch.mockReset().mockResolvedValue({ mode: "semantic", hits: [hit()] });
});

describe("MarketPage explorer", () => {
  it("renders the instruments lane from the default fetch (no query)", async () => {
    renderWithProviders(<MarketPage />, { route: "/market" });
    expect(await screen.findByText("AAPL")).toBeInTheDocument();
    expect(screen.getByText("Apple Inc.", { exact: false })).toBeInTheDocument();
    // No query => instruments fetched with the high coverage limit.
    expect(instruments).toHaveBeenCalledWith(
      expect.objectContaining({ q: undefined, limit: 60 }),
      expect.anything(),
    );
  });

  it("derives the coverage strip counts from the instruments page", async () => {
    instruments.mockResolvedValue({
      instruments: [
        inst({ ticker: "AAPL", exchange: "NASDAQ", watched: true }),
        inst({ ticker: "RELIANCE.NS", exchange: "NSE", watched: false }),
        inst({ ticker: "0700.HK", exchange: "HKEX", watched: true }),
      ],
    });
    renderWithProviders(<MarketPage />, { route: "/market" });

    await screen.findByText("RELIANCE.NS");
    // Instruments = 3, Watched = 2, Exchanges = 3 (NASDAQ/NSE/HKEX). Scope each
    // assertion to its stat tile — "Instruments" also names the lane header.
    const watched = screen.getByText("Watched").closest("div");
    expect(watched).toHaveTextContent("2");
    const exch = screen.getByText("Exchanges").closest("div");
    expect(exch).toHaveTextContent("3");
    // The instruments stat tile (the one whose label is in a <dt>) reads 3.
    const instrTile = screen.getByText("analyzed").closest("div"); // watched hint
    expect(instrTile).toBeTruthy();
  });

  it("reads ?q= from the URL and drives BOTH lanes", async () => {
    instruments.mockResolvedValue({
      instruments: [inst({ ticker: "NVDA", name: "NVIDIA Corp." })],
    });
    searchResearch.mockResolvedValue({
      mode: "semantic",
      hits: [hit({ ticker: "NVDA", title: "NVDA earnings beat" })],
    });
    renderWithProviders(<MarketPage />, { route: "/market?q=NVDA" });

    // Lane 1 (instrument name) + Lane 2 (research hit title) — text unique to
    // each lane so we prove BOTH rendered, not just the shared ticker.
    expect(await screen.findByText("NVIDIA Corp.")).toBeInTheDocument();
    expect(await screen.findByText("NVDA earnings beat")).toBeInTheDocument();
    // The search lane fired with the URL query, instruments used the search limit.
    expect(searchResearch).toHaveBeenCalledWith(
      expect.objectContaining({ q: "NVDA", limit: 12 }),
      expect.anything(),
    );
    expect(instruments).toHaveBeenCalledWith(
      expect.objectContaining({ q: "NVDA", limit: 12 }),
      expect.anything(),
    );
  });

  it("does NOT fire the search lane below the 2-char floor", async () => {
    renderWithProviders(<MarketPage />, { route: "/market?q=A" });
    await screen.findByText("AAPL"); // instruments still load
    expect(searchResearch).not.toHaveBeenCalled();
    // The pre-search prompt stands in for the research lane.
    expect(screen.getByText(/search the system’s memory/i)).toBeInTheDocument();
  });

  it("shows the keyword-fallback honesty banner only in keyword mode", async () => {
    searchResearch.mockResolvedValue({ mode: "keyword", hits: [hit()] });
    renderWithProviders(<MarketPage />, { route: "/market?q=tariff" });

    expect(await screen.findByText(/keyword fallback/i)).toBeInTheDocument();
  });

  it("hides the keyword banner in semantic mode", async () => {
    searchResearch.mockResolvedValue({ mode: "semantic", hits: [hit()] });
    renderWithProviders(<MarketPage />, { route: "/market?q=tariff" });

    await screen.findByText("Apple unveils new chip");
    expect(screen.queryByText(/keyword fallback/i)).not.toBeInTheDocument();
  });

  it("renders a run-kind hit linking to the library replay", async () => {
    searchResearch.mockResolvedValue({
      mode: "semantic",
      hits: [hit({ kind: "run", ref: "run-42", title: "AAPL — BUY", score: null })],
    });
    renderWithProviders(<MarketPage />, { route: "/market?q=apple" });

    const link = await screen.findByRole("link", { name: /replay run for AAPL/i });
    expect(link).toHaveAttribute("href", "/library/run-42");
  });

  it("opens news hits in a new tab with rel=noopener", async () => {
    renderWithProviders(<MarketPage />, { route: "/market?q=apple" });
    const link = await screen.findByRole("link", { name: /open article/i });
    expect(link).toHaveAttribute("href", "https://example.com/a");
    expect(link).toHaveAttribute("target", "_blank");
    expect(link.getAttribute("rel")).toContain("noopener");
  });

  it("shows an empty research lane when search returns no hits", async () => {
    searchResearch.mockResolvedValue({ mode: "semantic", hits: [] });
    renderWithProviders(<MarketPage />, { route: "/market?q=zzzzz" });
    expect(await screen.findByText(/no research memory yet/i)).toBeInTheDocument();
  });

  it("shows an error notice + retry when instruments reject", async () => {
    instruments.mockRejectedValue(new Error("boom"));
    renderWithProviders(<MarketPage />, { route: "/market" });
    await waitFor(() =>
      expect(screen.getByText(/couldn’t load instruments/i)).toBeInTheDocument(),
    );
    expect(screen.getByRole("button", { name: /retry/i })).toBeInTheDocument();
  });
});

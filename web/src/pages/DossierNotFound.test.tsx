/**
 * DossierPage — unknown-ticker dead-end, ISOLATED in its own file.
 *
 * This case drives EVERY market endpoint (prices/fundamentals/news) to reject
 * with a 404 AND the instrument lookup to resolve to nothing. Per the WP-8
 * test-isolation trap, expected-rejection tests live apart so their rejection
 * timing can't bleed into a happy-path test in the same module. The test
 * QueryClient's cache onError marks these rejections handled, so they don't trip
 * the unhandled-rejection detector — the rendered dead-end is asserted normally.
 */
import { screen } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import type * as ApiModuleNs from "@/lib/api";
import { ApiError } from "@/lib/api";
import { renderWithProviders } from "@/test/render";

import { DossierPage } from "./DossierPage";

type ApiModule = typeof ApiModuleNs;

vi.mock("@/features/market/CandlestickChart", () => ({
  CandlestickChart: () => <div data-testid="candles" />,
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

beforeEach(() => {
  const notFound = () => Promise.reject(new ApiError("unknown", 404));
  instruments.mockReset().mockResolvedValue({ instruments: [] });
  prices.mockReset().mockImplementation(notFound);
  fundamentals.mockReset().mockImplementation(notFound);
  news.mockReset().mockImplementation(notFound);
});

describe("DossierPage — unknown ticker", () => {
  it("shows the designed dead-end when nothing resolves", async () => {
    renderWithProviders(<DossierPage />, {
      route: "/market/ZZZZ",
      path: "/market/:ticker",
    });
    expect(
      await screen.findByText(/ZZZZ isn’t in coverage/i),
    ).toBeInTheDocument();
    // Both the header CTA and the dead-end CTA deep-link to the analyze page.
    const ctas = screen.getAllByRole("link", { name: /analyze ZZZZ live/i });
    expect(ctas.length).toBeGreaterThanOrEqual(1);
    ctas.forEach((cta) => expect(cta).toHaveAttribute("href", "/"));
  });
});

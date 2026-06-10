/**
 * RunRail — the run selector cards are plain <Link>s, so the one accessibility
 * contract worth pinning is WCAG 2.4.7: a keyboard user tabbing onto a card
 * must get a visible focus ring. The regression we guard against is
 * `focus-visible:outline-none` (which kills the ring) sneaking back in without
 * the explicit accent-ring restore classes.
 */
import { screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it } from "vitest";

import type { EvalResult } from "@/lib/api";
import { renderWithProviders } from "@/test/render";

import { RunRail } from "./RunRail";

const runs: EvalResult[] = [
  {
    id: 2,
    label: "demo",
    created_at: "2026-06-09T12:00:00Z",
    summary: { n_tickers: 3 },
    pairs: [],
  },
  {
    id: 1,
    label: "baseline",
    created_at: "2026-06-08T12:00:00Z",
    summary: { n_tickers: 5 },
    pairs: [],
  },
];

describe("RunRail", () => {
  it("renders one deep-linkable card per run with the active one marked", () => {
    renderWithProviders(<RunRail runs={runs} activeLabel="demo" />);
    const links = screen.getAllByRole("link");
    expect(links).toHaveLength(2);
    expect(links[0]).toHaveAttribute("aria-current", "true");
    expect(links[1]).not.toHaveAttribute("aria-current");
  });

  it("keeps a visible focus ring on a tabbed card (WCAG 2.4.7)", async () => {
    const user = userEvent.setup();
    renderWithProviders(<RunRail runs={runs} activeLabel="demo" />);

    await user.tab();
    const card = screen.getByRole("link", { name: /demo/ });
    expect(card).toHaveFocus();

    // The ring must be restored explicitly, never suppressed without a
    // replacement: assert the accent outline classes are present and the
    // ring-killer is absent.
    expect(card.className).toContain("focus-visible:outline-2");
    expect(card.className).toContain("focus-visible:outline-offset-2");
    expect(card.className).toContain(
      "focus-visible:outline-[var(--color-accent)]",
    );
    expect(card.className).not.toContain("focus-visible:outline-none");
  });
});

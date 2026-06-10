/**
 * QuotaBlocked is the designed state for an exhausted live-run quota: it must
 * steer to the Library replays rather than dead-end the showpiece.
 */
import { screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { renderWithProviders } from "@/test/render";

import { QuotaBlocked } from "./QuotaBlocked";

describe("QuotaBlocked", () => {
  it("explains the cap and links to the Library replays", () => {
    renderWithProviders(<QuotaBlocked />);
    expect(screen.getByText(/out of live runs for today/i)).toBeInTheDocument();
    const replay = screen.getByRole("link", { name: /watch a replay/i });
    expect(replay).toHaveAttribute("href", "/library");
  });

  it("offers a dismiss affordance when an onDismiss handler is provided", () => {
    renderWithProviders(<QuotaBlocked onDismiss={() => {}} />);
    expect(screen.getByRole("button", { name: /dismiss/i })).toBeInTheDocument();
  });
});

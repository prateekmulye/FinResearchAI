import { screen } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { TopNav } from "@/components/shell/TopNav";
import { renderWithProviders } from "@/test/render";

describe("TopNav — shell smoke", () => {
  beforeEach(() => {
    // Health + quota polls: keep them pending so the shell renders its resting state.
    vi.stubGlobal(
      "fetch",
      vi.fn(() => new Promise(() => {})),
    );
  });
  afterEach(() => vi.unstubAllGlobals());

  it("renders a primary navigation landmark", () => {
    renderWithProviders(<TopNav />);
    expect(screen.getByRole("navigation", { name: /primary/i })).toBeInTheDocument();
  });

  it("exposes all four section links", () => {
    renderWithProviders(<TopNav />);
    // Each label appears in the desktop link row AND the mobile row, so assert >=1.
    for (const label of ["Analyze", "Library", "Market", "Eval"]) {
      expect(
        screen.getAllByRole("link", { name: new RegExp(label, "i") }).length,
      ).toBeGreaterThanOrEqual(1);
    }
  });

  it("links the wordmark home", () => {
    renderWithProviders(<TopNav />);
    expect(screen.getByRole("link", { name: /finresearch home/i })).toHaveAttribute(
      "href",
      "/",
    );
  });

  it("renders a live status region (health dot)", () => {
    renderWithProviders(<TopNav />);
    expect(screen.getByRole("status")).toBeInTheDocument();
  });
});

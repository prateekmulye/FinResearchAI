/**
 * PageTransition owns the page's <main> landmark. The reduced-motion branch
 * used to return bare children — silently dropping the landmark for exactly
 * the users most likely to navigate by it. Both branches must render <main>.
 */
import { render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router";
import { afterEach, describe, expect, it, vi } from "vitest";

import { PageTransition } from "./PageTransition";

function stubMatchMedia(reducedMotion: boolean) {
  vi.stubGlobal(
    "matchMedia",
    vi.fn().mockImplementation((query: string) => ({
      matches: reducedMotion && query.includes("prefers-reduced-motion"),
      media: query,
      onchange: null,
      addEventListener: vi.fn(),
      removeEventListener: vi.fn(),
      addListener: vi.fn(),
      removeListener: vi.fn(),
      dispatchEvent: vi.fn(),
    })),
  );
}

afterEach(() => vi.unstubAllGlobals());

describe("PageTransition — main landmark", () => {
  it("renders a <main> landmark under prefers-reduced-motion", () => {
    stubMatchMedia(true);
    render(
      <MemoryRouter>
        <PageTransition>
          <p>page body</p>
        </PageTransition>
      </MemoryRouter>,
    );
    const main = screen.getByRole("main");
    expect(main).toBeInTheDocument();
    expect(main).toHaveTextContent("page body");
  });

  it("renders a <main> landmark with motion enabled too (parity)", () => {
    stubMatchMedia(false);
    render(
      <MemoryRouter>
        <PageTransition>
          <p>page body</p>
        </PageTransition>
      </MemoryRouter>,
    );
    expect(screen.getByRole("main")).toHaveTextContent("page body");
  });
});

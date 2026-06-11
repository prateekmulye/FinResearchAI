/**
 * DecisionReveal renders the Peak from a terminal `done` payload: the verdict
 * badge, the conviction gauge, the counted-up score, the rationale, and the
 * sanitized markdown report with a copy button.
 */
import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import type { AnalysisDone } from "@/hooks/useAnalysisStream";

import { DecisionReveal } from "./DecisionReveal";

function done(overrides: Partial<AnalysisDone> = {}): AnalysisDone {
  return {
    finalReport:
      "# Executive Summary\n\nAccumulate AAPL with an outlook of 74/100.\n\n## Bottom Line\n\nConviction 0.74.",
    finalDecision: {
      action: "BUY",
      conviction: 0.74,
      score: 74,
      rationale: "Arbiter: BUY AAPL at conviction 0.74.",
    },
    runMetrics: [],
    ...overrides,
  };
}

describe("DecisionReveal", () => {
  it("renders the verdict action, rationale, and report from a done payload", () => {
    render(<DecisionReveal done={done()} ticker="AAPL" />);
    // SignalBadge prints the action word (color is never the only signal).
    expect(screen.getByText("BUY")).toBeInTheDocument();
    expect(
      screen.getByText(/Arbiter: BUY AAPL at conviction 0\.74/),
    ).toBeInTheDocument();
    // The markdown report renders sanitized HTML structure.
    expect(
      screen.getByRole("heading", { name: /Executive Summary/i }),
    ).toBeInTheDocument();
    // Copy affordance present.
    expect(
      screen.getByRole("button", { name: /copy markdown/i }),
    ).toBeInTheDocument();
  });

  it("labels the reveal region and shows the conviction gauge label", () => {
    render(<DecisionReveal done={done()} ticker="AAPL" />);
    expect(screen.getByLabelText(/final verdict/i)).toBeInTheDocument();
    // The gauge label is mono uppercase "conviction"; at least one match exists.
    expect(screen.getAllByText(/conviction/i).length).toBeGreaterThan(0);
    expect(screen.getByText(/final decision/i)).toBeInTheDocument();
  });

  it("renders the report even when the decision is missing (degraded arbiter)", () => {
    // Use a report with no 'BUY' token so we can assert the badge is absent.
    render(
      <DecisionReveal
        done={done({
          finalDecision: null,
          finalReport: "# Executive Summary\n\nReport without a verdict header.",
        })}
        ticker="AAPL"
      />,
    );
    expect(
      screen.getByRole("heading", { name: /Executive Summary/i }),
    ).toBeInTheDocument();
    // No verdict badge in the degraded path (no final-decision header).
    expect(screen.queryByText(/final decision/i)).not.toBeInTheDocument();
  });

  it("does not inject raw HTML embedded in the report markdown", () => {
    const { container } = render(
      <DecisionReveal
        done={done({
          finalReport: "# Report\n\n<script>alert('xss')</script>\n\nSafe text.",
        })}
        ticker="AAPL"
      />,
    );
    expect(container.querySelector("script")).toBeNull();
  });

  it("keeps aria-live off the rAF count-up span; announces only the final score", () => {
    const { container } = render(<DecisionReveal done={done()} ticker="AAPL" />);

    // The rAF-mutated score span (textContent rewritten ~60fps; the text-4xl
    // one — the gauge has its own smaller counter) must be hidden from
    // assistive tech — a live region there announces every intermediate number.
    const counting = container.querySelector("span.text-4xl")!;
    expect(counting).not.toBeNull();
    expect(counting).not.toHaveAttribute("aria-live");
    expect(counting.closest('[aria-hidden="true"]')).not.toBeNull();

    // The polite announcement is a separate visually-hidden span, set once to
    // the final value and never mutated afterward.
    const announced = container.querySelector('.sr-only[aria-live="polite"]');
    expect(announced).toHaveTextContent("74/100");
  });
});

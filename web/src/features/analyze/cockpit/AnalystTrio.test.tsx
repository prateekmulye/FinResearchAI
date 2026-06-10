/**
 * AnalystTrio — per-analyst card states. A degraded analyst (node completed but
 * emitted no structured report) must say so, not show a check + "analyzing…".
 */
import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { AnalystTrio } from "./AnalystTrio";
import type { AnalystPanel } from "./pipeline";

function panel(node: string, over: Partial<AnalystPanel> = {}): AnalystPanel {
  return {
    node,
    status: "pending",
    text: "",
    summary: null,
    keyPoints: [],
    confidence: null,
    ...over,
  };
}

describe("AnalystTrio", () => {
  it("shows the structured summary once an analyst completes with a report", () => {
    render(
      <AnalystTrio
        news={panel("news_analyst", {
          status: "complete",
          summary: "Coverage skews constructive.",
        })}
        fundamentals={panel("fundamentals_analyst")}
        technicals={panel("technicals_analyst")}
      />,
    );
    expect(screen.getByText("Coverage skews constructive.")).toBeInTheDocument();
  });

  it("marks a completed analyst with no report as degraded (never 'analyzing…')", () => {
    render(
      <AnalystTrio
        news={panel("news_analyst", { status: "complete", summary: null })}
        fundamentals={panel("fundamentals_analyst")}
        technicals={panel("technicals_analyst")}
      />,
    );
    expect(screen.getByText(/no report — degraded/i)).toBeInTheDocument();
    expect(screen.queryByText(/analyzing/i)).not.toBeInTheDocument();
  });
});

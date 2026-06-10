import { describe, expect, it } from "vitest";

import { formatCompactUsd, formatPercent, formatRatio } from "@/lib/utils";

describe("formatCompactUsd", () => {
  it("abbreviates trillions / billions / millions", () => {
    expect(formatCompactUsd(3.21e12)).toBe("$3.21T");
    expect(formatCompactUsd(4.5e9)).toBe("$4.50B");
    expect(formatCompactUsd(8.1e6)).toBe("$8.10M");
  });

  it("falls through to grouped dollars below a million", () => {
    expect(formatCompactUsd(12_345)).toBe("$12,345");
  });

  it("renders an em dash for null / NaN", () => {
    expect(formatCompactUsd(null)).toBe("—");
    expect(formatCompactUsd(undefined)).toBe("—");
    expect(formatCompactUsd(NaN)).toBe("—");
  });
});

describe("formatRatio", () => {
  it("fixes precision and dashes the absent case", () => {
    expect(formatRatio(28.4)).toBe("28.40");
    expect(formatRatio(1.2345, 3)).toBe("1.234");
    expect(formatRatio(null)).toBe("—");
  });
});

describe("formatPercent", () => {
  it("scales a fraction to a percentage", () => {
    expect(formatPercent(0.184)).toBe("18.4%");
  });

  it("adds a leading sign only when signed and positive", () => {
    expect(formatPercent(0.184, { signed: true })).toBe("+18.4%");
    expect(formatPercent(-0.06, { signed: true })).toBe("-6.0%");
    expect(formatPercent(0.184, { signed: false })).toBe("18.4%");
  });

  it("dashes the absent case", () => {
    expect(formatPercent(null)).toBe("—");
  });
});

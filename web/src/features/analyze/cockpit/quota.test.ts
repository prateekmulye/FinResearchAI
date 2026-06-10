import { describe, expect, it } from "vitest";

import { isQuotaError } from "./quota";

describe("isQuotaError", () => {
  it("matches the hook's 429 rate-limit message", () => {
    expect(
      isQuotaError("Rate limited — daily live-run quota reached. Try a replay."),
    ).toBe(true);
  });

  it("matches a bare 429 / quota / replay mention", () => {
    expect(isQuotaError("analyze -> 429")).toBe(true);
    expect(isQuotaError("quota exhausted")).toBe(true);
  });

  it("does NOT match a genuine failure (so it shows the error band, not a steer)", () => {
    expect(isQuotaError("stream ended early")).toBe(false);
    expect(isQuotaError("network error")).toBe(false);
    expect(isQuotaError(null)).toBe(false);
  });
});

import { describe, expect, it } from "vitest";

import { isQuotaError } from "./quota";

describe("isQuotaError", () => {
  it("matches a real HTTP 429 via the status code, regardless of message", () => {
    expect(isQuotaError("analyze -> 429", 429)).toBe(true);
    expect(isQuotaError("anything at all", 429)).toBe(true);
  });

  it("matches the hook's rate-limit message when no status is available", () => {
    expect(
      isQuotaError("Rate limited — daily live-run quota reached. Try a replay.", null),
    ).toBe(true);
    expect(isQuotaError("quota exhausted", null)).toBe(true);
  });

  it("does NOT match incidental '429' or 'replay' text in arbitrary errors", () => {
    expect(isQuotaError("replay stream interrupted", null)).toBe(false);
    expect(isQuotaError("analyze -> 429", null)).toBe(false);
  });

  it("does NOT match a genuine failure (so it shows the error band, not a steer)", () => {
    expect(isQuotaError("stream ended early", null)).toBe(false);
    expect(isQuotaError("network error", 0)).toBe(false);
    expect(isQuotaError("GET /api -> 500", 500)).toBe(false);
    expect(isQuotaError(null, null)).toBe(false);
  });
});

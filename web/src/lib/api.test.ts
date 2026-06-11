import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { api, buildUrl, deriveQuotaState, type QuotaStatus } from "@/lib/api";

describe("buildUrl", () => {
  it("returns the bare path when there are no params", () => {
    expect(buildUrl("/api/library")).toBe("/api/library");
  });

  it("appends defined params", () => {
    expect(buildUrl("/api/library", { ticker: "AAPL", limit: 50 })).toBe(
      "/api/library?ticker=AAPL&limit=50",
    );
  });

  it("skips null, undefined, and empty-string params", () => {
    expect(
      buildUrl("/api/library", {
        ticker: "AAPL",
        status: undefined,
        offset: null,
        q: "",
      }),
    ).toBe("/api/library?ticker=AAPL");
  });

  it("encodes special characters", () => {
    expect(buildUrl("/api/market/instruments", { q: "a b&c" })).toContain("q=a+b%26c");
  });

  it("serializes booleans and numbers", () => {
    expect(buildUrl("/x", { a: true, b: 0 })).toBe("/x?a=true&b=0");
  });
});

describe("api client — request shaping", () => {
  const fetchMock = vi.fn();

  beforeEach(() => {
    fetchMock.mockReset();
    fetchMock.mockResolvedValue({
      ok: true,
      json: async () => ({}),
    } as Response);
    vi.stubGlobal("fetch", fetchMock);
  });

  afterEach(() => vi.unstubAllGlobals());

  it("library() hits the right URL with params", async () => {
    await api.library({ ticker: "msft", status: "finished", limit: 10 });
    expect(fetchMock).toHaveBeenCalledTimes(1);
    expect(fetchMock.mock.calls[0]![0]).toBe(
      "/api/library?ticker=msft&status=finished&limit=10",
    );
  });

  it("run() encodes the run id into the path", async () => {
    await api.run("abc 123");
    expect(fetchMock.mock.calls[0]![0]).toBe("/api/runs/abc%20123");
  });

  it("prices() builds the per-ticker market path", async () => {
    await api.prices("BRK.B", { days: 90 });
    expect(fetchMock.mock.calls[0]![0]).toBe("/api/market/BRK.B/prices?days=90");
  });

  it("instruments() defaults to the instruments endpoint", async () => {
    await api.instruments({ q: "apple" });
    expect(fetchMock.mock.calls[0]![0]).toBe("/api/market/instruments?q=apple");
  });

  it("prices() threads exchange + days, encoding the ticker", async () => {
    await api.prices("RELIANCE.NS", { exchange: "NSE", days: 180 });
    expect(fetchMock.mock.calls[0]![0]).toBe(
      "/api/market/RELIANCE.NS/prices?exchange=NSE&days=180",
    );
  });

  it("fundamentals() builds the per-ticker fundamentals path", async () => {
    await api.fundamentals("0700.HK", { exchange: "HKEX" });
    expect(fetchMock.mock.calls[0]![0]).toBe(
      "/api/market/0700.HK/fundamentals?exchange=HKEX",
    );
  });

  it("news() threads exchange + limit", async () => {
    await api.news("NVDA", { limit: 8 });
    expect(fetchMock.mock.calls[0]![0]).toBe("/api/market/NVDA/news?limit=8");
  });

  it("searchResearch() hits /api/search with the query", async () => {
    await api.searchResearch({ q: "tariff risk", limit: 12 });
    expect(fetchMock.mock.calls[0]![0]).toBe(
      "/api/search?q=tariff+risk&limit=12",
    );
  });

  it("evalResults() hits /api/eval/results with the limit", async () => {
    await api.evalResults({ limit: 20 });
    expect(fetchMock.mock.calls[0]![0]).toBe("/api/eval/results?limit=20");
  });

  it("quota() and health() hit fixed paths", async () => {
    await api.quota();
    await api.health();
    expect(fetchMock.mock.calls[0]![0]).toBe("/api/quota");
    expect(fetchMock.mock.calls[1]![0]).toBe("/healthz");
  });

  it("throws ApiError with the status on non-2xx", async () => {
    fetchMock.mockResolvedValueOnce({
      ok: false,
      status: 503,
      json: async () => ({ detail: "warehouse disabled" }),
    } as Response);
    await expect(api.evalResults()).rejects.toMatchObject({
      name: "ApiError",
      status: 503,
    });
  });
});

describe("deriveQuotaState", () => {
  const base: QuotaStatus = {
    metered: true,
    ip_used: 0,
    ip_limit: 5,
    global_used: 0,
    global_limit: 100,
    admin: false,
  };

  it("returns 'unknown' while loading", () => {
    expect(deriveQuotaState(undefined).kind).toBe("unknown");
  });

  it("admin overrides everything", () => {
    expect(deriveQuotaState({ ...base, admin: true }).kind).toBe("admin");
  });

  it("unmetered demo when metered=false", () => {
    const s = deriveQuotaState({ ...base, metered: false });
    expect(s.kind).toBe("unmetered");
  });

  it("reports remaining live runs when budget is available", () => {
    const s = deriveQuotaState({ ...base, ip_used: 2, ip_limit: 5 });
    expect(s).toMatchObject({ kind: "available", remaining: 3 });
    expect(s.label).toBe("3 live runs left today");
  });

  it("singularizes the label at one run left", () => {
    const s = deriveQuotaState({ ...base, ip_used: 4, ip_limit: 5 });
    expect(s.label).toBe("1 live run left today");
  });

  it("replay-only when the per-IP budget is spent", () => {
    expect(deriveQuotaState({ ...base, ip_used: 5, ip_limit: 5 }).kind).toBe(
      "replay-only",
    );
  });

  it("replay-only when the GLOBAL budget binds even if IP has room", () => {
    const s = deriveQuotaState({
      ...base,
      ip_used: 0,
      ip_limit: 5,
      global_used: 100,
      global_limit: 100,
    });
    expect(s.kind).toBe("replay-only");
  });

  it("uses the smaller of ip/global remaining as the count", () => {
    const s = deriveQuotaState({
      ...base,
      ip_used: 1,
      ip_limit: 5, // 4 left
      global_used: 98,
      global_limit: 100, // 2 left -> binds
    });
    expect(s).toMatchObject({ kind: "available", remaining: 2 });
  });

  it("degraded outage (200 + degraded:true, null counters) is 'quota unavailable' — never exhausted", () => {
    const s = deriveQuotaState({
      metered: true,
      degraded: true,
      ip_used: null,
      ip_limit: null,
      global_used: null,
      global_limit: null,
      admin: false,
    });
    expect(s.kind).toBe("degraded");
    expect(s.label).toBe("quota unavailable");
    expect(s.kind).not.toBe("replay-only");
  });

  it("admin still overrides a degraded payload", () => {
    const s = deriveQuotaState({
      metered: true,
      degraded: true,
      ip_used: null,
      ip_limit: null,
      global_used: null,
      global_limit: null,
      admin: true,
    });
    expect(s.kind).toBe("admin");
  });
});

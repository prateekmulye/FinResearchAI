import { screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { QuotaPill } from "@/components/shell/QuotaPill";
import { type QuotaStatus } from "@/lib/api";
import { renderWithProviders } from "@/test/render";

function mockQuota(payload: QuotaStatus) {
  vi.stubGlobal(
    "fetch",
    vi.fn(async () => ({ ok: true, json: async () => payload }) as Response),
  );
}

describe("QuotaPill — states", () => {
  afterEach(() => vi.unstubAllGlobals());

  beforeEach(() => vi.clearAllMocks());

  it("shows remaining live runs when budget is available", async () => {
    mockQuota({
      metered: true,
      ip_used: 1,
      ip_limit: 5,
      global_used: 0,
      global_limit: 100,
      admin: false,
    });
    renderWithProviders(<QuotaPill />);
    await waitFor(() =>
      expect(screen.getByText(/4 live runs left today/i)).toBeInTheDocument(),
    );
  });

  it("shows replay-only when the quota is spent", async () => {
    mockQuota({
      metered: true,
      ip_used: 5,
      ip_limit: 5,
      global_used: 10,
      global_limit: 100,
      admin: false,
    });
    renderWithProviders(<QuotaPill />);
    await waitFor(() => expect(screen.getByText(/replay-only/i)).toBeInTheDocument());
  });

  it("shows admin · unlimited for admins", async () => {
    mockQuota({
      metered: true,
      ip_used: 0,
      ip_limit: 5,
      global_used: 0,
      global_limit: 100,
      admin: true,
    });
    renderWithProviders(<QuotaPill />);
    await waitFor(() =>
      expect(screen.getByText(/admin · unlimited/i)).toBeInTheDocument(),
    );
  });

  it("shows unmetered demo when the quota system is off", async () => {
    mockQuota({
      metered: false,
      ip_used: null,
      ip_limit: null,
      global_used: null,
      global_limit: null,
      admin: false,
    });
    renderWithProviders(<QuotaPill />);
    await waitFor(() =>
      expect(screen.getByText(/unmetered demo/i)).toBeInTheDocument(),
    );
  });

  it("shows the neutral 'quota unavailable' on a degraded read (DB outage)", async () => {
    // Backend answers 200 with degraded:true + null counters when the quota
    // DB read fails — the pill must say "unavailable", never "replay-only".
    mockQuota({
      metered: true,
      degraded: true,
      ip_used: null,
      ip_limit: null,
      global_used: null,
      global_limit: null,
      admin: false,
    });
    renderWithProviders(<QuotaPill />);
    await waitFor(() =>
      expect(screen.getByText(/quota unavailable/i)).toBeInTheDocument(),
    );
    expect(screen.queryByText(/replay-only/i)).not.toBeInTheDocument();
  });
});

/**
 * useAnalysisStream — stream lifecycle tests.
 *
 * Mocks fetch with a controllable ReadableStream body so each test can push
 * SSE frames, close the stream, or abort, and assert the phase transitions:
 *   - stop() lands the phase back at "idle" (no dead Stop button)
 *   - unmount aborts the in-flight request
 *   - a stream that drains without done/error becomes phase "error"
 *   - a terminal done/error frame wins (never "stream ended early")
 */
import { act, renderHook, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { useAnalysisStream } from "@/hooks/useAnalysisStream";

const encoder = new TextEncoder();

function sseFrame(event: string, payload: Record<string, unknown>): Uint8Array {
  return encoder.encode(`event: ${event}\ndata: ${JSON.stringify(payload)}\n\n`);
}

const startFrame = () =>
  sseFrame("start", {
    type: "start",
    run_id: "r1",
    ticker: "AAPL",
    investor_mode: "Neutral",
  });

/** A fetch mock whose response body is a hand-cranked SSE stream. */
function mockSse() {
  let enqueue!: (chunk: Uint8Array) => void;
  let close!: () => void;
  let fail!: (err: unknown) => void;
  const body = new ReadableStream<Uint8Array>({
    start(c) {
      enqueue = (chunk) => c.enqueue(chunk);
      close = () => c.close();
      fail = (err) => c.error(err);
    },
  });

  let signal: AbortSignal | null = null;
  const fetchMock = vi.fn(async (_input: unknown, init?: RequestInit) => {
    signal = init?.signal ?? null;
    // Real fetch rejects the pending read with AbortError on abort; mimic it.
    signal?.addEventListener("abort", () => {
      try {
        fail(new DOMException("The operation was aborted.", "AbortError"));
      } catch {
        /* stream already closed */
      }
    });
    return { ok: true, status: 200, body } as Response;
  });

  return {
    fetchMock,
    push: (c: Uint8Array) => enqueue(c),
    close: () => close(),
    getSignal: () => signal,
  };
}

function renderStream() {
  const sse = mockSse();
  vi.stubGlobal("fetch", sse.fetchMock);
  const utils = renderHook(() => useAnalysisStream());
  return { ...sse, ...utils };
}

async function startRun(result: { current: ReturnType<typeof useAnalysisStream> }) {
  let promise!: Promise<void>;
  act(() => {
    promise = result.current.start({ ticker: "AAPL", investorMode: "Neutral" });
  });
  return promise;
}

afterEach(() => vi.unstubAllGlobals());

describe("useAnalysisStream — stop()", () => {
  it("returns the phase to idle so the form recovers its Run affordance", async () => {
    const { result, push } = renderStream();
    const run = startRun(result);

    act(() => push(startFrame()));
    await waitFor(() => expect(result.current.state.phase).toBe("streaming"));

    act(() => result.current.stop());
    expect(result.current.state.phase).toBe("idle");
    expect(result.current.isActive).toBe(false);

    // The aborted read loop must not retroactively flip the phase to error.
    await act(async () => {
      await run;
    });
    expect(result.current.state.phase).toBe("idle");
    expect(result.current.state.error).toBeNull();
  });

  it("never clobbers a terminal done state", async () => {
    const { result, push, close } = renderStream();
    const run = startRun(result);

    act(() => push(startFrame()));
    act(() =>
      push(
        sseFrame("done", {
          type: "done",
          run_id: "r1",
          final_report: "# R",
          final_decision: {},
          run_metrics: [],
        }),
      ),
    );
    act(() => close());
    await act(async () => {
      await run;
    });
    await waitFor(() => expect(result.current.state.phase).toBe("done"));

    act(() => result.current.stop());
    expect(result.current.state.phase).toBe("done");
  });
});

describe("useAnalysisStream — unmount", () => {
  it("aborts the in-flight request", async () => {
    const { result, push, getSignal, fetchMock, unmount } = renderStream();
    void startRun(result);

    await waitFor(() => expect(fetchMock).toHaveBeenCalledOnce());
    act(() => push(startFrame()));
    await waitFor(() => expect(result.current.state.phase).toBe("streaming"));
    expect(getSignal()?.aborted).toBe(false);

    unmount();
    expect(getSignal()?.aborted).toBe(true);
  });
});

describe("useAnalysisStream — stream draining without a terminal event", () => {
  it("dispatches 'stream ended early' instead of staying streaming forever", async () => {
    const { result, push, close } = renderStream();
    const run = startRun(result);

    act(() => push(startFrame()));
    act(() =>
      push(
        sseFrame("node_start", { type: "node_start", run_id: "r1", node: "router" }),
      ),
    );
    await waitFor(() => expect(result.current.state.phase).toBe("streaming"));

    act(() => close());
    await act(async () => {
      await run;
    });
    expect(result.current.state.phase).toBe("error");
    expect(result.current.state.error).toMatch(/stream ended early/i);
  });

  it("keeps phase done when the stream closes after a done frame", async () => {
    const { result, push, close } = renderStream();
    const run = startRun(result);

    act(() => push(startFrame()));
    act(() =>
      push(
        sseFrame("done", {
          type: "done",
          run_id: "r1",
          final_report: "# R",
          final_decision: {},
          run_metrics: [],
        }),
      ),
    );
    act(() => close());
    await act(async () => {
      await run;
    });
    expect(result.current.state.phase).toBe("done");
    expect(result.current.state.error).toBeNull();
  });

  it("keeps the backend's error message when the stream closes after an error frame", async () => {
    const { result, push, close } = renderStream();
    const run = startRun(result);

    act(() => push(startFrame()));
    act(() =>
      push(sseFrame("error", { type: "error", run_id: "r1", message: "boom" })),
    );
    act(() => close());
    await act(async () => {
      await run;
    });
    expect(result.current.state.phase).toBe("error");
    expect(result.current.state.error).toBe("boom");
  });
});

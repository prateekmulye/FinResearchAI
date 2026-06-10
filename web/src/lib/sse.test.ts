import { describe, expect, it } from "vitest";

import { SseFrameParser, decodeEvent, parseFrame, type RawSseFrame } from "@/lib/sse";

/** Build a wire SSE frame string from an event name + JSON payload. */
function frame(event: string, payload: unknown): string {
  return `event: ${event}\ndata: ${JSON.stringify(payload)}\n\n`;
}

describe("parseFrame", () => {
  it("parses event + data lines", () => {
    const f = parseFrame('event: token\ndata: {"x":1}');
    expect(f).toEqual({ event: "token", data: '{"x":1}' });
  });

  it("defaults event name to 'message' when absent", () => {
    const f = parseFrame('data: {"x":1}');
    expect(f?.event).toBe("message");
  });

  it("joins multiline data with newlines (SSE spec)", () => {
    const f = parseFrame("event: done\ndata: line-1\ndata: line-2");
    expect(f?.data).toBe("line-1\nline-2");
  });

  it("strips a single leading space after data:", () => {
    const f = parseFrame("data:  two-spaces");
    expect(f?.data).toBe(" two-spaces");
  });

  it("ignores SSE comment / heartbeat lines", () => {
    const f = parseFrame(": ping\nevent: token\ndata: hi");
    expect(f).toEqual({ event: "token", data: "hi" });
  });

  it("returns null for a frame with no data lines", () => {
    expect(parseFrame("event: token")).toBeNull();
    expect(parseFrame(": just a comment")).toBeNull();
  });
});

describe("SseFrameParser — framing", () => {
  it("emits a single complete frame", () => {
    const p = new SseFrameParser();
    const frames = p.push(frame("start", { type: "start", run_id: "r1" }));
    expect(frames).toHaveLength(1);
    expect(frames[0]!.event).toBe("start");
  });

  it("emits multiple frames from one chunk", () => {
    const p = new SseFrameParser();
    const chunk =
      frame("node_start", { node: "router" }) +
      frame("node_complete", { node: "router" });
    const frames = p.push(chunk);
    expect(frames.map((f) => f.event)).toEqual(["node_start", "node_complete"]);
  });

  it("retains a partial frame across a chunk boundary (mid-data split)", () => {
    const p = new SseFrameParser();
    const full = frame("token", { type: "token", node: "reporter", text: "hi" });
    const cut = Math.floor(full.length / 2);

    const first = p.push(full.slice(0, cut));
    expect(first).toHaveLength(0); // not yet terminated by \n\n
    const second = p.push(full.slice(cut));
    expect(second).toHaveLength(1);
    expect(decodeEvent(second[0]!)).toMatchObject({ type: "token", text: "hi" });
  });

  it("splits exactly on the blank-line boundary across chunks", () => {
    const p = new SseFrameParser();
    // Boundary "\n\n" arrives split between two chunks.
    const out1 = p.push("event: node_start\ndata: {}\n");
    expect(out1).toHaveLength(0);
    const out2 = p.push("\nevent: node_complete\ndata: {}\n\n");
    expect(out2.map((f) => f.event)).toEqual(["node_start", "node_complete"]);
  });

  it("normalizes CRLF line endings", () => {
    const p = new SseFrameParser();
    const frames = p.push("event: token\r\ndata: hi\r\n\r\n");
    expect(frames).toEqual<RawSseFrame[]>([{ event: "token", data: "hi" }]);
  });

  it("flush() drains a trailing frame with no blank line", () => {
    const p = new SseFrameParser();
    expect(p.push("event: done\ndata: {}")).toHaveLength(0);
    const flushed = p.flush();
    expect(flushed).toHaveLength(1);
    expect(flushed[0]!.event).toBe("done");
  });

  it("flush() returns nothing when the buffer is empty", () => {
    const p = new SseFrameParser();
    p.push(frame("start", { type: "start" }));
    expect(p.flush()).toHaveLength(0);
  });
});

describe("decodeEvent — all six event types", () => {
  const cases: Array<{ name: string; payload: Record<string, unknown> }> = [
    {
      name: "start",
      payload: { type: "start", run_id: "r", ticker: "AAPL", investor_mode: "Neutral" },
    },
    {
      name: "node_start",
      payload: { type: "node_start", run_id: "r", node: "router" },
    },
    {
      name: "node_complete",
      payload: { type: "node_complete", run_id: "r", node: "router", delta: { a: 1 } },
    },
    {
      name: "token",
      payload: { type: "token", run_id: "r", node: "reporter", text: "x" },
    },
    { name: "error", payload: { type: "error", run_id: "r", message: "boom" } },
    {
      name: "done",
      payload: {
        type: "done",
        run_id: "r",
        final_report: "# R",
        final_decision: { action: "BUY", conviction: 0.7, score: 72, rationale: "y" },
        run_metrics: [],
      },
    },
  ];

  for (const c of cases) {
    it(`decodes ${c.name}`, () => {
      const f = parseFrame(`event: ${c.name}\ndata: ${JSON.stringify(c.payload)}`)!;
      const event = decodeEvent(f);
      expect(event).not.toBeNull();
      expect(event!.type).toBe(c.name);
    });
  }

  it("trusts payload.type over the SSE event name", () => {
    const f: RawSseFrame = {
      event: "message",
      data: '{"type":"done","run_id":"r","final_report":"","final_decision":{},"run_metrics":[]}',
    };
    expect(decodeEvent(f)?.type).toBe("done");
  });

  it("returns null for malformed JSON", () => {
    expect(decodeEvent({ event: "token", data: "{not json" })).toBeNull();
  });

  it("returns null for an unknown event type", () => {
    expect(decodeEvent({ event: "message", data: '{"type":"weird"}' })).toBeNull();
  });

  it("returns null for a non-object payload", () => {
    expect(decodeEvent({ event: "token", data: "42" })).toBeNull();
  });

  it("rejects node-scoped events missing the node field", () => {
    for (const type of ["node_start", "node_complete", "token"]) {
      expect(
        decodeEvent({
          event: "message",
          data: JSON.stringify({ type, run_id: "r" }),
        }),
      ).toBeNull();
    }
  });

  it("rejects node-scoped events whose node field is not a string", () => {
    expect(
      decodeEvent({
        event: "token",
        data: '{"type":"token","run_id":"r","node":42,"text":"x"}',
      }),
    ).toBeNull();
  });

  it("still accepts non-node events without a node field", () => {
    expect(
      decodeEvent({
        event: "error",
        data: '{"type":"error","run_id":"r","message":"m"}',
      }),
    ).not.toBeNull();
  });
});

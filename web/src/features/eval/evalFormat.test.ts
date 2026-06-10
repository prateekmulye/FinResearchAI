/**
 * evalFormat — the null-safe summary/pairs normalization and the Functional
 * Signal Inversion (color a delta by outcome utility, not math sign). These are
 * the load-bearing correctness guarantees of the screen, so they're tested
 * exhaustively in isolation.
 */
import { describe, expect, it } from "vitest";

import {
  deltaArrow,
  deltaTone,
  formatRate,
  formatSigned,
  formatSignedInt,
  formatSignedSeconds,
  formatSignedUsd,
  readPairs,
  readSummary,
  toneColor,
} from "./evalFormat";

describe("readSummary", () => {
  const full = {
    n_tickers: 10,
    n_judged: 8,
    judge_prefers_on_rate: 0.75,
    judge_agreement_rate: 0.5,
    action_agreement_rate: 0.6,
    mean_score_delta_on_minus_off: 4.2,
    score_delta_stdev: 1.1,
    mean_cost_delta_on_minus_off: 0.024,
    mean_latency_delta_on_minus_off: 2.5,
    mean_token_delta_on_minus_off: 1200,
  };

  it("reads the long backend key names", () => {
    const s = readSummary(full);
    expect(s.nTickers).toBe(10);
    expect(s.nJudged).toBe(8);
    expect(s.judged).toBe(true);
    expect(s.judgePrefersOnRate).toBe(0.75);
    expect(s.meanScoreDelta).toBe(4.2);
    expect(s.meanCostDelta).toBe(0.024);
    expect(s.meanLatencyDelta).toBe(2.5);
    expect(s.meanTokenDelta).toBe(1200);
  });

  it("nulls the judge rates when nothing was judged (not a fake 0%)", () => {
    const s = readSummary({ ...full, n_judged: 0, judge_prefers_on_rate: 0.0 });
    expect(s.judged).toBe(false);
    expect(s.judgePrefersOnRate).toBeNull();
    expect(s.judgeAgreementRate).toBeNull();
    // Action agreement is independent of judging — still read.
    expect(s.actionAgreementRate).toBe(0.6);
  });

  it("degrades missing / malformed keys to null without throwing", () => {
    const s = readSummary({ n_tickers: 3 });
    expect(s.nTickers).toBe(3);
    expect(s.meanScoreDelta).toBeNull();
    expect(s.meanCostDelta).toBeNull();
    expect(s.actionAgreementRate).toBeNull();
  });

  it("rejects non-finite numbers", () => {
    const s = readSummary({
      n_tickers: 2,
      n_judged: 2,
      mean_cost_delta_on_minus_off: Infinity,
      mean_score_delta_on_minus_off: NaN,
    });
    expect(s.meanCostDelta).toBeNull();
    expect(s.meanScoreDelta).toBeNull();
  });
});

describe("readPairs", () => {
  const raw = [
    {
      ticker: "AAPL",
      action_on: "BUY",
      action_off: "HOLD",
      actions_agree: false,
      score_on: 80,
      score_off: 55,
      score_delta: 25,
      cost_on: 0.06,
      cost_off: 0.02,
      latency_on: 4.0,
      latency_off: 1.5,
      tokens_on: 150,
      tokens_off: 60,
      judge_preferred: "on",
      judge_agreement: false,
      judge_confidence: 0.7,
    },
  ];

  it("maps the per-ticker shape and derives deltas", () => {
    const p = readPairs(raw)[0]!;
    expect(p.ticker).toBe("AAPL");
    expect(p.actionOn).toBe("BUY");
    expect(p.actionOff).toBe("HOLD");
    expect(p.actionsAgree).toBe(false);
    expect(p.scoreDelta).toBe(25);
    expect(p.costDelta).toBeCloseTo(0.04, 6);
    expect(p.latencyDelta).toBeCloseTo(2.5, 6);
    expect(p.tokenDelta).toBe(90);
    expect(p.judgePreferred).toBe("on");
    expect(p.judgeConfidence).toBe(0.7);
  });

  it("handles the 'tie' and null judge-preference states", () => {
    const parsed = readPairs([
      { ticker: "T", judge_preferred: "tie" },
      { ticker: "N" }, // no judge fields
    ]);
    const tie = parsed[0]!;
    const none = parsed[1]!;
    expect(tie.judgePreferred).toBe("tie");
    expect(none.judgePreferred).toBeNull();
    expect(none.judgeAgreement).toBeNull();
    expect(none.judgeConfidence).toBeNull();
  });

  it("derives score delta when the explicit field is absent", () => {
    const p = readPairs([{ ticker: "X", score_on: 70, score_off: 50 }])[0]!;
    expect(p.scoreDelta).toBe(20);
  });

  it("falls back to comparing actions when actions_agree is missing", () => {
    const parsed = readPairs([
      { ticker: "S", action_on: "BUY", action_off: "BUY" },
      { ticker: "D", action_on: "BUY", action_off: "SELL" },
    ]);
    expect(parsed[0]!.actionsAgree).toBe(true);
    expect(parsed[1]!.actionsAgree).toBe(false);
  });

  it("returns [] for non-array payloads", () => {
    expect(readPairs(null)).toEqual([]);
    expect(readPairs(undefined)).toEqual([]);
    expect(readPairs({})).toEqual([]);
  });

  it("rejects unknown action strings to null", () => {
    const p = readPairs([{ ticker: "Z", action_on: "MAYBE", action_off: "BUY" }])[0]!;
    expect(p.actionOn).toBeNull();
    expect(p.actionOff).toBe("BUY");
  });
});

describe("deltaTone — functional signal inversion", () => {
  it("score: more is better (positive=good, negative=bad)", () => {
    expect(deltaTone(5, "more-is-better")).toBe("good");
    expect(deltaTone(-5, "more-is-better")).toBe("bad");
  });

  it("cost/latency: less is better (positive=bad, negative=good)", () => {
    expect(deltaTone(0.02, "less-is-better")).toBe("bad");
    expect(deltaTone(-0.02, "less-is-better")).toBe("good");
  });

  it("zero and null are neutral", () => {
    expect(deltaTone(0, "more-is-better")).toBe("neutral");
    expect(deltaTone(null, "less-is-better")).toBe("neutral");
  });

  it("maps tones to the right OKLCH tokens (amber for friction, not red)", () => {
    expect(toneColor("good")).toBe("var(--color-bull)");
    expect(toneColor("bad")).toBe("var(--color-hold)");
    expect(toneColor("neutral")).toBe("var(--color-fg-muted)");
  });
});

describe("deltaArrow", () => {
  it("points by sign, flat on zero/null", () => {
    expect(deltaArrow(3)).toBe("up");
    expect(deltaArrow(-3)).toBe("down");
    expect(deltaArrow(0)).toBe("flat");
    expect(deltaArrow(null)).toBe("flat");
  });
});

describe("signed formatters", () => {
  it("formatRate", () => {
    expect(formatRate(0.75)).toBe("75%");
    expect(formatRate(null)).toBe("—");
  });

  it("formatSigned leads with + for positives", () => {
    expect(formatSigned(4.2)).toBe("+4.2");
    expect(formatSigned(-1)).toBe("-1.0");
    expect(formatSigned(null)).toBe("—");
  });

  it("formatSignedUsd uses 4dp for tiny costs", () => {
    expect(formatSignedUsd(0.0024)).toBe("+$0.0024");
    expect(formatSignedUsd(-0.5)).toBe("-$0.50");
    expect(formatSignedUsd(0)).toBe("$0.0000");
  });

  it("formatSignedSeconds and formatSignedInt", () => {
    expect(formatSignedSeconds(2.5)).toBe("+2.5s");
    expect(formatSignedSeconds(-1)).toBe("-1.0s");
    expect(formatSignedInt(1200)).toBe("+1,200");
    expect(formatSignedInt(-90)).toBe("-90");
  });
});

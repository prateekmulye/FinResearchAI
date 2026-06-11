"""Deterministic fake chat model for APP_FAKE_LLM demo mode (WP-5).

PRODUCTION code (no imports from tests/). Implements exactly the LLM surface
every node uses — verified against all call sites:

    get_llm(tier).with_structured_output(Schema, method=STRUCT_METHOD)
                 .ainvoke(messages, config={"callbacks": [tracker]})

plus a bare ``.ainvoke`` returning an ``AIMessage`` for completeness (no
current node calls the raw model). The structured ainvoke:

- returns a plausible, fully-valid instance of THE schema it was bound to,
  dispatched by ``schema.__name__`` with a generic defaults/model_construct
  fallback for unknown schemas;
- is deterministic: outputs are pure functions of (schema, prompt text), with
  content keyed by the ticker extracted from the prompt so different tickers
  produce visibly different reports;
- fires the CostTracker callbacks (on_llm_start/on_llm_end with token_usage)
  so per-node run metrics stay realistic in fake mode, including a
  deterministic hash-derived 80-400ms synthetic latency injected by backdating
  the tracker's start marker (never by sleeping).
"""
from __future__ import annotations

import hashlib
import re
import time
from types import SimpleNamespace
from typing import Any

from langchain_core.messages import AIMessage

from src.tools.fake_data import demo_score, fake_fundamentals, fake_technicals, news_url

_ROLE_RE = re.compile(r"role='(bull|bear|conservative|aggressive)'")
_ROUND_RE = re.compile(r"round=(\d+)")
_TICKER_RES = (
    re.compile(r"Ticker:\s*([A-Za-z0-9.\-]{1,15})"),
    re.compile(r"symbol or company:\s*'([A-Za-z0-9.\-]{1,15})'"),
    re.compile(r"Topic:\s*([A-Za-z0-9.\-]{1,15})"),
)

# yfinance-style suffix -> (screener, exchange); bare tickers default to the US.
_SUFFIX_MAP = {
    ".NS": ("india", "NSE"),
    ".BO": ("india", "BSE"),
    ".T": ("japan", "TSE"),
    ".SS": ("china", "SSE"),
    ".SZ": ("china", "SZSE"),
    ".HK": ("hongkong", "HKEX"),
}


def _h(key: str) -> int:
    return int.from_bytes(hashlib.sha256(key.encode("utf-8")).digest()[:8], "big")


def _text_of(input_: Any) -> str:
    if isinstance(input_, str):
        return input_
    parts: list[str] = []
    for m in input_ or []:
        content = m.get("content") if isinstance(m, dict) else getattr(m, "content", "")
        parts.append(str(content))
    return "\n".join(parts)


def _ticker_of(text: str) -> str:
    for pattern in _TICKER_RES:
        match = pattern.search(text)
        if match:
            return match.group(1).strip().upper()
    return "DEMO"


# Well-known tickers that deterministically read bearish so demos can showcase
# the SELL path (everything else maps BUY/HOLD from its demo_score).
_SELL_TICKERS = frozenset({"GME"})


def _action_for(ticker: str) -> tuple[str, float, int]:
    if ticker in _SELL_TICKERS:
        # Mirror the outlook score into the bearish half of the scale; conviction
        # is confidence in the SELL call itself, so it mirrors back up.
        score = 100 - demo_score(ticker)
        return "SELL", round((100 - score) / 100, 2), score
    score = demo_score(ticker)
    action = "BUY" if score >= 70 else "HOLD"
    return action, round(score / 100, 2), score


# --------------------------------------------------------------------------
# Per-schema canned content (dispatched by schema.__name__; the schema CLASS
# passed to with_structured_output is used to construct, so no node imports).
# --------------------------------------------------------------------------


def _ticker_resolution(schema: type, text: str, ticker: str) -> Any:
    screener, exchange = "america", "NASDAQ"
    for suffix, (scr, exc) in _SUFFIX_MAP.items():
        if ticker.endswith(suffix):
            screener, exchange = scr, exc
            break
    return schema(resolved_ticker=ticker, screener=screener, exchange=exchange)


def _analyst_report(schema: type, text: str, ticker: str) -> Any:
    action, conviction, score = _action_for(ticker)
    confidence = round(0.6 + (_h(f"{ticker}:conf") % 30) / 100, 2)
    if "news analyst" in text:
        return schema(
            summary=(
                f"Coverage of {ticker} skews constructive: earnings strength and a new "
                "product cycle dominate headlines, partially offset by a regulatory inquiry."
            ),
            key_points=[
                f"{ticker} beat consensus on revenue and EPS last quarter",
                "Sell-side price targets drifting higher on margin expansion",
                "Open regulatory inquiry is the main overhang",
            ],
            confidence=confidence,
            citations=[news_url(ticker, i) for i in range(3)],
        )
    if "fundamentals analyst" in text:
        f = fake_fundamentals(ticker)
        return schema(
            summary=(
                f"{ticker} shows {'solid' if score >= 70 else 'mixed'} financial health: "
                f"P/E {f.trailing_pe}, profit margins {f.profit_margins:.0%}, "
                f"revenue growth {f.revenue_growth:.1%}."
            ),
            key_points=[
                f"Trailing P/E {f.trailing_pe} vs forward {f.forward_pe}",
                f"Profit margins {f.profit_margins:.0%} on gross margins {f.gross_margins:.0%}",
                f"Beta {f.beta} with dividend yield {f.dividend_yield:.2%}",
            ],
            data=f.to_dict(),
            confidence=confidence,
        )
    if "technical analyst" in text:
        t = fake_technicals(ticker, "america", "NASDAQ")
        return schema(
            summary=(
                f"Technical posture for {ticker} is {t.recommendation}: RSI {t.rsi}, "
                f"{t.buy_signals} buy vs {t.sell_signals} sell signals on the daily."
            ),
            key_points=[
                f"TradingView consensus {t.recommendation}",
                f"RSI {t.rsi} — {'overbought watch' if (t.rsi or 0) > 70 else 'room to run'}",
                f"MACD {t.macd} above signal {t.macd_signal}",
            ],
            data=t.to_dict(),
            confidence=confidence,
        )
    return schema(
        summary=f"Analyst view on {ticker}: balanced with a {action} lean.",
        key_points=[f"{ticker} composite outlook score {score}/100"],
        confidence=confidence,
    )


def _debate_turn(schema: type, text: str, ticker: str) -> Any:
    action, _, score = _action_for(ticker)
    roles = _ROLE_RE.findall(text)
    if {"bull", "bear"} <= set(roles):
        # facilitator/synthesis verdict: "set role='bull' if bullish else role='bear'"
        role = "bull" if score >= 70 else "bear"
    else:
        role = roles[0] if roles else "bull"
    round_match = _ROUND_RE.search(text)
    rnd = int(round_match.group(1)) if round_match else 1
    arguments = {
        "bull": (
            f"{ticker}'s earnings momentum, expanding margins, and a fresh product cycle "
            f"support accumulation here; the regulatory overhang is priced in and the "
            f"technical tape confirms demand (outlook {score}/100)."
        ),
        "bear": (
            f"{ticker}'s valuation already discounts the good news; decelerating growth "
            f"and the open regulatory inquiry cap upside, so risk/reward favors patience "
            f"(outlook only {score}/100)."
        ),
        "conservative": (
            f"Size down on {ticker}: concentration and headline risk argue for a tighter "
            "stop and partial exposure until the inquiry resolves."
        ),
        "aggressive": (
            f"Lean in on {ticker}: the trend, flows, and earnings revisions all point one "
            "way — under-sizing here is the real risk."
        ),
    }
    return schema(role=role, round=rnd, argument=arguments[role])


def _trade_proposal(schema: type, text: str, ticker: str) -> Any:
    action, conviction, score = _action_for(ticker)
    view = {"BUY": "bullish", "SELL": "bearish"}.get(action, "balanced")
    return schema(
        action=action,
        conviction=conviction,
        score=score,
        rationale=(
            f"{action} {ticker}: prevailing research view is "
            f"{view} (outlook {score}/100) on earnings "
            "momentum and supportive technicals, sized against the regulatory overhang."
        ),
    )


def _risk_stance(schema: type, text: str, ticker: str) -> Any:
    if "CONSERVATIVE" in text or "conservative" in text:
        return schema(
            stance=(
                f"Capital preservation first on {ticker}: cap position size, use a tight "
                "stop under recent support, and scale in only after the regulatory "
                "inquiry clears."
            )
        )
    return schema(
        stance=(
            f"The trend in {ticker} is established and earnings revisions are positive — "
            "take the full position now; hedging away this much signal costs more than "
            "the tail it protects."
        )
    )


def _final_decision(schema: type, text: str, ticker: str) -> Any:
    action, conviction, score = _action_for(ticker)
    return schema(
        action=action,
        conviction=conviction,
        score=score,
        rationale=(
            f"Arbiter: {action} {ticker} at conviction {conviction:.2f}. The aggressive "
            "case (trend + revisions) outweighs the conservative overhang, with sizing "
            "tempered per the risk debate."
        ),
    )


def _report_payload(schema: type, text: str, ticker: str) -> Any:
    action, conviction, score = _action_for(ticker)
    f = fake_fundamentals(ticker)
    t = fake_technicals(ticker, "america", "NASDAQ")
    sections = [
        {"heading": "Executive Summary",
         "body": (f"{ticker} screens as a {action} with an outlook score of {score}/100. "
                  "Earnings momentum and technical confirmation lead; a regulatory inquiry "
                  "is the principal overhang.")},
        {"heading": "Bull vs. Bear",
         "body": ("The bull case rests on margin expansion and a new product cycle; the "
                  "bear case on valuation and headline risk. The debate resolved "
                  f"{'bullish' if score >= 70 else 'cautious'} this run.")},
        {"heading": "Fundamentals",
         "body": (f"P/E {f.trailing_pe} (forward {f.forward_pe}), profit margins "
                  f"{f.profit_margins:.0%}, revenue growth {f.revenue_growth:.1%}, "
                  f"beta {f.beta}.")},
        {"heading": "Technicals",
         "body": (f"Daily consensus {t.recommendation}; RSI {t.rsi}, MACD {t.macd} vs "
                  f"signal {t.macd_signal}, {t.buy_signals} buy / {t.sell_signals} sell "
                  "signals.")},
        {"heading": "Risk Assessment",
         "body": ("Conservative desk wants reduced size pending the inquiry; aggressive "
                  "desk takes the trend at full size. Arbiter sized between the two.")},
        {"heading": "Bottom Line",
         "body": f"{action} — conviction {conviction:.2f}, score {score}/100."},
    ]
    financial_data = {
        "valuation": max(5.0, 100.0 - float(f.trailing_pe or 20) * 2),
        "growth": min(95.0, 50.0 + float(f.revenue_growth or 0) * 400),
        "profitability": min(95.0, float(f.profit_margins or 0.1) * 300),
        "momentum": min(95.0, float(t.rsi or 50) + 10),
        "sentiment": float(score),
        "risk": float(100 - score // 2),
        "metric_cards": [
            {"label": "P/E", "value": f"{f.trailing_pe}"},
            {"label": "RSI", "value": f"{t.rsi}"},
            {"label": "Conviction", "value": f"{conviction:.2f}"},
        ],
    }
    return schema(sections=sections, financial_data=financial_data)


_BUILDERS = {
    "TickerResolution": _ticker_resolution,
    "AnalystReport": _analyst_report,
    "DebateTurn": _debate_turn,
    "TradeProposal": _trade_proposal,
    "RiskStance": _risk_stance,
    "FinalDecision": _final_decision,
    "ReportPayload": _report_payload,
}


def _build(schema: Any, text: str) -> Any:
    ticker = _ticker_of(text)
    name = getattr(schema, "__name__", "")
    builder = _BUILDERS.get(name)
    if builder is not None:
        return builder(schema, text, ticker)
    # Generic fallback: defaults if they validate, else an unvalidated shell.
    try:
        return schema()
    except Exception:
        return schema.model_construct()


class _FakeStructured:
    """Stand-in for ``llm.with_structured_output(Schema)``: async-invokable,
    deterministic, and CostTracker-callback-compatible."""

    def __init__(self, schema: Any, tier: str) -> None:
        self._schema = schema
        self._tier = tier

    def _fire(self, callbacks: list[Any], text: str) -> None:
        # one start/end pair per call with plausible token usage
        rid = f"fake-{time.monotonic_ns()}"
        # CostTracker measures wall-clock perf_counter() between on_llm_start
        # and on_llm_end (src/llm/cost.py keeps the start in `_starts[run_id]`).
        # Backdate that marker by a deterministic hash-derived 80-400ms so the
        # recorded latency looks plausible WITHOUT sleeping — manipulating the
        # timing exactly the way the tracker computes it. Guarded so callbacks
        # without a `_starts` dict are untouched.
        synthetic_latency_s = 0.08 + (_h(f"latency:{text[:200]}") % 321) / 1000
        for cb in callbacks:
            if hasattr(cb, "on_llm_start"):
                cb.on_llm_start({}, [text[:200]], run_id=rid)
            starts = getattr(cb, "_starts", None)
            if isinstance(starts, dict) and rid in starts:
                starts[rid] -= synthetic_latency_s
        response = SimpleNamespace(
            llm_output={
                "token_usage": {
                    "prompt_tokens": max(1, len(text) // 4),
                    "completion_tokens": 64 + _h(text) % 64,
                },
                "model_name": f"fake-{self._tier}",
            }
        )
        for cb in callbacks:
            if hasattr(cb, "on_llm_end"):
                cb.on_llm_end(response, run_id=rid)

    async def ainvoke(self, input: Any, config: dict | None = None, **kwargs: Any) -> Any:
        text = _text_of(input)
        result = _build(self._schema, text)
        self._fire((config or {}).get("callbacks") or [], text)
        return result

    def invoke(self, input: Any, config: dict | None = None, **kwargs: Any) -> Any:
        text = _text_of(input)
        result = _build(self._schema, text)
        self._fire((config or {}).get("callbacks") or [], text)
        return result


class FakeChatModel:
    """get_llm() stand-in when settings.fake_llm is on (both tiers)."""

    def __init__(self, tier: str = "quick") -> None:
        self.tier = tier

    def with_structured_output(
        self, schema: Any, method: str | None = None, **kwargs: Any
    ) -> _FakeStructured:
        return _FakeStructured(schema, self.tier)

    async def ainvoke(self, input: Any, config: dict | None = None, **kwargs: Any) -> AIMessage:
        ticker = _ticker_of(_text_of(input))
        return AIMessage(
            content=f"[fake-{self.tier}] deterministic demo response for {ticker}."
        )

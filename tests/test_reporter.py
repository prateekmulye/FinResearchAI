# tests/test_reporter.py
"""WP-F reporter unit tests — no network. All LLM calls are mocked."""
from __future__ import annotations

import pytest
from pydantic import ValidationError

import src.agents.reporter as reporter_mod
from src.agents.reporter import (
    REPORTER_SYSTEM_PROMPT,
    FinancialData,
    MetricCard,
    ReportPayload,
    ReportSection,
    aggregate_metrics,
    build_report_messages,
    render_metrics_footer,
    render_verdict_header,
    reporter,
)

# ---------------------------------------------------------------------------
# Task 2: Schema tests
# ---------------------------------------------------------------------------


def test_financial_data_clamps_and_defaults():
    fd = FinancialData(
        valuation=120.0, growth=-5.0, profitability=50.0,
        momentum=50.0, sentiment=50.0, risk=50.0,
    )
    assert fd.valuation == 100.0
    assert fd.growth == 0.0


def test_financial_data_model_dump_is_plain_dict():
    fd = FinancialData(
        valuation=70.0, growth=60.0, profitability=80.0,
        momentum=55.0, sentiment=65.0, risk=40.0,
    )
    dumped = fd.model_dump()
    assert isinstance(dumped, dict)
    assert set(dumped) == {
        "valuation", "growth", "profitability", "momentum", "sentiment", "risk", "metric_cards",
    }
    assert dumped["metric_cards"] == []


def test_report_payload_nested_model_dump_recurses():
    payload = ReportPayload(
        sections=[ReportSection(heading="Thesis", body="strong")],
        financial_data=FinancialData(
            valuation=70.0, growth=60.0, profitability=80.0,
            momentum=55.0, sentiment=65.0, risk=40.0,
        ),
    )
    dumped = payload.model_dump()
    assert isinstance(dumped["sections"][0], dict)
    assert isinstance(dumped["financial_data"], dict)
    assert dumped["sections"][0]["heading"] == "Thesis"


def test_report_section_requires_heading_and_body():
    with pytest.raises(ValidationError):
        ReportSection(heading="only heading")  # body missing


# ---------------------------------------------------------------------------
# Task 3: Metrics aggregation + footer
# ---------------------------------------------------------------------------


def _sample_metrics():
    return [
        {"node": "news_analyst", "model": "gpt-oss:20b", "prompt_tokens": 100,
         "completion_tokens": 40, "latency_s": 1.5, "cost_usd": 0.002},
        {"node": "bull", "model": "gpt-oss:120b", "prompt_tokens": 200,
         "completion_tokens": 80, "latency_s": 3.0, "cost_usd": 0.01},
        {"node": "reporter", "model": "gpt-oss:20b", "prompt_tokens": 50,
         "completion_tokens": 20, "latency_s": 0.5, "cost_usd": 0.001},
    ]


def test_aggregate_metrics_sums_fields():
    agg = aggregate_metrics(_sample_metrics())
    assert agg["prompt_tokens"] == 350
    assert agg["completion_tokens"] == 140
    assert agg["total_tokens"] == 490
    assert round(agg["latency_s"], 2) == 5.0
    assert round(agg["cost_usd"], 4) == 0.013
    assert agg["node_count"] == 3


def test_aggregate_metrics_counts_distinct_node_labels_not_records():
    """Debate sub-turn records (research_debate/risk_debate) share one label each;
    'Nodes executed' must count distinct labels, not raw LLM-call records."""
    metrics = _sample_metrics() + [
        {"node": "research_debate", "model": "gpt-oss:120b", "prompt_tokens": 10,
         "completion_tokens": 5, "latency_s": 0.1, "cost_usd": 0.001},
        {"node": "research_debate", "model": "gpt-oss:120b", "prompt_tokens": 10,
         "completion_tokens": 5, "latency_s": 0.1, "cost_usd": 0.001},
        {"node": "risk_debate", "model": "gpt-oss:120b", "prompt_tokens": 10,
         "completion_tokens": 5, "latency_s": 0.1, "cost_usd": 0.001},
    ]
    agg = aggregate_metrics(metrics)
    # 3 distinct labels in _sample_metrics + research_debate + risk_debate = 5,
    # even though there are 6 records.
    assert agg["node_count"] == 5
    # token/cost sums still cover every record
    assert agg["prompt_tokens"] == 380


def test_aggregate_metrics_handles_empty():
    agg = aggregate_metrics([])
    assert agg["total_tokens"] == 0
    assert agg["cost_usd"] == 0.0
    assert agg["node_count"] == 0


def test_aggregate_metrics_tolerates_missing_keys():
    agg = aggregate_metrics([{"node": "x"}])  # no token/cost keys
    assert agg["total_tokens"] == 0
    assert agg["latency_s"] == 0.0


def test_render_metrics_footer_includes_aggregates_and_mode():
    footer = render_metrics_footer(_sample_metrics(), debate_mode="on")
    assert "Run Transparency" in footer
    assert "$0.013" in footer            # cost_usd
    assert "490" in footer               # total tokens
    assert "5.0" in footer or "5.00" in footer  # latency
    assert "on" in footer                # debate_mode
    assert "3" in footer                 # node count


def test_render_metrics_footer_empty_metrics():
    footer = render_metrics_footer([], debate_mode="off")
    assert "Run Transparency" in footer
    assert "off" in footer


# ---------------------------------------------------------------------------
# Task 4: Verdict header
# ---------------------------------------------------------------------------


def test_render_verdict_header_surfaces_action_score_ticker():
    header = render_verdict_header(
        ticker="AAPL",
        resolved_ticker="AAPL",
        investor_mode="Neutral",
        final_decision={"action": "BUY", "conviction": 0.82, "score": 78,
                        "rationale": "Strong fundamentals and momentum."},
        trade_proposal={"action": "HOLD", "conviction": 0.6, "score": 62, "rationale": "x"},
    )
    assert "AAPL" in header
    assert "BUY" in header
    assert "78" in header           # final score
    assert "0.82" in header         # conviction
    assert "Strong fundamentals" in header
    assert "Neutral" in header
    # transparency: the pre-risk proposal differing from final is noted
    assert "HOLD" in header
    assert "62" in header


def test_render_verdict_header_handles_missing_decision():
    header = render_verdict_header(
        ticker="TSLA", resolved_ticker="TSLA", investor_mode="Bullish",
        final_decision={}, trade_proposal={},
    )
    assert "TSLA" in header
    assert "HOLD" in header  # safe default action


# ---------------------------------------------------------------------------
# Task 5: Prompt + message builder
# ---------------------------------------------------------------------------


def _full_state():
    return {
        "ticker": "AAPL", "resolved_ticker": "AAPL", "investor_mode": "Neutral",
        "analyst_reports": {
            "news": {"summary": "Strong product cycle", "key_points": ["iPhone demand up"],
                     "data": {}, "confidence": 0.7, "citations": ["http://x"]},
            "fundamentals": {"summary": "Healthy margins", "key_points": ["FCF growth"],
                             "data": {"pe": 28}, "confidence": 0.6, "citations": []},
            "technicals": {"summary": "Uptrend", "key_points": ["RSI 60"],
                           "data": {"rsi": 60}, "confidence": 0.5, "citations": []},
        },
        "research_debate": {"bull_thesis": "Growth runway", "bear_thesis": "Valuation rich",
                            "facilitator_verdict": "Lean bull", "rounds": []},
        "trade_proposal": {"action": "BUY", "conviction": 0.7, "score": 70, "rationale": "momentum"},
        "risk_debate": {"conservative": "size down", "aggressive": "full size",
                        "arbiter_decision": "moderate size", "adjustments": ["trim 20%"], "rounds": []},
        "final_decision": {"action": "BUY", "conviction": 0.75, "score": 72,
                           "rationale": "Net favorable"},
        "run_metrics": [
            {"node": "reporter", "model": "gpt-oss:20b", "prompt_tokens": 10,
             "completion_tokens": 5, "latency_s": 0.2, "cost_usd": 0.0001},
        ],
    }


def test_build_report_messages_includes_state_facts():
    msgs = build_report_messages(_full_state())
    assert len(msgs) == 2
    assert msgs[0]["role"] == "system"
    assert msgs[0]["content"] == REPORTER_SYSTEM_PROMPT
    human = msgs[1]["content"]
    assert msgs[1]["role"] == "user"
    for needle in ["AAPL", "Strong product cycle", "Growth runway",
                   "Valuation rich", "Lean bull", "moderate size", "Net favorable"]:
        assert needle in human


def test_system_prompt_mentions_radar_and_sections():
    assert "financial_data" in REPORTER_SYSTEM_PROMPT
    assert "section" in REPORTER_SYSTEM_PROMPT.lower()
    assert "0..100" in REPORTER_SYSTEM_PROMPT or "0-100" in REPORTER_SYSTEM_PROMPT


# ---------------------------------------------------------------------------
# Task 6: Async reporter node (mocked LLM)
# ---------------------------------------------------------------------------


class _FakeStructured:
    def __init__(self, payload):
        self._payload = payload

    async def ainvoke(self, messages, config=None, **kwargs):
        # Fire CostTracker callbacks so per_node is populated.
        import time
        from types import SimpleNamespace
        callbacks = (config or {}).get("callbacks", []) or []
        rid = f"fake-{time.monotonic_ns()}"
        for cb in callbacks:
            if hasattr(cb, "on_llm_start"):
                cb.on_llm_start({}, ["<prompt>"], run_id=rid)
        response = SimpleNamespace(
            llm_output={
                "token_usage": {"prompt_tokens": 10, "completion_tokens": 5},
                "model_name": "fake-quick",
            }
        )
        for cb in callbacks:
            if hasattr(cb, "on_llm_end"):
                cb.on_llm_end(response, run_id=rid)
        return self._payload


class _FakeLLM:
    def __init__(self, payload):
        self._payload = payload

    def with_structured_output(self, schema, method=None):
        assert schema is ReportPayload
        return _FakeStructured(self._payload)


@pytest.fixture
def fake_payload():
    return ReportPayload(
        sections=[
            ReportSection(heading="Executive Summary", body="AAPL looks favorable."),
            ReportSection(heading="Risk Assessment", body="Valuation is a watch item."),
        ],
        financial_data=FinancialData(
            valuation=65.0, growth=72.0, profitability=80.0,
            momentum=58.0, sentiment=70.0, risk=55.0,
            metric_cards=[MetricCard(label="P/E", value="28"),
                          MetricCard(label="RSI", value="60")],
        ),
    )


@pytest.mark.asyncio
async def test_reporter_returns_report_and_financial_data(monkeypatch, fake_payload):
    monkeypatch.setattr(reporter_mod, "get_llm", lambda tier: _FakeLLM(fake_payload))
    state = _full_state()
    out = await reporter(state)

    assert set(out) >= {"final_report", "financial_data", "run_metrics"}

    report = out["final_report"]
    assert isinstance(report, str) and report.strip()
    assert "AAPL" in report
    assert "BUY" in report
    assert "72" in report
    assert "## Executive Summary" in report
    assert "AAPL looks favorable." in report
    assert "## Risk Assessment" in report
    assert "Run Transparency" in report
    assert "Debate mode" in report

    fd = out["financial_data"]
    assert isinstance(fd, dict)
    assert set(fd) == {"valuation", "growth", "profitability", "momentum",
                       "sentiment", "risk", "metric_cards"}
    assert fd["valuation"] == 65.0
    assert fd["metric_cards"][0] == {"label": "P/E", "value": "28"}


@pytest.mark.asyncio
async def test_reporter_appends_its_own_metric(monkeypatch, fake_payload):
    monkeypatch.setattr(reporter_mod, "get_llm", lambda tier: _FakeLLM(fake_payload))
    out = await reporter(_full_state())
    metrics = out["run_metrics"]
    assert isinstance(metrics, list)
    assert any(m["node"] == "reporter" for m in metrics)


@pytest.mark.asyncio
async def test_reporter_uses_quick_tier(monkeypatch, fake_payload):
    seen = {}

    def _capture(tier):
        seen["tier"] = tier
        return _FakeLLM(fake_payload)

    monkeypatch.setattr(reporter_mod, "get_llm", _capture)
    out = await reporter(_full_state())
    assert seen["tier"] == "quick"
    assert any(m["node"] == "reporter" for m in out["run_metrics"])


@pytest.mark.asyncio
async def test_reporter_reads_debate_mode_from_settings(monkeypatch, fake_payload):
    monkeypatch.setattr(reporter_mod, "get_llm", lambda tier: _FakeLLM(fake_payload))

    class _S:
        debate_mode = "off"

    monkeypatch.setattr(reporter_mod, "get_settings", lambda: _S())
    out = await reporter(_full_state())
    assert "| Debate mode | off |" in out["final_report"]


@pytest.mark.asyncio
async def test_reporter_explicit_debate_mode_overrides_settings(monkeypatch, fake_payload):
    """build_graph binds the per-run mode into the reporter; an explicit
    debate_mode kwarg must win over the settings default."""
    monkeypatch.setattr(reporter_mod, "get_llm", lambda tier: _FakeLLM(fake_payload))

    class _S:
        debate_mode = "on"

    monkeypatch.setattr(reporter_mod, "get_settings", lambda: _S())
    out = await reporter(_full_state(), debate_mode="off")
    assert "| Debate mode | off |" in out["final_report"]


@pytest.mark.asyncio
async def test_reporter_cache_hit_renders_cached_verdict_without_llm(monkeypatch):
    """On the verdict-cache short-circuit path (router -> reporter) the reporter
    renders deterministically from final_decision: no LLM call, a 'verdict cache'
    note in the body, a cache-hit footer row, and its zero-cost metric line."""

    def _llm_must_not_be_called(tier):
        raise AssertionError("reporter must not call the LLM on a cache hit")

    monkeypatch.setattr(reporter_mod, "get_llm", _llm_must_not_be_called)

    state = {
        "ticker": "AAPL",
        "resolved_ticker": "AAPL",
        "investor_mode": "Neutral",
        "model_plan": {"analysts": "quick", "cache_hit": True},
        "final_decision": {"action": "BUY", "conviction": 0.9, "score": 88,
                           "rationale": "cached: strong momentum"},
        "run_metrics": [
            {"node": "router", "model": "gpt-oss:20b", "prompt_tokens": 10,
             "completion_tokens": 5, "latency_s": 0.2, "cost_usd": 0.0001},
        ],
    }
    out = await reporter(state, debate_mode="on")

    report = out["final_report"]
    assert "AAPL" in report
    assert "BUY" in report and "88" in report          # cached decision in the header
    assert "verdict cache" in report                    # body explains the short-circuit
    assert "Run Transparency" in report                 # footer still rendered
    assert "Served from verdict cache | yes" in report  # footer notes the cache hit

    # No LLM call: financial_data degrades to neutral and metrics are zero-cost.
    assert out["financial_data"]["valuation"] == 50.0
    assert [m["node"] for m in out["run_metrics"]] == ["reporter"]
    assert out["run_metrics"][0]["cost_usd"] == 0.0


@pytest.mark.asyncio
async def test_reporter_degrades_gracefully_on_llm_failure(monkeypatch):
    """On LLM error, reporter still emits a minimal report with verdict + footer."""

    class _FailingStructured:
        async def ainvoke(self, messages, config=None, **kwargs):
            raise RuntimeError("model offline")

    class _FailingLLM:
        def with_structured_output(self, schema, method=None):
            return _FailingStructured()

    monkeypatch.setattr(reporter_mod, "get_llm", lambda tier: _FailingLLM())
    out = await reporter(_full_state())

    assert "final_report" in out
    assert "financial_data" in out
    assert "run_metrics" in out

    report = out["final_report"]
    assert "AAPL" in report          # ticker in header
    assert "BUY" in report           # action from final_decision
    assert "Run Transparency" in report  # footer still appended

    fd = out["financial_data"]
    assert set(fd) >= {"valuation", "growth", "profitability", "momentum", "sentiment", "risk"}
    # defaults to 50 on fallback
    assert fd["valuation"] == 50.0

import json

import pytest
from pydantic import ValidationError

from src.api.schemas import (
    TICKER_RE,
    AnalyzeRequest,
    done_payload,
    error_payload,
    node_complete_payload,
    node_start_payload,
    sse_event,
    start_payload,
    token_payload,
)


def test_analyze_request_defaults():
    r = AnalyzeRequest(ticker="AAPL")
    assert r.ticker == "AAPL"
    assert r.investor_mode == "Neutral"
    assert r.debate_mode is None  # use settings default


def test_analyze_request_uppercases_and_strips_ticker():
    r = AnalyzeRequest(ticker="  aapl ")
    assert r.ticker == "AAPL"


def test_analyze_request_rejects_bad_ticker():
    with pytest.raises(ValidationError):
        AnalyzeRequest(ticker="; DROP TABLE--")
    with pytest.raises(ValidationError):
        AnalyzeRequest(ticker="")
    with pytest.raises(ValidationError):
        AnalyzeRequest(ticker="A" * 25)


def test_analyze_request_rejects_bad_investor_mode():
    with pytest.raises(ValidationError):
        AnalyzeRequest(ticker="AAPL", investor_mode="YOLO")


def test_analyze_request_allows_dotted_international_ticker():
    assert AnalyzeRequest(ticker="RELIANCE.NS").ticker == "RELIANCE.NS"


def test_ticker_regex_anchored():
    assert TICKER_RE.fullmatch("BRK.B")
    assert not TICKER_RE.fullmatch("AAPL AAPL")


# WP-5 hardening: strict allowlist ^[A-Z0-9][A-Z0-9.\-]{0,14}$ after strip/upper.


@pytest.mark.parametrize(
    "junk",
    [
        "../etc",            # traversal
        "AAPL; DROP",        # injection-ish
        "\U0001f680",        # emoji
        "A" * 30,            # over-long
        "A" * 16,            # one past the 15-char cap
        "-AAPL",             # must start alphanumeric
        ".NS",               # ditto
        "AAPL\n",            # control chars survive strip? (\n is stripped -> ok)
    ],
)
def test_analyze_request_rejects_junk_tickers(junk):
    if junk == "AAPL\n":  # strip() normalizes trailing whitespace -> valid
        assert AnalyzeRequest(ticker=junk).ticker == "AAPL"
        return
    with pytest.raises(ValidationError):
        AnalyzeRequest(ticker=junk)


@pytest.mark.parametrize("ok", ["aapl", "BRK.B", "BRK-B", "0700.HK", "A", "A" * 15])
def test_analyze_request_accepts_allowlisted_tickers(ok):
    assert AnalyzeRequest(ticker=ok).ticker == ok.upper()


def test_analyze_request_rejects_bad_debate_mode():
    with pytest.raises(ValidationError):
        AnalyzeRequest(ticker="AAPL", debate_mode="maybe")
    assert AnalyzeRequest(ticker="AAPL", debate_mode="on").debate_mode == "on"
    assert AnalyzeRequest(ticker="AAPL", debate_mode="off").debate_mode == "off"
    assert AnalyzeRequest(ticker="AAPL", debate_mode=None).debate_mode is None


def test_sse_event_shape():
    ev = sse_event("node_complete", {"type": "node_complete", "run_id": "r1", "node": "router"})
    assert ev["event"] == "node_complete"
    payload = json.loads(ev["data"])
    assert payload["node"] == "router"
    assert payload["run_id"] == "r1"


def test_payload_builders_carry_run_id_and_type():
    assert start_payload("r1", "AAPL", "Neutral")["type"] == "start"
    assert node_start_payload("r1", "bull")["node"] == "bull"
    assert (
        node_complete_payload("r1", "router", {"resolved_ticker": "AAPL"})["delta"][
            "resolved_ticker"
        ]
        == "AAPL"
    )
    assert token_payload("r1", "bull", "hello")["text"] == "hello"
    assert error_payload("r1", "boom")["message"] == "boom"
    d = done_payload(
        "r1",
        final_report="# R",
        final_decision={"action": "HOLD"},
        run_metrics=[{"node": "router"}],
    )
    assert d["final_decision"]["action"] == "HOLD"
    assert d["run_metrics"][0]["node"] == "router"


def test_payloads_are_json_serializable():
    # done must survive json.dumps (recorder stores arbitrary deltas)
    d = done_payload("r1", final_report="x", final_decision={"a": 1}, run_metrics=[])
    json.dumps(d)

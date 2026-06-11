import json

from src.eval.harness import PairedResult
from src.eval.judge import JudgeVerdict
from src.eval.report import (
    PROXY_DISCLAIMER,
    aggregate,
    render_markdown,
    write_report,
)


def _paired(ticker, a_on, s_on, c_on, l_on, a_off, s_off, c_off, l_off):
    return PairedResult(
        ticker=ticker,
        decision_on={"action": a_on, "conviction": 0.6, "score": s_on, "rationale": "x"},
        decision_off={"action": a_off, "conviction": 0.6, "score": s_off, "rationale": "y"},
        metrics_on=[{"node": "n", "prompt_tokens": 100, "completion_tokens": 50,
                     "latency_s": l_on, "cost_usd": c_on}],
        metrics_off=[{"node": "n", "prompt_tokens": 40, "completion_tokens": 20,
                      "latency_s": l_off, "cost_usd": c_off}],
    )


def _fixture():
    pairs = [
        _paired("AAPL", "BUY", 80, 0.06, 4.0, "HOLD", 55, 0.02, 1.5),
        _paired("MSFT", "BUY", 70, 0.04, 3.0, "BUY", 65, 0.02, 1.5),
    ]
    verdicts = {
        "AAPL": JudgeVerdict(preferred="on", agreement=False, reasoning="r", confidence=0.7),
        "MSFT": JudgeVerdict(preferred="off", agreement=True, reasoning="r", confidence=0.6),
    }
    return pairs, verdicts


def test_aggregate_action_agreement_rate():
    pairs, verdicts = _fixture()
    agg = aggregate(pairs, verdicts)
    # AAPL actions differ (BUY vs HOLD); MSFT match (BUY vs BUY) => 1/2 = 0.5
    assert agg["action_agreement_rate"] == 0.5


def test_aggregate_judge_preference_rate():
    pairs, verdicts = _fixture()
    agg = aggregate(pairs, verdicts)
    # judge preferred "on" once of two => 0.5
    assert agg["judge_prefers_on_rate"] == 0.5


def test_aggregate_mean_score_delta():
    pairs, verdicts = _fixture()
    agg = aggregate(pairs, verdicts)
    # (80-55) + (70-65) = 30; mean = 15.0
    assert agg["mean_score_delta_on_minus_off"] == 15.0


def test_aggregate_mean_cost_and_latency_delta():
    pairs, verdicts = _fixture()
    agg = aggregate(pairs, verdicts)
    # cost delta: (0.06-0.02)+(0.04-0.02) = 0.06; mean = 0.03
    assert agg["mean_cost_delta_on_minus_off"] == 0.03
    # latency delta: (4.0-1.5)+(3.0-1.5)=4.0; mean = 2.0
    assert agg["mean_latency_delta_on_minus_off"] == 2.0


def test_aggregate_reports_spread():
    pairs, verdicts = _fixture()
    agg = aggregate(pairs, verdicts)
    # score deltas are [25, 5]; population stdev = 10.0
    assert agg["score_delta_stdev"] == 10.0


def test_aggregate_includes_judge_cost():
    """The judge's own LLM spend is part of the eval's honest cost accounting."""
    pairs, verdicts = _fixture()
    agg = aggregate(pairs, verdicts)
    assert agg["judge_cost_usd"] == 0.0  # defaults when no totals supplied
    assert agg["judge_tokens"] == 0

    judge_totals = {"prompt_tokens": 100, "completion_tokens": 50,
                    "latency_s": 1.0, "cost_usd": 0.123456, "per_node": []}
    agg2 = aggregate(pairs, verdicts, judge_totals=judge_totals)
    assert agg2["judge_cost_usd"] == 0.123456
    assert agg2["judge_tokens"] == 150


def test_render_markdown_includes_judge_cost_row():
    pairs, verdicts = _fixture()
    judge_totals = {"prompt_tokens": 80, "completion_tokens": 20,
                    "latency_s": 1.0, "cost_usd": 0.05, "per_node": []}
    md = render_markdown(aggregate(pairs, verdicts, judge_totals=judge_totals),
                         pairs, verdicts, label="demo")
    assert "Judge cost" in md
    assert "0.05" in md
    assert "100" in md  # judge tokens


def test_render_markdown_includes_proxy_disclaimer():
    pairs, verdicts = _fixture()
    md = render_markdown(aggregate(pairs, verdicts), pairs, verdicts, label="demo")
    # HONESTY: the metric must be labeled a proxy, not P&L
    assert PROXY_DISCLAIMER in md
    assert "AAPL" in md and "MSFT" in md


def test_write_report_uses_label_not_wallclock(tmp_path):
    pairs, verdicts = _fixture()
    md_path, json_path = write_report(pairs, verdicts, label="demo", out_dir=str(tmp_path))
    assert md_path.name == "report-demo.md"
    assert json_path.name == "report-demo.json"
    assert PROXY_DISCLAIMER in md_path.read_text(encoding="utf-8")
    data = json.loads(json_path.read_text(encoding="utf-8"))
    assert data["disclaimer"] == PROXY_DISCLAIMER
    assert data["summary"]["action_agreement_rate"] == 0.5
    assert len(data["per_ticker"]) == 2

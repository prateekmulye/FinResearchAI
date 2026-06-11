# tests/test_eval_run.py
"""WP-10 eval-run wiring: ``run_eval`` persists the A/B result to the warehouse
(label + aggregate summary + per-ticker rows) AFTER writing the file reports,
and keeps working exactly as before when the warehouse is disabled.

``run_ab`` and ``judge_decision`` are monkeypatched on src.eval.run with the
same canned shapes used by tests/test_eval_{harness,report}.py — no graph, no
LLM, no network.
"""
from __future__ import annotations

import json

from sqlalchemy import select

from src.eval import run as run_mod
from src.eval.harness import PairedResult
from src.eval.judge import JudgeVerdict
from src.eval.report import _per_ticker_rows, aggregate
from src.eval.run import run_eval
from src.warehouse.db import session_scope
from src.warehouse.models import EvalResult

_PAIRS = [
    PairedResult(
        ticker="AAPL",
        decision_on={"action": "BUY", "conviction": 0.6, "score": 80, "rationale": "x"},
        decision_off={"action": "HOLD", "conviction": 0.6, "score": 55, "rationale": "y"},
        metrics_on=[{"node": "n", "prompt_tokens": 100, "completion_tokens": 50,
                     "latency_s": 4.0, "cost_usd": 0.06}],
        metrics_off=[{"node": "n", "prompt_tokens": 40, "completion_tokens": 20,
                      "latency_s": 1.5, "cost_usd": 0.02}],
    ),
    PairedResult(
        ticker="MSFT",
        decision_on={"action": "BUY", "conviction": 0.6, "score": 70, "rationale": "x"},
        decision_off={"action": "BUY", "conviction": 0.6, "score": 65, "rationale": "y"},
        metrics_on=[{"node": "n", "prompt_tokens": 100, "completion_tokens": 50,
                     "latency_s": 3.0, "cost_usd": 0.04}],
        metrics_off=[{"node": "n", "prompt_tokens": 40, "completion_tokens": 20,
                      "latency_s": 1.5, "cost_usd": 0.02}],
    ),
]

_VERDICTS = {
    "AAPL": JudgeVerdict(preferred="on", agreement=False, reasoning="r", confidence=0.7),
    "MSFT": JudgeVerdict(preferred="off", agreement=True, reasoning="r", confidence=0.6),
}


def _patch_eval_seams(monkeypatch) -> None:
    async def fake_run_ab(tickers, *, investor_mode="Neutral", concurrency=3):
        assert tickers == ["AAPL", "MSFT"]  # loaded from the tickers file
        return list(_PAIRS)

    async def fake_judge(*, ticker, context, decision_on, decision_off, tracker=None):
        return _VERDICTS[ticker]

    monkeypatch.setattr(run_mod, "run_ab", fake_run_ab)
    monkeypatch.setattr(run_mod, "judge_decision", fake_judge)


def _write_tickers(tmp_path) -> str:
    path = tmp_path / "tickers.json"
    path.write_text(
        json.dumps({"tickers": [{"ticker": "AAPL"}, {"ticker": "MSFT"}]}),
        encoding="utf-8",
    )
    return str(path)


async def test_run_eval_persists_summary_and_pairs_to_warehouse(
    sqlite_warehouse, monkeypatch, tmp_path
):
    _patch_eval_seams(monkeypatch)
    await run_eval(_write_tickers(tmp_path), "wp10", 2, str(tmp_path))

    async with session_scope() as session:
        row = (await session.execute(select(EvalResult))).scalar_one()
    assert row.label == "wp10"
    assert row.summary == aggregate(_PAIRS, _VERDICTS)
    assert row.pairs == _per_ticker_rows(_PAIRS, _VERDICTS)

    # The persisted pairs ARE the dashboard rows: same shape as the JSON report.
    report = json.loads((tmp_path / "report-wp10.json").read_text(encoding="utf-8"))
    assert row.pairs == report["per_ticker"]
    assert row.summary == report["summary"]
    first = row.pairs[0]
    for key in (
        "ticker", "action_on", "action_off", "score_on", "score_off",
        "cost_on", "cost_off", "latency_on", "latency_off",
        "tokens_on", "tokens_off", "judge_preferred", "judge_agreement",
        "judge_confidence",
    ):
        assert key in first, f"dashboard row missing {key}"
    assert first["ticker"] == "AAPL"
    assert first["judge_preferred"] == "on"


async def test_run_eval_one_judge_failure_skips_ticker_and_completes(
    monkeypatch, tmp_path, caplog
):
    """One judge exception must not kill the batch: the failed ticker lands unjudged
    (judge_* fields None, n_judged excludes it) and both reports are still written."""

    async def fake_run_ab(tickers, *, investor_mode="Neutral", concurrency=3):
        return list(_PAIRS)

    async def fake_judge(*, ticker, context, decision_on, decision_off, **kwargs):
        if ticker == "AAPL":
            raise RuntimeError("judge model offline")
        return _VERDICTS[ticker]

    monkeypatch.setattr(run_mod, "run_ab", fake_run_ab)
    monkeypatch.setattr(run_mod, "judge_decision", fake_judge)

    with caplog.at_level("WARNING"):
        md_path = await run_eval(_write_tickers(tmp_path), "wp14", 2, str(tmp_path))

    assert md_path.exists()
    report = json.loads((tmp_path / "report-wp14.json").read_text(encoding="utf-8"))
    assert report["summary"]["n_tickers"] == 2
    assert report["summary"]["n_judged"] == 1  # AAPL unjudged, MSFT judged
    rows = {r["ticker"]: r for r in report["per_ticker"]}
    assert rows["AAPL"]["judge_preferred"] is None
    assert rows["MSFT"]["judge_preferred"] == "off"
    failures = [r for r in caplog.records if "judge failed" in r.getMessage()]
    assert failures, "expected a judge-failure degrade warning"
    assert failures[0].exc_info is not None


async def test_run_eval_surfaces_judge_cost_in_summary(monkeypatch, tmp_path):
    """The judge's shared CostTracker totals land in the summary
    (judge_cost_usd / judge_tokens) and in the markdown report table."""
    from types import SimpleNamespace

    async def fake_run_ab(tickers, *, investor_mode="Neutral", concurrency=3):
        return list(_PAIRS)

    async def fake_judge(*, ticker, context, decision_on, decision_off, tracker=None):
        # Simulate the LLM-call cost the real judge_decision records on the
        # shared tracker run_eval threads through.
        assert tracker is not None, "run_eval must pass its shared judge tracker"
        rid = f"judge-{ticker}"
        tracker.on_llm_start({}, ["<p>"], run_id=rid)
        tracker.on_llm_end(
            SimpleNamespace(
                llm_output={
                    "token_usage": {"prompt_tokens": 100, "completion_tokens": 50},
                    "model_name": "fake-deep",
                }
            ),
            run_id=rid,
        )
        return _VERDICTS[ticker]

    monkeypatch.setattr(run_mod, "run_ab", fake_run_ab)
    monkeypatch.setattr(run_mod, "judge_decision", fake_judge)

    await run_eval(_write_tickers(tmp_path), "wp14cost", 2, str(tmp_path))

    report = json.loads((tmp_path / "report-wp14cost.json").read_text(encoding="utf-8"))
    assert report["summary"]["judge_tokens"] == 300  # 150 per ticker x 2 tickers
    assert report["summary"]["judge_cost_usd"] == 0.0  # fake-deep has no pricing entry
    md = (tmp_path / "report-wp14cost.md").read_text(encoding="utf-8")
    assert "Judge cost" in md


async def test_run_eval_disabled_warehouse_still_writes_reports(monkeypatch, tmp_path):
    # env_isolation (autouse) scrubbed DATABASE_URL -> warehouse disabled.
    _patch_eval_seams(monkeypatch)
    md_path = await run_eval(_write_tickers(tmp_path), "wp10", 2, str(tmp_path))

    # File outputs unchanged and the run completes without a warehouse.
    assert md_path == tmp_path / "report-wp10.md"
    assert md_path.exists()
    assert (tmp_path / "report-wp10.json").exists()


async def test_run_eval_persistence_failure_never_breaks_the_run(
    sqlite_warehouse, monkeypatch, tmp_path, caplog
):
    """A dead warehouse mid-persist degrades to a WARNING; reports still land."""
    from src.warehouse import ingest as ingest_mod

    def _boom():
        raise RuntimeError("db down")

    _patch_eval_seams(monkeypatch)
    monkeypatch.setattr(ingest_mod, "session_scope", _boom)
    with caplog.at_level("WARNING"):
        md_path = await run_eval(_write_tickers(tmp_path), "wp10", 2, str(tmp_path))
    assert md_path.exists()
    assert any("record_eval_result" in r.message for r in caplog.records)

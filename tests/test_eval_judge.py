import pytest

from src.eval import judge as judge_mod
from src.eval.judge import JudgeVerdict, _RawJudgeVerdict, judge_decision


class _FakeStructured:
    def __init__(self, verdict):
        self._verdict = verdict

    async def ainvoke(self, messages, config=None):
        return self._verdict


class _FakeLLM:
    def __init__(self, verdict):
        self._verdict = verdict
        self.last_method = None

    def with_structured_output(self, schema, method=None):
        self.last_method = method
        assert schema is _RawJudgeVerdict
        return _FakeStructured(self._verdict)


def test_judge_verdict_schema_validates():
    v = JudgeVerdict(preferred="on", agreement=True, reasoning="debate added nuance",
                     confidence=0.7)
    assert v.preferred == "on"
    assert v.model_dump()["agreement"] is True


def test_judge_verdict_rejects_bad_preferred():
    from pydantic import ValidationError
    with pytest.raises(ValidationError):
        JudgeVerdict(preferred="maybe", agreement=False, reasoning="x", confidence=0.5)


@pytest.mark.asyncio
async def test_judge_decision_maps_llm_output(monkeypatch):
    canned = _RawJudgeVerdict(preferred_label="B", agreement=False,
                              reasoning="single-pass was crisper", confidence=0.55)
    fake = _FakeLLM(canned)
    monkeypatch.setattr(judge_mod, "get_llm", lambda tier: fake)

    result = await judge_decision(
        ticker="AAPL",
        context="news + fundamentals summary",
        decision_on={"action": "BUY", "score": 80, "rationale": "growth"},
        decision_off={"action": "HOLD", "score": 55, "rationale": "valuation"},
    )
    assert isinstance(result, JudgeVerdict)
    assert result.preferred == "off"  # label "B" maps to pipeline "off"
    assert result.agreement is False
    # default structured-output method is function_calling (COORDINATION §2)
    assert fake.last_method == "function_calling"

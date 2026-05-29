# tests/test_factory.py
import pytest
from langchain_openai import ChatOpenAI
from src.llm import factory
from src.config import settings as settings_mod


@pytest.fixture(autouse=True)
def _clear_caches(monkeypatch):
    # Force a deterministic Settings and clear memoization between tests.
    settings_mod.get_settings.cache_clear()
    factory.get_llm.cache_clear()
    monkeypatch.setenv("OLLAMA_API_KEY", "unit-test-key")
    monkeypatch.setenv("QUICK_MODEL", "q-model")
    monkeypatch.setenv("DEEP_MODEL", "d-model")
    # Neutralize models.yaml so env-provided model names are authoritative in this test.
    monkeypatch.setattr(settings_mod, "load_model_tiers", lambda *a, **k: {})
    yield
    settings_mod.get_settings.cache_clear()
    factory.get_llm.cache_clear()


def test_get_llm_quick_tier():
    llm = factory.get_llm("quick")
    assert isinstance(llm, ChatOpenAI)
    assert llm.model_name == "q-model"


def test_get_llm_deep_tier():
    assert factory.get_llm("deep").model_name == "d-model"


def test_get_llm_is_cached_singleton():
    assert factory.get_llm("quick") is factory.get_llm("quick")


def test_get_llm_bad_tier_raises():
    with pytest.raises(ValueError, match="unknown tier"):
        factory.get_llm("medium")

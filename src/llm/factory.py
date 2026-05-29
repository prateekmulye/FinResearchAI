# src/llm/factory.py
from __future__ import annotations

from functools import lru_cache

from langchain_openai import ChatOpenAI

from src.config.settings import get_settings

# Structured-output method constant — all WPs import this rather than hardcoding the string.
# If an Ollama model lacks tool calling, flip to "json_schema" here in one place.
# WP nodes MUST pass this explicitly: llm.with_structured_output(Schema, method=STRUCT_METHOD).
# ChatOpenAI's own default is "json_schema" — relying on the default bypasses this knob.
STRUCT_METHOD = "function_calling"


@lru_cache(maxsize=None)
def get_llm(tier: str) -> ChatOpenAI:
    """Return a cached ChatOpenAI pointed at the configured provider for the given tier.

    tier: "quick" (retrieval/summary/formatting) or "deep" (debate/verdict/arbiter).
    Cached per tier; callers that reload settings via get_settings.cache_clear() must also call get_llm.cache_clear().
    """
    s = get_settings()
    if tier == "quick":
        model, temperature = s.quick_model, s.quick_temperature
    elif tier == "deep":
        model, temperature = s.deep_model, s.deep_temperature
    else:
        raise ValueError(f"unknown tier: {tier!r} (expected 'quick' or 'deep')")

    return ChatOpenAI(
        model=model,
        base_url=s.llm_base_url,
        api_key=s.ollama_api_key or "not-set",
        temperature=temperature,
        timeout=120,
        max_retries=2,
    )

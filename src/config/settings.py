# src/config/settings.py
from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Any, Literal

import yaml
from pydantic_settings import BaseSettings, SettingsConfigDict

_MODELS_YAML = Path(__file__).parent / "models.yaml"


def load_model_tiers(path: Path = _MODELS_YAML) -> dict[str, dict[str, Any]]:
    """Load the tier->{model,temperature} mapping. Returns {} if file absent."""
    if not path.exists():
        return {}
    with path.open(encoding="utf-8") as f:
        return yaml.safe_load(f) or {}


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env", env_file_encoding="utf-8", extra="ignore", case_sensitive=False
    )

    # LLM provider (Ollama Cloud by default; swappable)
    llm_provider: str = "ollama_cloud"
    llm_base_url: str = "https://ollama.com/v1"
    ollama_api_key: str = ""

    # Web research
    firecrawl_api_key: str = ""

    # Model tiers (env overrides win over models.yaml)
    quick_model: str = "gpt-oss:20b"
    deep_model: str = "gpt-oss:120b"
    quick_temperature: float = 0.3
    deep_temperature: float = 0.5

    # Debate
    research_debate_rounds: int = 1
    risk_debate_rounds: int = 1
    debate_mode: Literal["on", "off"] = "on"

    # Memory (verdict cache is warehouse-backed; embeddings stay local/fastembed)
    embedding_model: str = "BAAI/bge-small-en-v1.5"

    # Observability
    runs_dir: str = "runs"
    langsmith_enabled: bool = False

    # Warehouse (WP-1, additive): Postgres+pgvector via SQLAlchemy async.
    # Unset DATABASE_URL means the warehouse subsystem is disabled (guarded opt-in).
    database_url: str | None = None
    db_echo: bool = False

    # Collector (WP-3, additive): in-process scheduled refresh of watched
    # instruments (prices + fundamentals). Off by default; only ever started
    # when the warehouse is enabled too.
    collector_enabled: bool = False
    collector_interval_hours: int = 24

    def apply_model_yaml(self, tiers: dict[str, dict[str, Any]] | None = None) -> "Settings":
        """Fill model/temperature from models.yaml ONLY where env didn't override."""
        tiers = tiers if tiers is not None else load_model_tiers()
        if "quick" in tiers:
            if "quick_model" not in self.model_fields_set:
                self.quick_model = tiers["quick"].get("model", self.quick_model)
            if "quick_temperature" not in self.model_fields_set:
                self.quick_temperature = tiers["quick"].get("temperature", self.quick_temperature)
        if "deep" in tiers:
            if "deep_model" not in self.model_fields_set:
                self.deep_model = tiers["deep"].get("model", self.deep_model)
            if "deep_temperature" not in self.model_fields_set:
                self.deep_temperature = tiers["deep"].get("temperature", self.deep_temperature)
        return self


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings().apply_model_yaml()

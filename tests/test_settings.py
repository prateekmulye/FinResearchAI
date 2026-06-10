# tests/test_settings.py
import textwrap
from src.config.settings import Settings, load_model_tiers


def test_load_model_tiers_reads_yaml(tmp_path):
    p = tmp_path / "models.yaml"
    p.write_text(textwrap.dedent("""
        quick:
          model: "m-quick"
          temperature: 0.1
        deep:
          model: "m-deep"
          temperature: 0.9
    """))
    tiers = load_model_tiers(p)
    assert tiers["quick"]["model"] == "m-quick"
    assert tiers["deep"]["temperature"] == 0.9


# COORDINATION §1 frozen Settings fields. A rename/removal here is a coordination
# event that breaks downstream WPs, so assert the full set explicitly.
# WP-1 (flagship elevation, spec-sanctioned ADDITIVE change): database_url + db_echo.
# WP-2 (spec-sanctioned REMOVAL): chroma_dir is gone with the Chroma backend.
# WP-3 (ADDITIVE): collector_enabled + collector_interval_hours (scheduled collector).
# WP-5 (ADDITIVE): admin_token + demo daily caps + fake_llm (APP_FAKE_LLM demo mode).
_CONTRACT_FIELDS = {
    "llm_provider", "llm_base_url", "ollama_api_key", "firecrawl_api_key",
    "quick_model", "deep_model", "quick_temperature", "deep_temperature",
    "research_debate_rounds", "risk_debate_rounds", "debate_mode",
    "embedding_model", "runs_dir", "langsmith_enabled",
    "database_url", "db_echo",
    "collector_enabled", "collector_interval_hours",
    "admin_token", "demo_runs_per_ip_per_day", "demo_runs_global_per_day", "fake_llm",
}


def test_settings_exposes_all_contract_fields(monkeypatch):
    for k in ("OLLAMA_API_KEY", "FIRECRAWL_API_KEY", "QUICK_MODEL", "DEEP_MODEL"):
        monkeypatch.delenv(k, raising=False)
    s = Settings(_env_file=None)
    missing = _CONTRACT_FIELDS - set(type(s).model_fields)
    assert not missing, f"Settings dropped frozen contract fields: {missing}"
    # Spot-check contract defaults that downstream WPs rely on.
    assert s.llm_provider == "ollama_cloud"
    assert s.debate_mode == "on"
    assert s.embedding_model == "BAAI/bge-small-en-v1.5"
    # WP-2: the Chroma backend (and its chroma_dir setting) is gone.
    assert "chroma_dir" not in type(s).model_fields
    assert s.runs_dir == "runs"
    assert s.langsmith_enabled is False
    # WP-1 warehouse fields: disabled by default (no DATABASE_URL -> warehouse off).
    assert s.database_url is None
    assert s.db_echo is False
    # WP-3 collector fields: opt-in, daily by default.
    assert s.collector_enabled is False
    assert s.collector_interval_hours == 24
    # WP-5 demo-guard fields: no admin token, conservative daily caps, fake mode off.
    assert s.admin_token is None
    assert s.demo_runs_per_ip_per_day == 3
    assert s.demo_runs_global_per_day == 25
    assert s.fake_llm is False


def test_settings_wp5_reads_env(monkeypatch):
    monkeypatch.setenv("ADMIN_TOKEN", "sekrit")
    monkeypatch.setenv("DEMO_RUNS_PER_IP_PER_DAY", "7")
    monkeypatch.setenv("DEMO_RUNS_GLOBAL_PER_DAY", "99")
    monkeypatch.setenv("APP_FAKE_LLM", "1")
    s = Settings(_env_file=None)
    assert s.admin_token == "sekrit"
    assert s.demo_runs_per_ip_per_day == 7
    assert s.demo_runs_global_per_day == 99
    assert s.fake_llm is True


def test_settings_fake_llm_env_var_is_app_prefixed(monkeypatch):
    # The flag's env var is APP_FAKE_LLM (the constructor still accepts fake_llm=).
    monkeypatch.setenv("APP_FAKE_LLM", "true")
    assert Settings(_env_file=None).fake_llm is True
    monkeypatch.delenv("APP_FAKE_LLM")
    assert Settings(_env_file=None).fake_llm is False
    assert Settings(_env_file=None, fake_llm=True).fake_llm is True


def test_settings_collector_reads_env(monkeypatch):
    monkeypatch.setenv("COLLECTOR_ENABLED", "true")
    monkeypatch.setenv("COLLECTOR_INTERVAL_HOURS", "6")
    s = Settings(_env_file=None)
    assert s.collector_enabled is True
    assert s.collector_interval_hours == 6


def test_settings_defaults_without_env(monkeypatch):
    # Ensure no env bleed-through from a real .env
    for k in ["OLLAMA_API_KEY", "LLM_BASE_URL", "QUICK_MODEL", "DEEP_MODEL"]:
        monkeypatch.delenv(k, raising=False)
    s = Settings(_env_file=None)
    assert s.llm_base_url == "https://ollama.com/v1"
    assert s.debate_mode == "on"
    assert s.research_debate_rounds == 1


def test_settings_reads_env(monkeypatch):
    monkeypatch.setenv("OLLAMA_API_KEY", "test-key-123")
    monkeypatch.setenv("QUICK_MODEL", "override-quick")
    s = Settings(_env_file=None)
    assert s.ollama_api_key == "test-key-123"
    assert s.quick_model == "override-quick"


def test_apply_model_yaml_env_wins_over_yaml(tmp_path, monkeypatch):
    monkeypatch.setenv("QUICK_MODEL", "env-model")
    p = tmp_path / "m.yaml"
    p.write_text("quick:\n  model: yaml-model\n  temperature: 0.1\n")
    s = Settings(_env_file=None)
    s.apply_model_yaml(load_model_tiers(p))
    assert s.quick_model == "env-model"       # env wins
    assert s.quick_temperature == 0.1          # yaml fills the unset field

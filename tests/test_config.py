"""Tests for app.config: defaults, provider helpers, configured_providers."""
from app import config


# Every env var config reads. We clear these so tests don't inherit a real .env.
ENV_VARS = [
    "LLM_PROVIDER",
    "OPENAI_API_KEY",
    "OPENROUTER_API_KEY",
    "MODEL",
    "TAVILY_API_KEY",
    "NEWSAPI_KEY",
    "MAX_ITERATIONS",
    "DB_PATH",
]


def _clear_env(monkeypatch):
    for var in ENV_VARS:
        monkeypatch.delenv(var, raising=False)


def test_defaults_when_env_unset(monkeypatch):
    _clear_env(monkeypatch)
    config.reload_settings()
    s = config.settings
    assert s.llm_provider == "openai"
    assert s.model == "gpt-4o-mini"
    assert s.max_iterations == 2
    assert s.db_path == "research.db"
    assert s.openai_api_key is None
    assert s.openrouter_api_key is None
    assert s.tavily_api_key is None
    assert s.newsapi_key is None


def test_env_overrides_defaults(monkeypatch):
    _clear_env(monkeypatch)
    monkeypatch.setenv("LLM_PROVIDER", "openrouter")
    monkeypatch.setenv("MODEL", "anthropic/claude-3.5-sonnet")
    monkeypatch.setenv("MAX_ITERATIONS", "5")
    monkeypatch.setenv("DB_PATH", "custom.db")
    config.reload_settings()
    s = config.settings
    assert s.llm_provider == "openrouter"
    assert s.model == "anthropic/claude-3.5-sonnet"
    assert s.max_iterations == 5
    assert s.db_path == "custom.db"


def test_configured_providers_reflects_keys(monkeypatch):
    _clear_env(monkeypatch)
    config.reload_settings()
    assert config.configured_providers() == []

    monkeypatch.setenv("OPENAI_API_KEY", "sk-openai-test")
    config.reload_settings()
    assert config.configured_providers() == ["openai"]

    monkeypatch.setenv("OPENROUTER_API_KEY", "sk-or-test")
    config.reload_settings()
    assert config.configured_providers() == ["openai", "openrouter"]

    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    config.reload_settings()
    assert config.configured_providers() == ["openrouter"]


def test_provider_base_url():
    assert config.provider_base_url("openrouter") == "https://openrouter.ai/api/v1"
    assert config.provider_base_url("openai") is None
    assert config.provider_base_url("something-else") is None


def test_provider_api_key(monkeypatch):
    _clear_env(monkeypatch)
    monkeypatch.setenv("OPENAI_API_KEY", "sk-a")
    monkeypatch.setenv("OPENROUTER_API_KEY", "sk-b")
    config.reload_settings()
    assert config.provider_api_key("openai") == "sk-a"
    assert config.provider_api_key("openrouter") == "sk-b"
    assert config.provider_api_key("unknown") is None

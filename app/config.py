"""Environment-driven settings and LLM-provider helpers.

A single module-level ``settings`` object is populated from the environment
(after loading a local ``.env``). ``reload_settings()`` re-reads the environment
into that same object in place, which keeps every ``from app.config import
settings`` reference valid while still being test-friendly.
"""
from __future__ import annotations

import os
from dataclasses import dataclass, fields

from dotenv import load_dotenv

# Load a local .env (if present) into os.environ. Existing env vars win.
load_dotenv()

OPENROUTER_BASE_URL = "https://openrouter.ai/api/v1"


@dataclass
class Settings:
    llm_provider: str = "openai"
    openai_api_key: str | None = None
    openrouter_api_key: str | None = None
    model: str = "gpt-4o-mini"
    tavily_api_key: str | None = None
    newsapi_key: str | None = None
    max_iterations: int = 2
    db_path: str = "research.db"


def _load() -> Settings:
    """Build a Settings instance from the current os.environ."""
    return Settings(
        llm_provider=os.environ.get("LLM_PROVIDER", "openai"),
        openai_api_key=os.environ.get("OPENAI_API_KEY") or None,
        openrouter_api_key=os.environ.get("OPENROUTER_API_KEY") or None,
        model=os.environ.get("MODEL", "gpt-4o-mini"),
        tavily_api_key=os.environ.get("TAVILY_API_KEY") or None,
        newsapi_key=os.environ.get("NEWSAPI_KEY") or None,
        max_iterations=int(os.environ.get("MAX_ITERATIONS", "2")),
        db_path=os.environ.get("DB_PATH", "research.db"),
    )


# The single shared settings object every other module imports.
settings = _load()


def reload_settings() -> Settings:
    """Re-read os.environ into the existing ``settings`` object, in place."""
    fresh = _load()
    for f in fields(settings):
        setattr(settings, f.name, getattr(fresh, f.name))
    return settings


def provider_base_url(provider: str) -> str | None:
    """OpenRouter needs a custom base URL; OpenAI uses the SDK default (None)."""
    if provider == "openrouter":
        return OPENROUTER_BASE_URL
    return None


def provider_api_key(provider: str) -> str | None:
    """Return the API key configured for ``provider`` (or None)."""
    if provider == "openai":
        return settings.openai_api_key
    if provider == "openrouter":
        return settings.openrouter_api_key
    return None


def configured_providers() -> list[str]:
    """Providers whose API key is set, in stable order."""
    return [p for p in ("openai", "openrouter") if provider_api_key(p)]

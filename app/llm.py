# app/llm.py
from __future__ import annotations

from langchain_openai import ChatOpenAI

from app.config import settings, provider_api_key, provider_base_url


def _supports_temperature(model: str) -> bool:
    """Whether a model accepts a custom ``temperature``.

    OpenAI's ``*-search-preview`` models and the o-series reasoning models
    (o1/o3/o4) reject a custom temperature and only accept their fixed default;
    passing one returns HTTP 400. For those we omit the parameter entirely.
    """
    m = (model or "").lower()
    if "search-preview" in m:
        return False
    base = m.split("/")[-1]  # strip any "openai/" style provider prefix
    for family in ("o1", "o3", "o4"):
        if base == family or base.startswith(family + "-"):
            return False
    return True


def get_llm(
    provider: str | None = None,
    model: str | None = None,
    api_key: str | None = None,
) -> ChatOpenAI:
    """Build a provider-agnostic ChatOpenAI client.

    provider defaults to settings.llm_provider; model defaults to settings.model.
    An explicit ``api_key`` (e.g. entered in the UI) overrides the configured
    ``.env`` key for this call; otherwise the key is resolved from config.
    The base URL is resolved from config helpers so the same OpenAI-compatible
    client can talk to OpenAI or OpenRouter. ``temperature`` is set only for
    models that accept it. Constructing this performs no I/O.
    """
    p = provider or settings.llm_provider
    m = model or settings.model
    kwargs = {
        "model": m,
        "api_key": api_key or provider_api_key(p),
        "base_url": provider_base_url(p),
    }
    if _supports_temperature(m):
        kwargs["temperature"] = 0.2
    return ChatOpenAI(**kwargs)

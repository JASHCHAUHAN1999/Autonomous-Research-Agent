# app/models.py
from __future__ import annotations

import time
from dataclasses import dataclass

import httpx

from app.config import configured_providers, provider_api_key


@dataclass
class ModelInfo:
    id: str
    name: str
    free: bool
    pricing: dict | None = None
    context_length: int | None = None


# --- Simple in-memory TTL cache ------------------------------------------------
# Keyed by provider name; value is (timestamp, list[ModelInfo]).
# Only results fetched with the configured (.env) key are cached. Requests that
# carry an explicit override key skip the cache entirely so an override never
# poisons — and is never served from — the shared configured-key cache.
_CACHE_TTL: float = 300.0
_cache: dict[str, tuple[float, list[ModelInfo]]] = {}


def _cache_get(provider: str) -> list[ModelInfo] | None:
    entry = _cache.get(provider)
    if entry is None:
        return None
    ts, models = entry
    if time.time() - ts > _CACHE_TTL:
        _cache.pop(provider, None)
        return None
    return models


def _cache_set(provider: str, models: list[ModelInfo]) -> None:
    _cache[provider] = (time.time(), models)


def list_providers() -> list[str]:
    return configured_providers()


def _auth_headers(provider: str, api_key: str | None = None) -> dict[str, str]:
    key = api_key or provider_api_key(provider)
    if key:
        return {"Authorization": f"Bearer {key}"}
    return {}


async def _fetch_openrouter(api_key: str | None = None) -> list[ModelInfo]:
    url = "https://openrouter.ai/api/v1/models"
    async with httpx.AsyncClient(timeout=30.0) as client:
        resp = await client.get(url, headers=_auth_headers("openrouter", api_key))
        resp.raise_for_status()
        data = resp.json().get("data", [])

    models: list[ModelInfo] = []
    for item in data:
        pricing = item.get("pricing")
        free = bool(
            pricing
            and pricing.get("prompt") == "0"
            and pricing.get("completion") == "0"
        )
        models.append(
            ModelInfo(
                id=item.get("id"),
                name=item.get("name") or item.get("id"),
                free=free,
                pricing=pricing,
                context_length=item.get("context_length"),
            )
        )
    return models


async def _fetch_openai(api_key: str | None = None) -> list[ModelInfo]:
    url = "https://api.openai.com/v1/models"
    async with httpx.AsyncClient(timeout=30.0) as client:
        resp = await client.get(url, headers=_auth_headers("openai", api_key))
        resp.raise_for_status()
        data = resp.json().get("data", [])

    models: list[ModelInfo] = []
    for item in data:
        model_id = item.get("id")
        models.append(
            ModelInfo(
                id=model_id,
                name=model_id,
                free=False,
                pricing=None,
                context_length=item.get("context_length"),
            )
        )
    return models


async def list_models(provider: str, api_key: str | None = None) -> list[ModelInfo]:
    # Only the configured-key path uses the shared cache (see note above).
    if not api_key:
        cached = _cache_get(provider)
        if cached is not None:
            return cached

    if provider == "openrouter":
        models = await _fetch_openrouter(api_key)
    elif provider == "openai":
        models = await _fetch_openai(api_key)
    else:
        models = []

    if not api_key:
        _cache_set(provider, models)
    return models

# tests/test_models.py
import httpx
import pytest
import respx

import app.models as models_module
from app.models import ModelInfo, list_models, list_providers


@pytest.fixture(autouse=True)
def clear_model_cache():
    """Each test starts and ends with an empty in-memory cache."""
    models_module._cache.clear()
    yield
    models_module._cache.clear()


OPENROUTER_PAYLOAD = {
    "data": [
        {
            "id": "meta-llama/llama-3-8b-instruct:free",
            "name": "Meta: Llama 3 8B Instruct (free)",
            "context_length": 8192,
            "pricing": {"prompt": "0", "completion": "0"},
        },
        {
            "id": "openai/gpt-4o",
            "name": "OpenAI: GPT-4o",
            "context_length": 128000,
            "pricing": {"prompt": "0.000005", "completion": "0.000015"},
        },
    ]
}

OPENAI_PAYLOAD = {
    "data": [
        {"id": "gpt-4o-mini", "object": "model"},
        {"id": "gpt-4o", "object": "model"},
    ]
}


def test_modelinfo_defaults():
    m = ModelInfo(id="x", name="X", free=True)
    assert m.id == "x"
    assert m.name == "X"
    assert m.free is True
    assert m.pricing is None
    assert m.context_length is None


def test_list_providers_delegates(monkeypatch):
    monkeypatch.setattr(
        models_module, "configured_providers", lambda: ["openai", "openrouter"]
    )
    assert list_providers() == ["openai", "openrouter"]


@pytest.mark.asyncio
@respx.mock
async def test_list_models_openrouter_free_and_paid():
    route = respx.get("https://openrouter.ai/api/v1/models").mock(
        return_value=httpx.Response(200, json=OPENROUTER_PAYLOAD)
    )
    models = await list_models("openrouter")

    assert route.called
    assert len(models) == 2
    by_id = {m.id: m for m in models}

    free_model = by_id["meta-llama/llama-3-8b-instruct:free"]
    paid_model = by_id["openai/gpt-4o"]

    assert free_model.free is True
    assert paid_model.free is False
    assert free_model.pricing == {"prompt": "0", "completion": "0"}
    assert free_model.name == "Meta: Llama 3 8B Instruct (free)"
    assert free_model.context_length == 8192
    assert paid_model.pricing == {"prompt": "0.000005", "completion": "0.000015"}


@pytest.mark.asyncio
@respx.mock
async def test_list_models_openai_name_equals_id_and_not_free():
    route = respx.get("https://api.openai.com/v1/models").mock(
        return_value=httpx.Response(200, json=OPENAI_PAYLOAD)
    )
    models = await list_models("openai")

    assert route.called
    assert len(models) == 2
    for m in models:
        assert m.name == m.id
        assert m.free is False
        assert m.pricing is None


@pytest.mark.asyncio
@respx.mock
async def test_list_models_uses_ttl_cache():
    route = respx.get("https://openrouter.ai/api/v1/models").mock(
        return_value=httpx.Response(200, json=OPENROUTER_PAYLOAD)
    )
    first = await list_models("openrouter")
    second = await list_models("openrouter")

    assert first == second          # ModelInfo is a dataclass -> value equality
    assert route.call_count == 1     # second call served from cache, no HTTP


@pytest.mark.asyncio
@respx.mock
async def test_list_models_uses_override_key_and_skips_cache():
    route = respx.get("https://openrouter.ai/api/v1/models").mock(
        return_value=httpx.Response(200, json=OPENROUTER_PAYLOAD)
    )
    await list_models("openrouter", api_key="my-override")

    assert route.called
    # The override key is sent as the bearer token, not the .env key.
    assert route.calls.last.request.headers.get("Authorization") == "Bearer my-override"
    # An override request must not populate the shared configured-key cache...
    assert "openrouter" not in models_module._cache
    # ...and a second override call is never served from cache.
    await list_models("openrouter", api_key="my-override")
    assert route.call_count == 2

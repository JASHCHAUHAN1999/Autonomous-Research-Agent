# tests/test_llm.py
import pytest
from langchain_openai import ChatOpenAI

import app.config as config
from app.llm import get_llm


def test_get_llm_openrouter_sets_model_and_base(monkeypatch):
    # Provide fake keys so ChatOpenAI does not complain about a missing key.
    monkeypatch.setattr(config.settings, "openrouter_api_key", "or-test-key")
    monkeypatch.setattr(config.settings, "openai_api_key", "oai-test-key")

    llm = get_llm("openrouter", "x")

    assert isinstance(llm, ChatOpenAI)
    # model= maps to the model_name field on ChatOpenAI
    assert llm.model_name == "x"
    # base_url= maps to openai_api_base on ChatOpenAI
    assert llm.openai_api_base == "https://openrouter.ai/api/v1"
    assert llm.temperature == 0.2


def test_get_llm_openai_uses_settings_model_and_no_custom_base(monkeypatch):
    monkeypatch.setattr(config.settings, "openai_api_key", "oai-test-key")
    monkeypatch.setattr(config.settings, "model", "gpt-4o-mini")
    monkeypatch.setattr(config.settings, "llm_provider", "openai")

    # model omitted -> should fall back to settings.model
    llm = get_llm("openai")

    assert llm.model_name == "gpt-4o-mini"
    # openai has no custom base_url (provider_base_url returns None)
    assert not llm.openai_api_base
    assert llm.temperature == 0.2


def test_get_llm_omits_temperature_for_search_preview():
    # search-preview models reject a custom temperature (HTTP 400) -> omit it.
    llm = get_llm("openai", "gpt-4o-mini-search-preview", api_key="k")
    assert llm.temperature is None


def test_get_llm_omits_temperature_for_reasoning_model():
    # o-series reasoning models reject our custom 0.2. We must not impose it;
    # langchain either omits temperature (None) or uses the model's own valid
    # default (e.g. 1.0 for o1) — but never our 0.2.
    for model in ("o1", "o3-mini", "o4-mini", "openai/o1"):
        llm = get_llm("openai", model, api_key="k")
        assert llm.temperature != 0.2, model


def test_get_llm_sets_temperature_for_normal_model():
    llm = get_llm("openai", "gpt-4o-mini", api_key="k")
    assert llm.temperature == 0.2


def test_get_llm_uses_explicit_api_key_over_settings(monkeypatch):
    # A UI-entered key must override the configured .env key for this call.
    monkeypatch.setattr(config.settings, "openrouter_api_key", "env-key")
    llm = get_llm("openrouter", "x", api_key="override-key")
    assert llm.openai_api_key.get_secret_value() == "override-key"


def test_get_llm_provider_defaults_to_settings(monkeypatch):
    monkeypatch.setattr(config.settings, "llm_provider", "openrouter")
    monkeypatch.setattr(config.settings, "openrouter_api_key", "or-test-key")
    monkeypatch.setattr(config.settings, "model", "auto-model")

    # both args omitted -> provider from settings.llm_provider, model from settings.model
    llm = get_llm()

    assert llm.model_name == "auto-model"
    assert llm.openai_api_base == "https://openrouter.ai/api/v1"
    assert llm.temperature == 0.2

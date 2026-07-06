import pytest

from app.sources import base
from app.sources.base import (
    REGISTRY,
    SourceResult,
    available_sources,
    get_adapter,
    register,
)


@pytest.fixture(autouse=True)
def clean_registry():
    """Snapshot REGISTRY before each test and restore it after."""
    saved = dict(REGISTRY)
    REGISTRY.clear()
    try:
        yield
    finally:
        REGISTRY.clear()
        REGISTRY.update(saved)


class FakeAdapter:
    """Minimal SourceAdapter implementation for tests."""

    def __init__(self, name: str, requires_key: bool = False):
        self.name = name
        self.requires_key = requires_key

    async def search(
        self, query: str, limit: int = 5, api_key: str | None = None
    ) -> list[SourceResult]:
        return [
            SourceResult(
                source=self.name,
                title=f"{query} result",
                url="https://example.com/x",
                content="body",
            )
        ]


def test_source_result_defaults():
    r = SourceResult(
        source="tavily",
        title="Hello",
        url="https://example.com/a",
        content="some content",
    )
    assert r.source == "tavily"
    assert r.title == "Hello"
    assert r.url == "https://example.com/a"
    assert r.content == "some content"
    assert r.published_at is None
    assert r.score is None


def test_register_and_get_adapter():
    adapter = FakeAdapter("tavily")
    register(adapter)
    assert get_adapter("tavily") is adapter
    assert REGISTRY["tavily"] is adapter


def test_get_adapter_missing_raises():
    with pytest.raises(KeyError):
        get_adapter("does-not-exist")


def test_available_sources_gated_by_keys():
    keyless = FakeAdapter("wikipedia", requires_key=False)
    keyed = FakeAdapter("tavily", requires_key=True)
    register(keyless)
    register(keyed)

    # No keys supplied -> only the keyless source is available.
    avail = available_sources()
    assert "wikipedia" in avail
    assert "tavily" not in avail

    # Supplying the key enables the keyed source.
    avail_keyed = available_sources({"tavily": "k"})
    assert "wikipedia" in avail_keyed
    assert "tavily" in avail_keyed

    # An empty-string key does not enable it.
    assert "tavily" not in available_sources({"tavily": ""})


def test_fake_adapter_satisfies_protocol():
    assert isinstance(FakeAdapter("web"), base.SourceAdapter)


@pytest.mark.asyncio
async def test_adapter_search_returns_source_results():
    adapter = FakeAdapter("wikipedia")
    register(adapter)
    results = await get_adapter("wikipedia").search("python", limit=3)
    assert isinstance(results, list)
    assert len(results) == 1
    assert isinstance(results[0], SourceResult)
    assert results[0].source == "wikipedia"

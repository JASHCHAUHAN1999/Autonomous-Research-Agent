# tests/sources/test_news.py
import httpx
import pytest
import respx

from app.sources.base import SourceResult, get_adapter
from app.sources.news import NewsAdapter

NEWS_URL = "https://newsapi.org/v2/everything"

SAMPLE = {
    "status": "ok",
    "totalResults": 2,
    "articles": [
        {
            "title": "AI breakthrough announced",
            "url": "https://example.com/ai",
            "description": "A big description",
            "content": "full content here",
            "publishedAt": "2026-07-01T12:00:00Z",
        },
        {
            "title": "Second story",
            "url": "https://example.com/two",
            "description": None,
            "content": "fallback content",
            "publishedAt": "2026-07-02T08:30:00Z",
        },
    ],
}


def test_name_and_requires_key():
    a = NewsAdapter()
    assert a.name == "news"
    assert a.requires_key is True


def test_registered_in_registry():
    # Importing app.sources.news triggers register(NewsAdapter()) at import time.
    adapter = get_adapter("news")
    assert adapter.name == "news"


@pytest.mark.asyncio
@respx.mock
async def test_search_uses_supplied_key_and_maps_articles():
    route = respx.get(NEWS_URL).mock(return_value=httpx.Response(200, json=SAMPLE))

    # The key comes from the caller (UI), not settings/.env.
    results = await NewsAdapter().search(
        "artificial intelligence", limit=3, api_key="ui-key"
    )

    assert route.called
    request = route.calls.last.request
    assert request.url.params["q"] == "artificial intelligence"
    assert request.url.params["pageSize"] == "3"
    assert request.url.params["apiKey"] == "ui-key"

    assert len(results) == 2
    assert all(isinstance(r, SourceResult) for r in results)

    first = results[0]
    assert first.source == "news"
    assert first.title == "AI breakthrough announced"
    assert first.url == "https://example.com/ai"
    assert first.content == "A big description"
    assert first.published_at == "2026-07-01T12:00:00Z"

    # description is None -> content falls back to the "content" field.
    second = results[1]
    assert second.content == "fallback content"
    assert second.published_at == "2026-07-02T08:30:00Z"


@pytest.mark.asyncio
@respx.mock
async def test_search_returns_empty_without_key():
    route = respx.get(NEWS_URL)
    results = await NewsAdapter().search("anything")
    assert results == []
    assert not route.called

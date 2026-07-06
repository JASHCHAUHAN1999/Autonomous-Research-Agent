# tests/sources/test_tavily.py
import json

import httpx
import pytest
import respx

from app.sources.tavily import TavilyAdapter


def test_adapter_name_and_requires_key():
    a = TavilyAdapter()
    assert a.name == "tavily"
    assert a.requires_key is True


@pytest.mark.asyncio
@respx.mock
async def test_search_uses_supplied_key_and_maps_results():
    route = respx.post("https://api.tavily.com/search").mock(
        return_value=httpx.Response(
            200,
            json={
                "results": [
                    {
                        "title": "Result One",
                        "url": "https://example.com/1",
                        "content": "First content",
                        "score": 0.9,
                    },
                    {
                        "title": "Result Two",
                        "url": "https://example.com/2",
                        "content": "Second content",
                        "score": 0.5,
                    },
                ]
            },
        )
    )

    # The key comes from the caller (UI), not settings/.env.
    results = await TavilyAdapter().search("test query", limit=2, api_key="ui-key")

    assert route.called
    sent = json.loads(route.calls.last.request.content)
    assert sent == {"api_key": "ui-key", "query": "test query", "max_results": 2}

    assert len(results) == 2
    first = results[0]
    assert first.source == "tavily"
    assert first.title == "Result One"
    assert first.url == "https://example.com/1"
    assert first.content == "First content"
    assert first.score == 0.9
    assert results[1].url == "https://example.com/2"


@pytest.mark.asyncio
@respx.mock
async def test_search_falls_back_to_snippet():
    respx.post("https://api.tavily.com/search").mock(
        return_value=httpx.Response(
            200,
            json={"results": [{"title": "T", "url": "https://e.com", "snippet": "snip text"}]},
        )
    )

    results = await TavilyAdapter().search("q", api_key="ui-key")

    assert results[0].content == "snip text"
    assert results[0].score is None


@pytest.mark.asyncio
@respx.mock
async def test_search_returns_empty_without_key():
    # No key supplied -> no HTTP request, returns [] (source stays unavailable).
    route = respx.post("https://api.tavily.com/search")

    results = await TavilyAdapter().search("test query")

    assert results == []
    assert not route.called

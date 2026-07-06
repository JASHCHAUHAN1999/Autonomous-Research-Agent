# tests/sources/test_wikipedia.py
import httpx
import pytest
import respx

from app.sources.base import SourceResult, REGISTRY
from app.sources.wikipedia import WikipediaAdapter, API_URL

# Sample payload shaped like the Wikipedia action API
# (action=query&generator=search&prop=extracts) response.
WIKI_RESPONSE = {
    "batchcomplete": "",
    "query": {
        "pages": {
            "21356332": {
                "pageid": 21356332,
                "ns": 0,
                "title": "Python (programming language)",
                "index": 1,
                "extract": "Python is a high-level, general-purpose programming language.",
            },
            "23862": {
                "pageid": 23862,
                "ns": 0,
                "title": "Python",
                "index": 2,
                "extract": "Python may refer to the snake, the language, or other things.",
            },
        }
    },
}


def test_name_and_requires_no_key():
    adapter = WikipediaAdapter()
    assert adapter.name == "wikipedia"
    assert adapter.requires_key is False


def test_module_registers_adapter_on_import():
    # Importing app.sources.wikipedia should have called register(WikipediaAdapter())
    assert "wikipedia" in REGISTRY
    assert REGISTRY["wikipedia"].name == "wikipedia"


@pytest.mark.asyncio
@respx.mock
async def test_search_returns_source_results():
    route = respx.get(API_URL).mock(
        return_value=httpx.Response(200, json=WIKI_RESPONSE)
    )

    adapter = WikipediaAdapter()
    results = await adapter.search("python", limit=5)

    assert route.called
    assert isinstance(results, list)
    assert len(results) == 2
    for r in results:
        assert isinstance(r, SourceResult)
        assert r.source == "wikipedia"
        assert r.title  # non-empty title
        assert r.content  # non-empty content
        assert r.url.startswith("https://en.wikipedia.org/wiki/")

    # Ordered by the search index; spaces/parens preserved in the URL title.
    assert results[0].title == "Python (programming language)"
    assert (
        results[0].url
        == "https://en.wikipedia.org/wiki/Python_(programming_language)"
    )
    assert results[0].content.startswith("Python is a high-level")


@pytest.mark.asyncio
@respx.mock
async def test_search_respects_limit():
    respx.get(API_URL).mock(
        return_value=httpx.Response(200, json=WIKI_RESPONSE)
    )
    adapter = WikipediaAdapter()
    results = await adapter.search("python", limit=1)
    assert len(results) == 1


@pytest.mark.asyncio
@respx.mock
async def test_search_empty_when_no_pages():
    # Wikipedia omits the "query" key entirely when nothing matches.
    respx.get(API_URL).mock(
        return_value=httpx.Response(200, json={"batchcomplete": ""})
    )
    adapter = WikipediaAdapter()
    results = await adapter.search("zzxqnothingmatchesthis", limit=5)
    assert results == []

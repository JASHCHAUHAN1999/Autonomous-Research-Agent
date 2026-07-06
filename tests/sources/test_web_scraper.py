import httpx
import pytest
import respx

from app.sources.base import SourceResult
from app.sources.web_scraper import WebScraperAdapter


SAMPLE_HTML = """
<!DOCTYPE html>
<html>
  <head>
    <title>Example Domain</title>
    <style>body { color: red; }</style>
  </head>
  <body>
    <script>console.log("ignore me");</script>
    <h1>Welcome</h1>
    <p>This domain is for use in examples.</p>
  </body>
</html>
"""


def test_name_and_requires_no_key():
    adapter = WebScraperAdapter()
    assert adapter.name == "web"
    assert adapter.requires_key is False


@pytest.mark.asyncio
async def test_search_extracts_title_and_text():
    url = "https://example.com/article"
    with respx.mock:
        respx.get(url).mock(return_value=httpx.Response(200, html=SAMPLE_HTML))
        adapter = WebScraperAdapter()
        results = await adapter.search(url)

    assert len(results) == 1
    result = results[0]
    assert isinstance(result, SourceResult)
    assert result.source == "web"
    assert result.url == url
    assert result.title == "Example Domain"
    assert "This domain is for use in examples." in result.content
    assert "console.log" not in result.content
    assert "color: red" not in result.content


@pytest.mark.asyncio
async def test_search_follows_redirects():
    start = "https://example.com/old"
    final = "https://example.com/new"
    with respx.mock:
        respx.get(start).mock(
            return_value=httpx.Response(301, headers={"Location": final})
        )
        respx.get(final).mock(return_value=httpx.Response(200, html=SAMPLE_HTML))
        adapter = WebScraperAdapter()
        results = await adapter.search(start)

    assert len(results) == 1
    # url returned is the original query URL passed to search()
    assert results[0].url == start
    assert results[0].title == "Example Domain"


@pytest.mark.asyncio
async def test_search_non_url_returns_empty():
    adapter = WebScraperAdapter()
    assert await adapter.search("what is machine learning") == []
    assert await adapter.search("") == []
    assert await adapter.search("   ") == []
    assert await adapter.search("ftp://example.com/file") == []
    assert await adapter.search("example.com/no-scheme") == []


def test_registered_in_registry():
    # Importing app.sources.web_scraper (done at top of this file) must have
    # registered the adapter under the exact key "web".
    from app.sources.base import REGISTRY, get_adapter

    assert "web" in REGISTRY
    assert get_adapter("web").name == "web"

from __future__ import annotations

from urllib.parse import urlparse

import httpx
from bs4 import BeautifulSoup

from app.sources.base import SourceResult, register


def _is_valid_url(url: str) -> bool:
    """True only for well-formed absolute http/https URLs."""
    try:
        parsed = urlparse(url)
    except (ValueError, TypeError):
        return False
    return parsed.scheme in ("http", "https") and bool(parsed.netloc)


class WebScraperAdapter:
    """Fetches a single URL and returns its readable text as one SourceResult.

    Unlike the other adapters, `query` is interpreted as a URL to fetch,
    not a search term.
    """

    name = "web"
    requires_key = False

    async def search(
        self, query: str, limit: int = 5, api_key: str | None = None
    ) -> list[SourceResult]:
        url = (query or "").strip()
        if not _is_valid_url(url):
            return []

        try:
            async with httpx.AsyncClient(
                follow_redirects=True, timeout=20.0
            ) as client:
                response = await client.get(url)
                response.raise_for_status()
                html = response.text
        except httpx.HTTPError:
            return []

        soup = BeautifulSoup(html, "html.parser")

        title_tag = soup.find("title")
        title = title_tag.get_text(strip=True) if title_tag else url

        # Remove non-content nodes before extracting text.
        for tag in soup(["script", "style", "noscript"]):
            tag.decompose()

        content = soup.get_text(separator=" ", strip=True)

        return [
            SourceResult(
                source="web",
                title=title or url,
                url=url,
                content=content,
            )
        ]


register(WebScraperAdapter())

# app/sources/wikipedia.py
from __future__ import annotations

import httpx

from app.sources.base import SourceResult, register

API_URL = "https://en.wikipedia.org/w/api.php"

# A descriptive User-Agent is requested by the Wikimedia API etiquette guidelines.
_USER_AGENT = "AutonomousResearchAgent/1.0 (https://example.com; research-agent)"


class WikipediaAdapter:
    name = "wikipedia"
    requires_key = False  # no API key needed

    async def search(
        self, query: str, limit: int = 5, api_key: str | None = None
    ) -> list[SourceResult]:
        params = {
            "action": "query",
            "format": "json",
            "generator": "search",     # find pages matching the query
            "gsrsearch": query,
            "gsrlimit": limit,
            "prop": "extracts",        # and pull each page's intro text
            "exintro": 1,              # only the lead section
            "explaintext": 1,          # plain text, not HTML
            "exlimit": "max",          # allow extracts for all returned pages
        }
        headers = {"User-Agent": _USER_AGENT}

        async with httpx.AsyncClient(timeout=20.0) as client:
            resp = await client.get(API_URL, params=params, headers=headers)
            resp.raise_for_status()
            data = resp.json()

        pages = data.get("query", {}).get("pages", {})
        # Order by the search relevance index (lower index == better match).
        ordered = sorted(pages.values(), key=lambda p: p.get("index", 0))

        results: list[SourceResult] = []
        for page in ordered:
            title = page.get("title") or ""
            if not title:
                continue
            extract = page.get("extract") or ""
            url = "https://en.wikipedia.org/wiki/" + title.replace(" ", "_")
            results.append(
                SourceResult(
                    source="wikipedia",
                    title=title,
                    url=url,
                    content=extract,
                )
            )

        return results[:limit]


# Populate the shared REGISTRY at import time.
register(WikipediaAdapter())

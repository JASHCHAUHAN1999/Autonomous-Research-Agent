# app/sources/tavily.py
from __future__ import annotations

import httpx

from app.sources.base import SourceResult, register

TAVILY_SEARCH_URL = "https://api.tavily.com/search"


class TavilyAdapter:
    name: str = "tavily"
    requires_key: bool = True

    async def search(
        self, query: str, limit: int = 5, api_key: str | None = None
    ) -> list[SourceResult]:
        if not api_key:
            return []

        payload = {
            "api_key": api_key,
            "query": query,
            "max_results": limit,
        }

        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.post(TAVILY_SEARCH_URL, json=payload)
            response.raise_for_status()
            data = response.json()

        results: list[SourceResult] = []
        for item in data.get("results", []):
            results.append(
                SourceResult(
                    source="tavily",
                    title=item.get("title", ""),
                    url=item.get("url", ""),
                    content=item.get("content") or item.get("snippet") or "",
                    score=item.get("score"),
                )
            )
        return results


register(TavilyAdapter())

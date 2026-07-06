# app/sources/news.py
import httpx

from app.sources.base import SourceResult, register

NEWSAPI_URL = "https://newsapi.org/v2/everything"


class NewsAdapter:
    name = "news"
    requires_key = True

    async def search(
        self, query: str, limit: int = 5, api_key: str | None = None
    ) -> list[SourceResult]:
        if not api_key:
            return []
        params = {
            "q": query,
            "pageSize": limit,
            "apiKey": api_key,
        }
        async with httpx.AsyncClient(timeout=20.0) as client:
            resp = await client.get(NEWSAPI_URL, params=params)
            resp.raise_for_status()
            data = resp.json()

        results: list[SourceResult] = []
        for article in data.get("articles", []):
            results.append(
                SourceResult(
                    source="news",
                    title=article.get("title") or "",
                    url=article.get("url") or "",
                    content=article.get("description") or article.get("content") or "",
                    published_at=article.get("publishedAt"),
                )
            )
        return results


register(NewsAdapter())

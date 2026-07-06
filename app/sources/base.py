"""Source registry and shared result type for all research source adapters."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol, runtime_checkable


@dataclass
class SourceResult:
    """A single item returned by a source adapter."""

    source: str
    title: str
    url: str
    content: str
    published_at: str | None = None
    score: float | None = None


@runtime_checkable
class SourceAdapter(Protocol):
    """Interface every source adapter (tavily/wikipedia/news/web) implements."""

    name: str
    requires_key: bool

    async def search(
        self, query: str, limit: int = 5, api_key: str | None = None
    ) -> list[SourceResult]:
        """Run a search and return up to `limit` results.

        Adapters that need an API key receive it via `api_key` (supplied per
        request from the UI); keyless adapters ignore it.
        """
        ...


# Keys are populated at import time by each adapter module calling register().
# Canonical adapter names: "tavily", "wikipedia", "news", "web".
REGISTRY: dict[str, SourceAdapter] = {}


def register(adapter: SourceAdapter) -> None:
    """Register an adapter under its .name (called by each adapter module)."""
    REGISTRY[adapter.name] = adapter


def get_adapter(name: str) -> SourceAdapter:
    """Return the registered adapter for `name` or raise KeyError."""
    try:
        return REGISTRY[name]
    except KeyError:
        raise KeyError(
            f"No source adapter registered under {name!r}. "
            f"Registered: {sorted(REGISTRY)}"
        )


def available_sources(keys: dict[str, str] | None = None) -> list[str]:
    """Names of sources usable for a request given the supplied per-source keys.

    A source is available when it needs no key (``requires_key`` is False) or a
    non-empty key for it is present in ``keys`` (e.g. {"tavily": "...",
    "news": "..."}). Source keys come from the UI per request — there is no
    ``.env`` fallback for source keys.
    """
    keys = keys or {}
    return [
        name
        for name, adapter in REGISTRY.items()
        if not getattr(adapter, "requires_key", False) or keys.get(name)
    ]

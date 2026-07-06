"""Typed state definitions for the research agent graph."""

from __future__ import annotations

from typing import TypedDict

from app.sources.base import SourceResult

# Plan: the planning node's structured decision.
# For the "web" source, subqueries["web"] holds URLs to fetch rather than
# free-text search phrases.
Plan = TypedDict(
    "Plan",
    {
        "sources": list[str],
        "subqueries": dict[str, list[str]],
        "reasoning": str,
    },
)

# ResearchState: the LangGraph state object threaded through every node.
# total=False -> every key is optional, so nodes may return partial updates.
ResearchState = TypedDict(
    "ResearchState",
    {
        "query": str,
        "provider": str | None,
        "model": str | None,
        # Optional per-request LLM API key entered in the UI; overrides the .env key.
        "api_key": str | None,
        # Per-source API keys entered in the UI, e.g. {"tavily": "...", "news": "..."}.
        "source_keys": dict,
        # User's explicit source selection from the UI (empty/absent => auto-pick).
        "requested_sources": list[str],
        "plan": Plan | None,
        "raw_results": list[SourceResult],
        "clean_results": list[SourceResult],
        "iteration": int,
        "reflection": dict | None,
        "report_markdown": str | None,
        "run_id": int | None,
        "errors": list[str],
    },
    total=False,
)

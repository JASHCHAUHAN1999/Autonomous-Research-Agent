# app/processing/dedupe.py
"""Deduplication and relevance filtering for gathered source results."""
from __future__ import annotations

import difflib
import json
import re
from urllib.parse import urlsplit

from app.sources.base import SourceResult


def _normalize_url(url: str) -> str:
    """Normalize a URL for duplicate detection.

    Drops scheme + query + fragment, lowercases netloc/path, strips a trailing
    slash, so "https://Example.com/page/?q=1" == "http://example.com/page".
    """
    if not url:
        return ""
    parts = urlsplit(url.strip())
    netloc = parts.netloc.lower()
    path = parts.path or ""
    combined = f"{netloc}{path}" if netloc else path
    return combined.lower().rstrip("/")


def dedupe(results: list[SourceResult]) -> list[SourceResult]:
    """Drop duplicate results by normalized URL and near-identical content.

    A result is dropped when its normalized URL matches an already-kept result,
    or when its content is near-identical (difflib ratio > 0.9) to a kept one.
    """
    kept: list[SourceResult] = []
    seen_urls: set[str] = set()
    for r in results:
        key = _normalize_url(r.url)
        if key and key in seen_urls:
            continue
        content = (r.content or "").strip()
        is_dup = False
        if content:
            for existing in kept:
                existing_content = (existing.content or "").strip()
                if not existing_content:
                    continue
                ratio = difflib.SequenceMatcher(None, content, existing_content).ratio()
                if ratio > 0.9:
                    is_dup = True
                    break
        if is_dup:
            continue
        if key:
            seen_urls.add(key)
        kept.append(r)
    return kept


def _parse_json(content) -> dict:
    """Tolerant JSON-object extraction from raw LLM text output."""
    if isinstance(content, dict):
        return content
    text = content if isinstance(content, str) else str(content)
    text = text.strip()
    if text.startswith("```"):
        text = re.sub(r"^```[a-zA-Z0-9]*\s*", "", text)
        text = re.sub(r"\s*```$", "", text).strip()
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass
    match = re.search(r"\{.*\}", text, re.DOTALL)
    if match:
        try:
            return json.loads(match.group(0))
        except json.JSONDecodeError:
            return {}
    return {}


def _build_filter_messages(query: str, results: list[SourceResult]) -> tuple[str, str]:
    """Return (system, user) messages, using app.agent.prompts when available."""
    try:
        from app.agent.prompts import FILTER_SYSTEM, build_filter_prompt
    except ImportError:
        system = (
            "You are a relevance filter. Given a research query and a numbered "
            "list of candidate sources, decide which are relevant to the query. "
            'Respond with JSON only, in the form {"keep": [<indices to keep>]}.'
        )
        lines = [f"Query: {query}", "", "Sources:"]
        for i, r in enumerate(results):
            snippet = (r.content or "").replace("\n", " ")[:300]
            lines.append(f"[{i}] {r.title} ({r.url}) - {snippet}")
        lines += ["", 'Return JSON {"keep": [indices to keep]}.']
        return system, "\n".join(lines)
    return FILTER_SYSTEM, build_filter_prompt(query, results)


async def filter_relevant(
    query: str, results: list[SourceResult], llm=None
) -> list[SourceResult]:
    """Filter results by relevance to the query.

    With llm=None (offline default) the input list is returned unchanged. With an
    llm, ask it for JSON {"keep": [indices]} and return only the selected results,
    preserving the original `results` order (source ranking) regardless of the
    order of indices in `keep`, and ignoring out-of-range/duplicate indices.
    """
    if llm is None or not results:
        return list(results)
    system, user = _build_filter_messages(query, results)
    try:
        response = await llm.ainvoke(
            [
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ]
        )
    except Exception:  # noqa: BLE001 - filtering is best-effort
        # If the LLM call fails (e.g. a transient rate-limit), keep the deduped
        # results rather than aborting the whole research run.
        return list(results)
    content = getattr(response, "content", response)
    data = _parse_json(content)
    keep = data.get("keep")
    if not isinstance(keep, list):
        return list(results)
    keep_indices: set[int] = set()
    for raw in keep:
        try:
            idx = int(raw)
        except (TypeError, ValueError):
            continue
        if 0 <= idx < len(results):
            keep_indices.add(idx)
    return [r for i, r in enumerate(results) if i in keep_indices]

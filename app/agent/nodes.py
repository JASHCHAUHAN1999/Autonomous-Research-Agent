"""LangGraph node coroutines for the autonomous research agent.

Each node takes the ``ResearchState`` and returns a partial-state dict that
LangGraph merges into the running state. ``route_after_reflect`` is the
conditional edge deciding whether to loop back to ``gather`` or move on to
``synthesize``. ``parse_json`` tolerantly extracts a JSON object from
arbitrary LLM text.
"""

import asyncio
import json
import re

from langchain_core.messages import SystemMessage, HumanMessage

from app.config import settings
from app.llm import get_llm
from app.sources.base import available_sources, get_adapter
from app.processing.dedupe import dedupe, filter_relevant
from app.storage import db
from app.agent.prompts import (
    PLAN_SYSTEM,
    build_plan_prompt,
    REFLECT_SYSTEM,
    build_reflect_prompt,
    SYNTH_SYSTEM,
    build_synth_prompt,
)


def parse_json(content: str) -> dict:
    """Tolerantly extract a JSON object from arbitrary LLM text.

    Tries, in order: direct parse, fenced ```json ... ``` block, then the
    substring from the first '{' to the last '}'. Returns {} on failure.
    """
    if not content:
        return {}
    text = content.strip()

    # 1) direct parse
    try:
        parsed = json.loads(text)
        if isinstance(parsed, dict):
            return parsed
    except (json.JSONDecodeError, TypeError):
        pass

    # 2) fenced code block (```json ... ``` or ``` ... ```)
    fence = re.search(r"```(?:json)?\s*(.*?)```", text, re.DOTALL)
    if fence:
        try:
            parsed = json.loads(fence.group(1).strip())
            if isinstance(parsed, dict):
                return parsed
        except json.JSONDecodeError:
            pass

    # 3) first '{' .. last '}'
    start = text.find("{")
    end = text.rfind("}")
    if start != -1 and end != -1 and end > start:
        try:
            parsed = json.loads(text[start:end + 1])
            if isinstance(parsed, dict):
                return parsed
        except json.JSONDecodeError:
            pass

    return {}


_TRANSIENT_MARKERS = (
    "429", "502", "503", "rate limit", "rate-limited", "ratelimit",
    "resourceexhausted", "resource exhausted", "overloaded", "temporarily",
    "timeout", "timed out",
)


async def _ainvoke(llm, system: str, human: str, *, max_retries: int = 4) -> str:
    """Invoke the chat model, retrying transient errors (429/502/rate-limit) with backoff.

    Provider free tiers throttle bursts of calls; a research run makes several
    sequential LLM calls, so a single transient rate-limit shouldn't abort the
    whole run. Retries honor a ``Retry-After`` hint when the error carries one.
    """
    messages = [SystemMessage(content=system), HumanMessage(content=human)]
    delay = 3.0
    for attempt in range(max_retries + 1):
        try:
            response = await llm.ainvoke(messages)
            return getattr(response, "content", "") or ""
        except Exception as exc:  # noqa: BLE001 - classify then re-raise if fatal
            msg = str(exc).lower()
            transient = any(marker in msg for marker in _TRANSIENT_MARKERS)
            if not transient or attempt == max_retries:
                raise
            wait = delay
            hint = re.search(r"retry[_-]?after[^0-9]*(\d+)", msg)
            if hint:
                wait = max(wait, float(hint.group(1)) + 1.0)
            await asyncio.sleep(min(wait, 40.0))
            delay *= 2


async def plan_node(state) -> dict:
    query = state.get("query", "")
    available = available_sources(state.get("source_keys"))

    # If the user explicitly selected sources, constrain the planner to the
    # ones that are actually available; otherwise let it auto-pick from all.
    requested = [s for s in (state.get("requested_sources") or []) if s in available]
    candidates = requested if requested else available

    llm = get_llm(state.get("provider"), state.get("model"), state.get("api_key"))
    content = await _ainvoke(llm, PLAN_SYSTEM, build_plan_prompt(query, candidates))
    data = parse_json(content)

    subqueries = data.get("subqueries", {}) or {}
    chosen = [s for s in data.get("sources", []) if s in candidates]

    if requested:
        # Honor the user's selection exactly: the LLM still crafts subqueries,
        # but the set of sources is the user's choice (that is available), never
        # the model's auto-pick. Backfill subqueries the model may have omitted.
        chosen = list(requested)
        for source in requested:
            if not subqueries.get(source):
                subqueries[source] = [query]

    plan = {
        "sources": chosen,
        "subqueries": subqueries,
        "reasoning": data.get("reasoning", ""),
    }
    return {"plan": plan}


async def gather_node(state) -> dict:
    query = state.get("query", "")
    plan = state.get("plan") or {"sources": [], "subqueries": {}}
    subqueries = plan.get("subqueries", {}) or {}

    raw_results = list(state.get("raw_results", []))
    errors = list(state.get("errors", []))
    source_keys = state.get("source_keys") or {}

    tasks = []
    for source in plan.get("sources", []):
        try:
            adapter = get_adapter(source)
        except KeyError as exc:
            # An unknown/unavailable source is recorded and skipped, never fatal.
            errors.append(f"gather: {exc}")
            continue
        subs = subqueries.get(source) or [query]
        for sub in subs:
            tasks.append(
                adapter.search(sub, limit=5, api_key=source_keys.get(source))
            )

    if tasks:
        outcomes = await asyncio.gather(*tasks, return_exceptions=True)
        for outcome in outcomes:
            if isinstance(outcome, Exception):
                errors.append(f"gather: {outcome}")
            else:
                raw_results.extend(outcome)

    return {
        "raw_results": raw_results,
        "iteration": state.get("iteration", 0) + 1,
        "errors": errors,
    }


async def process_node(state) -> dict:
    query = state.get("query", "")
    deduped = dedupe(state.get("raw_results", []))
    clean = await filter_relevant(
        query,
        deduped,
        llm=get_llm(state.get("provider"), state.get("model"), state.get("api_key")),
    )
    return {"clean_results": clean}


async def reflect_node(state) -> dict:
    query = state.get("query", "")
    results = state.get("clean_results", [])
    llm = get_llm(state.get("provider"), state.get("model"), state.get("api_key"))
    content = await _ainvoke(llm, REFLECT_SYSTEM, build_reflect_prompt(query, results))
    data = parse_json(content)
    reflection = {
        "enough": bool(data.get("enough", True)),
        "gaps": data.get("gaps", []) or [],
    }
    return {"reflection": reflection}


async def synthesize_node(state) -> dict:
    query = state.get("query", "")
    results = state.get("clean_results", [])
    llm = get_llm(state.get("provider"), state.get("model"), state.get("api_key"))
    content = await _ainvoke(llm, SYNTH_SYSTEM, build_synth_prompt(query, results))
    return {"report_markdown": content}


async def persist_node(state) -> dict:
    query = state.get("query", "")
    provider = state.get("provider") or settings.llm_provider
    model = state.get("model") or settings.model
    run_id = db.create_run(query, provider, model)
    db.save_report(
        run_id,
        state.get("report_markdown") or "",
        state.get("clean_results", []),
        status="done",
    )
    return {"run_id": run_id}


def route_after_reflect(state) -> str:
    reflection = state.get("reflection") or {}
    enough = reflection.get("enough", True)
    iteration = state.get("iteration", 0)
    if not enough and iteration < settings.max_iterations:
        return "gather"
    return "synthesize"

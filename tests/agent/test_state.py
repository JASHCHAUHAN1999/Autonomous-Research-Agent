import pytest

from app.agent.state import Plan, ResearchState
from app.agent.prompts import (
    PLAN_SYSTEM,
    FILTER_SYSTEM,
    REFLECT_SYSTEM,
    SYNTH_SYSTEM,
    build_plan_prompt,
    build_filter_prompt,
    build_reflect_prompt,
    build_synth_prompt,
)
from app.sources.base import SourceResult


def test_plan_typeddict_accepts_expected_keys():
    plan: Plan = {
        "sources": ["tavily", "web"],
        "subqueries": {"tavily": ["q1", "q2"], "web": ["https://example.com"]},
        "reasoning": "because tavily is broad and web fetches a known page",
    }
    assert plan["sources"] == ["tavily", "web"]
    assert plan["subqueries"]["web"] == ["https://example.com"]
    assert set(Plan.__annotations__) == {"sources", "subqueries", "reasoning"}


def test_research_state_accepts_expected_keys():
    state: ResearchState = {
        "query": "what is rust",
        "provider": "openai",
        "model": "gpt-4o-mini",
        "requested_sources": ["wikipedia"],
        "plan": None,
        "raw_results": [],
        "clean_results": [],
        "iteration": 0,
        "reflection": None,
        "report_markdown": None,
        "run_id": None,
        "errors": [],
    }
    assert state["query"] == "what is rust"
    expected = {
        "query",
        "provider",
        "model",
        "api_key",
        "source_keys",
        "requested_sources",
        "plan",
        "raw_results",
        "clean_results",
        "iteration",
        "reflection",
        "report_markdown",
        "run_id",
        "errors",
    }
    assert set(ResearchState.__annotations__) == expected
    # total=False -> no key is required, so an empty dict is a valid state
    assert ResearchState.__total__ is False
    empty: ResearchState = {}
    assert empty == {}


def test_build_plan_prompt_contains_sources_and_query():
    query = "best python web frameworks"
    prompt = build_plan_prompt(query, ["tavily", "wikipedia"])
    assert "tavily" in prompt
    assert "wikipedia" in prompt
    assert query in prompt


def test_synth_system_mentions_four_sections():
    for section in (
        "Key Points",
        "Important Findings",
        "References / Sources",
        "Actionable Insights",
    ):
        assert section in SYNTH_SYSTEM


def test_build_synth_prompt_mentions_sections_and_query():
    prompt = build_synth_prompt("q about rust", [])
    assert "q about rust" in prompt
    for section in (
        "Key Points",
        "Important Findings",
        "References / Sources",
        "Actionable Insights",
    ):
        assert section in prompt


def test_system_prompts_are_nonempty_strings():
    for s in (PLAN_SYSTEM, FILTER_SYSTEM, REFLECT_SYSTEM, SYNTH_SYSTEM):
        assert isinstance(s, str)
        assert s.strip() != ""


def test_filter_and_reflect_prompts_include_indices_and_content():
    results = [
        SourceResult(
            source="tavily", title="T", url="https://a.com", content="alpha content"
        ),
        SourceResult(
            source="wikipedia", title="W", url="https://b.com", content="beta content"
        ),
    ]
    fprompt = build_filter_prompt("q", results)
    assert "[0]" in fprompt and "[1]" in fprompt
    assert "keep" in fprompt
    assert "alpha content" in fprompt

    rprompt = build_reflect_prompt("q", results)
    assert "enough" in rprompt
    assert "beta content" in rprompt

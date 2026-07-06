import asyncio
import json
from types import SimpleNamespace

import pytest

from app.agent import nodes
from app.config import settings
from app.sources.base import SourceResult
from app.storage import db


# --- test doubles ---------------------------------------------------------

class FakeLLM:
    """Stand-in for ChatOpenAI: ainvoke returns a canned .content string."""

    def __init__(self, content):
        self._content = content

    async def ainvoke(self, messages):
        return SimpleNamespace(content=self._content)


class ConcurrencyTracker:
    def __init__(self):
        self.active = 0
        self.max_active = 0


class FakeAdapter:
    def __init__(self, name, tracker):
        self.name = name
        self.tracker = tracker

    def available(self):
        return True

    async def search(self, query, limit=5, api_key=None):
        self.tracker.active += 1
        self.tracker.max_active = max(self.tracker.max_active, self.tracker.active)
        await asyncio.sleep(0.01)
        self.tracker.active -= 1
        return [
            SourceResult(
                source=self.name,
                title=query,
                url=f"http://{self.name}/{query}",
                content=f"content for {query}",
            )
        ]


# --- gather passes the per-source key ------------------------------------

@pytest.mark.asyncio
async def test_gather_node_passes_per_source_key(monkeypatch):
    captured = {}

    class KeyCapturingAdapter:
        name = "tavily"
        requires_key = True

        async def search(self, query, limit=5, api_key=None):
            captured["api_key"] = api_key
            return [SourceResult(source="tavily", title="t", url="u", content="c")]

    monkeypatch.setattr(nodes, "get_adapter", lambda name: KeyCapturingAdapter())
    state = {
        "query": "q",
        "plan": {"sources": ["tavily"], "subqueries": {"tavily": ["sub"]}},
        "source_keys": {"tavily": "secret-key"},
        "raw_results": [],
        "errors": [],
        "iteration": 0,
    }
    await nodes.gather_node(state)
    assert captured["api_key"] == "secret-key"


# --- parse_json -----------------------------------------------------------

def test_parse_json_handles_fences_and_prose():
    assert nodes.parse_json('{"a": 1}') == {"a": 1}
    assert nodes.parse_json('```json\n{"a": 2}\n```') == {"a": 2}
    assert nodes.parse_json('Result: {"a": 3}. Done.') == {"a": 3}
    assert nodes.parse_json("no json here") == {}
    assert nodes.parse_json("") == {}


# --- plan_node ------------------------------------------------------------

@pytest.mark.asyncio
async def test_plan_node_filters_to_available(monkeypatch):
    monkeypatch.setattr(nodes, "available_sources", lambda keys=None: ["wikipedia", "web"])
    canned = json.dumps(
        {
            "sources": ["wikipedia", "tavily", "web"],  # tavily NOT available
            "subqueries": {
                "wikipedia": ["python history"],
                "web": ["https://python.org"],
            },
            "reasoning": "picked these",
        }
    )
    monkeypatch.setattr(nodes, "get_llm", lambda *a, **k: FakeLLM(canned))

    result = await nodes.plan_node({"query": "python"})
    plan = result["plan"]
    assert plan["sources"] == ["wikipedia", "web"]  # tavily dropped
    assert plan["subqueries"]["wikipedia"] == ["python history"]
    assert plan["reasoning"] == "picked these"


# --- gather_node ----------------------------------------------------------

@pytest.mark.asyncio
async def test_gather_node_fills_increments_and_runs_concurrently(monkeypatch):
    tracker = ConcurrencyTracker()
    adapters = {
        "wikipedia": FakeAdapter("wikipedia", tracker),
        "web": FakeAdapter("web", tracker),
    }
    monkeypatch.setattr(nodes, "get_adapter", lambda name: adapters[name])

    existing = SourceResult(source="x", title="old", url="http://x", content="c")
    state = {
        "query": "python",
        "plan": {
            "sources": ["wikipedia", "web"],
            "subqueries": {"wikipedia": ["a", "b"], "web": ["https://x"]},
            "reasoning": "",
        },
        "iteration": 0,
        "raw_results": [existing],
    }

    result = await nodes.gather_node(state)
    assert result["iteration"] == 1
    # 1 pre-existing + 2 wikipedia subqueries + 1 web subquery = 4
    assert len(result["raw_results"]) == 4
    assert result["raw_results"][0] is existing  # appended, not replaced
    assert tracker.max_active >= 2  # proves concurrent execution


@pytest.mark.asyncio
async def test_gather_node_survives_failing_adapter(monkeypatch):
    """A raising/timing-out adapter is recorded in errors and skipped, not fatal."""
    tracker = ConcurrencyTracker()

    class BoomAdapter:
        name = "boom"

        def available(self):
            return True

        async def search(self, query, limit=5, api_key=None):
            raise RuntimeError("adapter exploded")

    adapters = {
        "wikipedia": FakeAdapter("wikipedia", tracker),
        "boom": BoomAdapter(),
    }
    monkeypatch.setattr(nodes, "get_adapter", lambda name: adapters[name])

    state = {
        "query": "python",
        "plan": {
            "sources": ["wikipedia", "boom"],
            "subqueries": {"wikipedia": ["a"], "boom": ["b"]},
            "reasoning": "",
        },
        "iteration": 0,
        "raw_results": [],
    }

    result = await nodes.gather_node(state)
    # The run still completed and produced the good adapter's result.
    assert result["iteration"] == 1
    assert len(result["raw_results"]) == 1
    assert result["raw_results"][0].source == "wikipedia"
    # The failure was recorded, not raised.
    assert len(result["errors"]) == 1
    assert "adapter exploded" in result["errors"][0]


# --- process_node ---------------------------------------------------------

@pytest.mark.asyncio
async def test_process_node_dedupes_and_filters(monkeypatch):
    monkeypatch.setattr(nodes, "get_llm", lambda *a, **k: FakeLLM("{}"))

    captured = {}

    async def fake_filter(query, results, llm=None):
        captured["query"] = query
        captured["llm"] = llm
        return results

    monkeypatch.setattr(nodes, "filter_relevant", fake_filter)

    r1 = SourceResult(source="wikipedia", title="A",
                      url="https://ex.com/a", content="hello world")
    r2 = SourceResult(source="wikipedia", title="A2",
                      url="http://ex.com/a/", content="hello world")  # same normalized URL
    r3 = SourceResult(source="web", title="B",
                      url="https://other.com", content="a completely different body")

    result = await nodes.process_node({"query": "q", "raw_results": [r1, r2, r3]})
    clean = result["clean_results"]
    assert len(clean) == 2  # r1/r2 collapsed by dedupe
    assert captured["query"] == "q"
    assert captured["llm"] is not None  # filter_relevant was given a real llm


# --- reflect_node ---------------------------------------------------------

@pytest.mark.asyncio
async def test_reflect_node_parses_reflection(monkeypatch):
    canned = '```json\n{"enough": false, "gaps": ["pricing", "benchmarks"]}\n```'
    monkeypatch.setattr(nodes, "get_llm", lambda *a, **k: FakeLLM(canned))

    result = await nodes.reflect_node({"query": "q", "clean_results": []})
    assert result["reflection"] == {"enough": False, "gaps": ["pricing", "benchmarks"]}


# --- synthesize_node ------------------------------------------------------

@pytest.mark.asyncio
async def test_synthesize_node_sets_report(monkeypatch):
    md = "# Report\n\n## Key Points\n- one\n"
    monkeypatch.setattr(nodes, "get_llm", lambda *a, **k: FakeLLM(md))

    result = await nodes.synthesize_node({"query": "q", "clean_results": []})
    assert result["report_markdown"] == md


# --- persist_node ---------------------------------------------------------

@pytest.mark.asyncio
async def test_persist_node_writes_row(monkeypatch, tmp_path):
    db_file = tmp_path / "research.db"
    monkeypatch.setattr(settings, "db_path", str(db_file))
    db.init_db(str(db_file))

    state = {
        "query": "python typing",
        "provider": "openai",
        "model": "gpt-4o-mini",
        "report_markdown": "# Report body",
        "clean_results": [
            SourceResult(source="web", title="T", url="http://x", content="c")
        ],
    }

    result = await nodes.persist_node(state)
    run_id = result["run_id"]
    assert isinstance(run_id, int)

    stored = db.get_run(run_id)
    assert stored is not None
    assert stored["query"] == "python typing"
    assert stored["report_markdown"] == "# Report body"
    assert stored["provider"] == "openai"
    assert stored["model"] == "gpt-4o-mini"
    assert len(stored["sources"]) == 1


# --- route_after_reflect --------------------------------------------------

def test_route_after_reflect_boundaries(monkeypatch):
    monkeypatch.setattr(nodes.settings, "max_iterations", 2)

    # enough == True -> synthesize regardless of iteration
    assert nodes.route_after_reflect(
        {"reflection": {"enough": True, "gaps": []}, "iteration": 1}
    ) == "synthesize"

    # not enough AND iteration < max -> loop back to gather
    assert nodes.route_after_reflect(
        {"reflection": {"enough": False, "gaps": ["x"]}, "iteration": 1}
    ) == "gather"

    # not enough BUT iteration >= max -> stop, synthesize
    assert nodes.route_after_reflect(
        {"reflection": {"enough": False, "gaps": ["x"]}, "iteration": 2}
    ) == "synthesize"

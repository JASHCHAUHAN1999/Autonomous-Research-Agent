# tests/agent/test_graph.py
import json

import pytest

from app.sources.base import SourceResult
from app.agent.graph import build_graph, run_research


# --- Fakes -----------------------------------------------------------------

class FakeResponse:
    """Mimics a langchain AIMessage: exposes a .content string."""

    def __init__(self, content: str):
        self.content = content


class FakeLLM:
    """Keyword-driven stand-in for ChatOpenAI.

    Inspects the prompt text and returns the JSON / markdown each node
    expects. Works whether nodes pass a message list or a single string.
    """

    def __init__(self, reflect_enough: bool = True):
        self.reflect_enough = reflect_enough

    async def ainvoke(self, prompt, *args, **kwargs):
        if isinstance(prompt, str):
            text = prompt.lower()
        else:
            text = " ".join(getattr(m, "content", str(m)) for m in prompt).lower()

        # plan_node: JSON {sources, subqueries, reasoning}
        if "subqueries" in text and "sources" in text:
            return FakeResponse(json.dumps({
                "sources": ["wikipedia"],
                "subqueries": {"wikipedia": ["q"]},
                "reasoning": "fake plan",
            }))
        # filter (process_node, only if it passes an llm): JSON {keep: [indices]}
        if "keep" in text:
            return FakeResponse(json.dumps({"keep": [0]}))
        # reflect_node: JSON {enough, gaps}
        if "enough" in text or "gaps" in text:
            return FakeResponse(json.dumps({
                "enough": self.reflect_enough,
                "gaps": ["a gap"],
            }))
        # synthesize_node: markdown report
        return FakeResponse(
            "# Report\n\n## Key Points\n- point\n\n"
            "## Important Findings\n- finding\n\n"
            "## References / Sources\n- src\n\n"
            "## Actionable Insights\n- do this\n"
        )


class SpyAdapter:
    """Fake 'wikipedia' adapter that counts search() calls (== gather runs)."""

    name = "wikipedia"

    def __init__(self):
        self.calls = 0

    def available(self) -> bool:
        return True

    async def search(self, query: str, limit: int = 5, api_key: str | None = None):
        self.calls += 1
        return [SourceResult(
            source="wikipedia",
            title="Result title",
            url="http://example.com/a",
            content=f"content about {query}",
        )]


def _patch_llm(monkeypatch, reflect_enough: bool) -> FakeLLM:
    """Patch get_llm wherever it may have been imported."""
    fake = FakeLLM(reflect_enough=reflect_enough)

    def factory(provider=None, model=None, api_key=None):
        return fake

    import app.llm as llm_mod
    monkeypatch.setattr(llm_mod, "get_llm", factory)

    import app.agent.nodes as nodes_mod
    if hasattr(nodes_mod, "get_llm"):
        monkeypatch.setattr(nodes_mod, "get_llm", factory)
    return fake


# --- Fixtures --------------------------------------------------------------

@pytest.fixture
def fake_env(monkeypatch, tmp_path):
    """Isolated DB + spy adapter; returns the spy so tests can read .calls."""
    import app.sources  # noqa: F401 - ensures REGISTRY is populated
    from app.sources import base as sources_base
    from app.config import settings
    from app.storage import db

    db_path = tmp_path / "research.db"
    monkeypatch.setattr(settings, "db_path", str(db_path))
    monkeypatch.setattr(settings, "max_iterations", 2)
    db.init_db(str(db_path))

    spy = SpyAdapter()
    monkeypatch.setitem(sources_base.REGISTRY, "wikipedia", spy)
    return spy


# --- Tests -----------------------------------------------------------------

def test_build_graph_compiles_with_expected_nodes():
    graph = build_graph()
    assert hasattr(graph, "astream")
    names = set(graph.get_graph().nodes)
    for node in ["plan", "gather", "process", "reflect", "synthesize", "persist"]:
        assert node in names


@pytest.mark.asyncio
async def test_run_research_produces_report_and_persists(fake_env, monkeypatch):
    _patch_llm(monkeypatch, reflect_enough=True)
    from app.storage.db import get_run

    events = [e async for e in run_research("what is python")]

    types = [e["type"] for e in events]
    assert "node" in types
    assert types[-1] == "done"

    reports = [e for e in events if e["type"] == "report"]
    assert len(reports) == 1
    report = reports[0]
    assert report["markdown"].strip()          # non-empty markdown
    assert report["run_id"] is not None         # persisted

    run = get_run(report["run_id"])
    assert run is not None
    assert run["query"] == "what is python"
    assert run["report_markdown"].strip()


@pytest.mark.asyncio
async def test_reflect_loop_capped_by_max_iterations(fake_env, monkeypatch):
    from app.config import settings
    spy = fake_env
    _patch_llm(monkeypatch, reflect_enough=False)  # never "enough" -> keep looping

    events = [e async for e in run_research("loop question")]

    # gather ran more than once (loop actually engaged) but is capped.
    assert spy.calls >= 2
    assert spy.calls <= settings.max_iterations + 1

    # Even when never satisfied, the run still terminates with a report.
    reports = [e for e in events if e["type"] == "report"]
    assert len(reports) == 1
    assert reports[0]["markdown"].strip()


@pytest.mark.asyncio
async def test_requested_sources_override_planner_autopick(monkeypatch, tmp_path):
    """Requesting sources=['wikipedia'] gathers ONLY wikipedia, even when the
    planner's LLM would auto-pick a different source ('news')."""
    import app.sources  # noqa: F401 - ensures REGISTRY is populated
    from app.sources import base as sources_base
    from app.config import settings
    from app.storage import db

    db_path = tmp_path / "research.db"
    monkeypatch.setattr(settings, "db_path", str(db_path))
    monkeypatch.setattr(settings, "max_iterations", 1)
    db.init_db(str(db_path))

    wiki = SpyAdapter()  # name == "wikipedia"

    class NewsSpy(SpyAdapter):
        name = "news"

    news = NewsSpy()
    monkeypatch.setitem(sources_base.REGISTRY, "wikipedia", wiki)
    monkeypatch.setitem(sources_base.REGISTRY, "news", news)

    # A planner that ALWAYS auto-picks "news" - the source the user did NOT ask
    # for. Before the fix this auto-pick won; now the user's choice wins.
    class AutoPickNewsLLM(FakeLLM):
        async def ainvoke(self, prompt, *args, **kwargs):
            if isinstance(prompt, str):
                text = prompt.lower()
            else:
                text = " ".join(
                    getattr(m, "content", str(m)) for m in prompt
                ).lower()
            if "subqueries" in text and "sources" in text:
                return FakeResponse(json.dumps({
                    "sources": ["news"],
                    "subqueries": {"news": ["auto picked query"]},
                    "reasoning": "auto-picked news",
                }))
            return await super().ainvoke(prompt, *args, **kwargs)

    fake = AutoPickNewsLLM(reflect_enough=True)

    def factory(provider=None, model=None, api_key=None):
        return fake

    import app.llm as llm_mod
    monkeypatch.setattr(llm_mod, "get_llm", factory)
    import app.agent.nodes as nodes_mod
    monkeypatch.setattr(nodes_mod, "get_llm", factory)

    events = [e async for e in run_research("q", sources=["wikipedia"])]

    # The user's selection is honored: wikipedia gathered, auto-picked news NOT.
    assert wiki.calls >= 1
    assert news.calls == 0

    # The run still completes and produces a report (event contract intact).
    reports = [e for e in events if e["type"] == "report"]
    assert len(reports) == 1
    assert reports[0]["markdown"].strip()
    assert reports[0]["run_id"] is not None


@pytest.mark.asyncio
async def test_no_requested_sources_uses_planner_autopick(fake_env, monkeypatch):
    """With no requested sources, the planner's auto-pick still drives gather."""
    spy = fake_env  # spy 'wikipedia' adapter; FakeLLM auto-picks 'wikipedia'
    _patch_llm(monkeypatch, reflect_enough=True)

    events = [e async for e in run_research("what is python")]  # no sources arg

    assert spy.calls >= 1  # auto-picked source was gathered
    reports = [e for e in events if e["type"] == "report"]
    assert len(reports) == 1
    assert reports[0]["markdown"].strip()


@pytest.mark.asyncio
async def test_run_research_emits_error_event_on_failure(monkeypatch):
    # Force build_graph (called inside run_research) to raise.
    import app.agent.graph as graph_mod

    def boom():
        raise RuntimeError("kaboom")

    monkeypatch.setattr(graph_mod, "build_graph", boom)

    events = [e async for e in graph_mod.run_research("x")]
    assert events == [{"type": "error", "message": "kaboom"}]

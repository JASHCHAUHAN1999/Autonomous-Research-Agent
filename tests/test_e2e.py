import json

import pytest
from fastapi.testclient import TestClient
from langchain_core.messages import AIMessage

from app import config
from app.agent import prompts
from app.sources.base import SourceResult, REGISTRY
from app.storage import db


# ---------------------------------------------------------------------------
# Deterministic fakes -- no network, no real LLM, no real search adapters.
# ---------------------------------------------------------------------------
class FakeLLM:
    """Stand-in for langchain_openai.ChatOpenAI. Returns canned content keyed
    by which system prompt the calling node embedded in its messages."""

    def _content(self, messages):
        text = " ".join((getattr(m, "content", "") or "") for m in messages)
        if prompts.SYNTH_SYSTEM in text:
            return (
                "# Research Report\n\n"
                "## Key Points\n- Fake key point about the topic.\n\n"
                "## Important Findings\n- Fake important finding.\n\n"
                "## References / Sources\n- https://example.com/wikipedia\n\n"
                "## Actionable Insights\n- Fake actionable insight.\n"
            )
        if prompts.REFLECT_SYSTEM in text:
            return json.dumps({"enough": True, "gaps": []})
        if prompts.FILTER_SYSTEM in text:
            return json.dumps({"keep": [0]})
        # default: planning
        return json.dumps(
            {
                "sources": ["wikipedia"],
                "subqueries": {"wikipedia": ["fake subquery"]},
                "reasoning": "fake planning reasoning",
            }
        )

    async def ainvoke(self, messages, *args, **kwargs):
        return AIMessage(content=self._content(messages))

    def invoke(self, messages, *args, **kwargs):
        return AIMessage(content=self._content(messages))


class FakeAdapter:
    """Stand-in SourceAdapter: always available, returns one canned result."""

    def __init__(self, name):
        self.name = name

    def available(self):
        return True

    async def search(self, query, limit=5, api_key=None):
        return [
            SourceResult(
                source=self.name,
                title=f"{self.name.title()} article about {query}",
                url=f"https://example.com/{self.name}",
                content=f"Deterministic content about {query} from {self.name}.",
                published_at="2026-01-01",
                score=0.9,
            )
        ]


@pytest.fixture
def client(tmp_path, monkeypatch):
    # 1) isolated temp sqlite db -- create_run/save_report read settings.db_path
    db_file = tmp_path / "e2e.db"
    monkeypatch.setattr(config.settings, "db_path", str(db_file))
    db.init_db(str(db_file))

    # 2) fake the LLM at the exact name the nodes call it by
    from app.agent import nodes

    monkeypatch.setattr(nodes, "get_llm", lambda provider=None, model=None, api_key=None: FakeLLM())

    # 3) fake search adapter under the registry key the fake planner will pick
    monkeypatch.setitem(REGISTRY, "wikipedia", FakeAdapter("wikipedia"))

    from app.main import app

    return TestClient(app)


def _parse_sse(raw: str):
    """Parse an SSE body ('data: {json}\\n\\n' frames) into a list of events."""
    events = []
    for frame in raw.split("\n\n"):
        frame = frame.strip()
        if frame.startswith("data:"):
            events.append(json.loads(frame[len("data:"):].strip()))
    return events


def test_e2e_research_history_and_export(client):
    # --- POST /api/research (SSE stream) -----------------------------------
    resp = client.post("/api/research", json={"query": "quantum computing"})
    assert resp.status_code == 200

    events = _parse_sse(resp.text)
    types = [e["type"] for e in events]
    assert "node" in types            # progress events were emitted
    assert "report" in types          # a report was produced
    assert types[-1] == "done"        # stream terminated cleanly
    assert "error" not in types

    report = next(e for e in events if e["type"] == "report")
    assert "Key Points" in report["markdown"]
    run_id = report["run_id"]
    assert isinstance(run_id, int)

    # --- GET /api/history (list) -------------------------------------------
    hist = client.get("/api/history")
    assert hist.status_code == 200
    runs = hist.json()["runs"]
    assert any(r["id"] == run_id for r in runs)

    # --- GET /api/history/{id} (detail) ------------------------------------
    detail = client.get(f"/api/history/{run_id}")
    assert detail.status_code == 200
    data = detail.json()
    assert data["query"] == "quantum computing"
    assert "Key Points" in data["report_markdown"]
    assert len(data["sources"]) >= 1

    # --- GET /api/export?format=md -----------------------------------------
    md = client.get(f"/api/export/{run_id}?format=md")
    assert md.status_code == 200
    assert "text/markdown" in md.headers["content-type"]
    assert "attachment" in md.headers.get("content-disposition", "")
    assert "Key Points" in md.text

    # --- GET /api/export?format=pdf ----------------------------------------
    pdf = client.get(f"/api/export/{run_id}?format=pdf")
    assert pdf.status_code == 200
    assert "application/pdf" in pdf.headers["content-type"]
    assert pdf.content.startswith(b"%PDF")


def test_e2e_missing_run_returns_404(client):
    assert client.get("/api/history/999999").status_code == 404

# tests/test_api.py
import httpx
import pytest
from fastapi.testclient import TestClient

import app.main as main_module
from app.main import app
from app.config import settings
from app.storage import db
from app.sources.base import SourceResult
from app.models import ModelInfo


SEED_QUERY = "What is quantum computing?"


@pytest.fixture
def client(tmp_path, monkeypatch):
    # Point the DB at an isolated temp file, create tables, seed one finished run.
    db_file = tmp_path / "test.db"
    monkeypatch.setattr(settings, "db_path", str(db_file))
    db.init_db()  # reads settings.db_path
    run_id = db.create_run(SEED_QUERY, "openai", "gpt-4o-mini")
    db.save_report(
        run_id,
        "# Report\n\nQuantum computing uses qubits and superposition.",
        [
            SourceResult(
                source="wikipedia",
                title="Quantum computing",
                url="https://en.wikipedia.org/wiki/Quantum_computing",
                content="Qubits, superposition and entanglement.",
            )
        ],
        status="done",
    )
    # `with` fires the lifespan startup (which calls init_db() again — idempotent).
    with TestClient(app) as c:
        c.seeded_run_id = run_id
        yield c


def test_providers(client, monkeypatch):
    monkeypatch.setattr(main_module, "list_providers", lambda: ["openai", "openrouter"])
    resp = client.get("/api/providers")
    assert resp.status_code == 200
    assert resp.json() == {"providers": ["openai", "openrouter"]}


def test_models(client, monkeypatch):
    async def fake_list_models(provider, api_key=None):
        assert provider == "openai"
        return [
            ModelInfo(id="gpt-4o-mini", name="gpt-4o-mini", free=False),
            ModelInfo(id="free-model", name="Free Model", free=True, context_length=8000),
        ]

    monkeypatch.setattr(main_module, "list_models", fake_list_models)
    resp = client.get("/api/models", params={"provider": "openai"})
    assert resp.status_code == 200
    models = resp.json()["models"]
    assert models[0]["id"] == "gpt-4o-mini"
    assert models[0]["free"] is False
    assert models[1]["free"] is True
    assert models[1]["context_length"] == 8000


def test_models_graceful_error(client, monkeypatch):
    # Carry-forward fix: list_models raises httpx.HTTPStatusError (e.g. an invalid
    # provider key -> 401). The endpoint must degrade gracefully, never 500.
    async def raising_list_models(provider, api_key=None):
        raise httpx.HTTPStatusError(
            "401 Unauthorized",
            request=httpx.Request("GET", "https://api.openai.com/v1/models"),
            response=httpx.Response(401),
        )

    monkeypatch.setattr(main_module, "list_models", raising_list_models)
    resp = client.get("/api/models", params={"provider": "openai"})
    assert resp.status_code == 200
    assert resp.json()["models"] == []


def test_research_sse(client, monkeypatch):
    async def fake_run_research(query, provider=None, model=None, sources=None, api_key=None, source_keys=None):
        assert query == "capital of France"
        yield {"type": "node", "node": "plan", "detail": "planning"}
        yield {"type": "node", "node": "gather", "detail": "gathering"}
        yield {"type": "report", "markdown": "# Answer\n\nParis is the capital.", "run_id": 42}
        yield {"type": "done"}

    monkeypatch.setattr(main_module, "run_research", fake_run_research)
    resp = client.post("/api/research", json={"query": "capital of France"})
    assert resp.status_code == 200
    assert resp.headers["content-type"].startswith("text/event-stream")
    text = resp.text
    assert "data:" in text
    assert "Paris is the capital." in text
    assert '"type": "done"' in text


def test_history_list(client):
    resp = client.get("/api/history")
    assert resp.status_code == 200
    runs = resp.json()["runs"]
    assert any(r["id"] == client.seeded_run_id for r in runs)
    seeded = next(r for r in runs if r["id"] == client.seeded_run_id)
    assert seeded["query"] == SEED_QUERY


def test_history_detail(client):
    resp = client.get(f"/api/history/{client.seeded_run_id}")
    assert resp.status_code == 200
    body = resp.json()
    assert body["query"] == SEED_QUERY
    assert "qubits" in body["report_markdown"]
    assert body["sources"][0]["source"] == "wikipedia"


def test_history_detail_404(client):
    resp = client.get("/api/history/999999")
    assert resp.status_code == 404


def test_export_md(client):
    resp = client.get(f"/api/export/{client.seeded_run_id}", params={"format": "md"})
    assert resp.status_code == 200
    assert "text/markdown" in resp.headers["content-type"]
    assert "attachment" in resp.headers["content-disposition"]
    assert SEED_QUERY in resp.text


def test_export_pdf(client):
    resp = client.get(f"/api/export/{client.seeded_run_id}", params={"format": "pdf"})
    assert resp.status_code == 200
    assert "application/pdf" in resp.headers["content-type"]
    assert "attachment" in resp.headers["content-disposition"]
    assert resp.content.startswith(b"%PDF")


def test_export_404(client):
    resp = client.get("/api/export/999999", params={"format": "md"})
    assert resp.status_code == 404


def test_models_passes_api_key(client, monkeypatch):
    # An api_key on the query string must be threaded into list_models.
    captured = {}

    async def fake_list_models(provider, api_key=None):
        captured["provider"] = provider
        captured["api_key"] = api_key
        return [ModelInfo(id="m", name="m", free=True)]

    monkeypatch.setattr(main_module, "list_models", fake_list_models)
    resp = client.get(
        "/api/models", params={"provider": "openrouter", "api_key": "ui-key"}
    )
    assert resp.status_code == 200
    assert captured == {"provider": "openrouter", "api_key": "ui-key"}


def test_research_passes_api_key(client, monkeypatch):
    # An api_key in the POST body must be threaded into run_research.
    captured = {}

    async def fake_run_research(
        query, provider=None, model=None, sources=None, api_key=None, source_keys=None
    ):
        captured["api_key"] = api_key
        yield {"type": "report", "markdown": "ok", "run_id": 1}
        yield {"type": "done"}

    monkeypatch.setattr(main_module, "run_research", fake_run_research)
    resp = client.post("/api/research", json={"query": "q", "api_key": "ui-key"})
    assert resp.status_code == 200
    assert captured["api_key"] == "ui-key"


def test_research_passes_source_keys(client, monkeypatch):
    # Per-source keys in the POST body must be threaded into run_research.
    captured = {}

    async def fake_run_research(
        query, provider=None, model=None, sources=None, api_key=None, source_keys=None
    ):
        captured["source_keys"] = source_keys
        yield {"type": "report", "markdown": "ok", "run_id": 1}
        yield {"type": "done"}

    monkeypatch.setattr(main_module, "run_research", fake_run_research)
    resp = client.post(
        "/api/research", json={"query": "q", "source_keys": {"tavily": "tk"}}
    )
    assert resp.status_code == 200
    assert captured["source_keys"] == {"tavily": "tk"}

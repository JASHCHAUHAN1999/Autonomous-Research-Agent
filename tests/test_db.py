# tests/test_db.py
from app.sources.base import SourceResult
from app.storage import db


def test_create_run_returns_id_and_running_status(tmp_db):
    run_id = db.create_run("What is RAG?", "openai", "gpt-4o-mini")
    assert isinstance(run_id, int)
    assert run_id > 0

    run = db.get_run(run_id)
    assert run is not None
    assert run["query"] == "What is RAG?"
    assert run["provider"] == "openai"
    assert run["model"] == "gpt-4o-mini"
    assert run["status"] == "running"
    assert run["report_markdown"] is None
    assert run["sources"] == []
    assert run["created_at"]  # non-empty timestamp string


def test_save_report_roundtrip(tmp_db):
    run_id = db.create_run("history of python", "openai", "gpt-4o-mini")
    sources = [
        SourceResult(
            source="wikipedia",
            title="Python (programming language)",
            url="https://en.wikipedia.org/wiki/Python",
            content="x" * 800,
            published_at=None,
            score=0.9,
        ),
        SourceResult(
            source="web",
            title="Docs",
            url="https://docs.python.org",
            content="short body",
        ),
    ]
    db.save_report(run_id, "# Report\n\nSome findings.", sources)

    run = db.get_run(run_id)
    assert run is not None
    assert run["status"] == "done"
    assert run["report_markdown"] == "# Report\n\nSome findings."
    assert len(run["sources"]) == 2

    first = run["sources"][0]
    assert first["source"] == "wikipedia"
    assert first["title"] == "Python (programming language)"
    assert first["url"] == "https://en.wikipedia.org/wiki/Python"
    # snippet is content truncated to 500 chars
    assert len(first["snippet"]) == 500
    assert set(first.keys()) == {"source", "title", "url", "snippet"}

    assert run["sources"][1]["snippet"] == "short body"


def test_save_report_custom_status(tmp_db):
    run_id = db.create_run("q", "openai", "gpt-4o-mini")
    db.save_report(run_id, "partial", [], status="error")

    run = db.get_run(run_id)
    assert run["status"] == "error"
    assert run["report_markdown"] == "partial"
    assert run["sources"] == []


def test_list_runs_newest_first(tmp_db):
    id1 = db.create_run("first", "openai", "gpt-4o-mini")
    id2 = db.create_run("second", "openrouter", "meta-llama/llama-3-8b")
    id3 = db.create_run("third", "openai", "gpt-4o-mini")

    runs = db.list_runs()
    assert [r["id"] for r in runs] == [id3, id2, id1]
    assert runs[0]["query"] == "third"
    assert set(runs[0].keys()) == {
        "id",
        "query",
        "created_at",
        "model",
        "provider",
        "status",
    }


def test_get_run_missing_returns_none(tmp_db):
    assert db.get_run(9999) is None

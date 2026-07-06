# tests/test_exporter.py
from app.export.exporter import _fix_chars, to_markdown, to_pdf


def _sample_run() -> dict:
    """A run dict shaped exactly like app.storage.db.get_run() returns."""
    return {
        "id": 1,
        "query": "Impact of AI on jobs",
        "created_at": "2026-07-06 12:00:00",
        "model": "gpt-4o-mini",
        "provider": "openai",
        "status": "done",
        "report_markdown": (
            "## Key Points\n\n"
            "AI will change the labor market significantly.\n"
        ),
        "sources": [
            {
                "source": "wikipedia",
                "title": "Artificial intelligence",
                "url": "https://en.wikipedia.org/wiki/Artificial_intelligence",
                "snippet": "AI is intelligence demonstrated by machines.",
            },
            {
                "source": "news",
                "title": "AI and the future of work",
                "url": "https://example.com/ai-work",
                "snippet": "A look at automation trends.",
            },
        ],
    }


def test_to_markdown_contains_query_report_and_source_link():
    run = _sample_run()
    md = to_markdown(run)

    # Title is the query as an H1
    assert "# Impact of AI on jobs" in md
    # Metadata line mentions model and created_at
    assert "gpt-4o-mini" in md
    assert "2026-07-06 12:00:00" in md
    # The report body is included verbatim
    assert "AI will change the labor market significantly." in md
    # A Sources section with markdown links per source
    assert "## Sources" in md
    assert (
        "[Artificial intelligence]"
        "(https://en.wikipedia.org/wiki/Artificial_intelligence)"
    ) in md
    assert "[AI and the future of work](https://example.com/ai-work)" in md


def test_to_markdown_handles_missing_sources():
    run = _sample_run()
    run["sources"] = []
    run["report_markdown"] = None  # persist may leave this empty
    md = to_markdown(run)

    assert "# Impact of AI on jobs" in md
    assert "## Sources" in md
    # Should not raise and should still be a non-empty string
    assert isinstance(md, str) and md.strip()


def test_to_pdf_returns_pdf_bytes():
    run = _sample_run()
    data = to_pdf(run)

    assert isinstance(data, bytes)
    assert len(data) > 0
    assert data.startswith(b"%PDF")


def test_fix_chars_replaces_box_causing_characters():
    # The non-breaking hyphen (U+2011) is what rendered as a black box in the PDF.
    assert _fix_chars("Solid‑State") == "Solid-State"
    assert _fix_chars("2024‑2025") == "2024-2025"
    # Zero-width space is stripped entirely.
    assert _fix_chars("a​b") == "ab"


def test_to_pdf_handles_special_characters_without_crashing():
    # A report full of the glyphs that previously produced black boxes must
    # still render to a valid PDF (embedded Unicode font + _fix_chars fallback).
    run = _sample_run()
    run["report_markdown"] = (
        "## Key Points\n\n"
        "- Solid‑State batteries (2024‑2025) — “big” news.\n"
        "- Cross‑Reference power‑and‑renewables trends.\n"
    )
    data = to_pdf(run)
    assert isinstance(data, bytes) and data.startswith(b"%PDF")
    assert len(data) > 0

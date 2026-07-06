# app/storage/db.py
"""SQLite persistence for research runs and their sources (stdlib sqlite3)."""
from __future__ import annotations

import sqlite3
from datetime import datetime

from app.config import settings
from app.sources.base import SourceResult


def _connect(path: str | None = None) -> sqlite3.Connection:
    """Open a connection to the given path, or settings.db_path when None."""
    conn = sqlite3.connect(path or settings.db_path)
    conn.row_factory = sqlite3.Row
    return conn


def init_db(path: str | None = None) -> None:
    """Create the runs and sources tables if they do not already exist."""
    conn = _connect(path)
    try:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS runs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                query TEXT NOT NULL,
                created_at TEXT NOT NULL,
                model TEXT,
                provider TEXT,
                status TEXT NOT NULL,
                report_markdown TEXT
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS sources (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                run_id INTEGER NOT NULL,
                source TEXT,
                title TEXT,
                url TEXT,
                snippet TEXT,
                FOREIGN KEY (run_id) REFERENCES runs(id)
            )
            """
        )
        conn.commit()
    finally:
        conn.close()


def create_run(query: str, provider: str, model: str) -> int:
    """Insert a new run with status 'running'; return its row id."""
    conn = _connect()
    try:
        created_at = datetime.now().isoformat(timespec="seconds")
        cur = conn.execute(
            "INSERT INTO runs (query, created_at, model, provider, status, report_markdown) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            (query, created_at, model, provider, "running", None),
        )
        conn.commit()
        return int(cur.lastrowid)
    finally:
        conn.close()


def save_report(
    run_id: int,
    report_markdown: str,
    sources: list[SourceResult],
    status: str = "done",
) -> None:
    """Store the report + status on the run and insert one row per source."""
    conn = _connect()
    try:
        conn.execute(
            "UPDATE runs SET report_markdown = ?, status = ? WHERE id = ?",
            (report_markdown, status, run_id),
        )
        for r in sources:
            snippet = (r.content or "")[:500]
            conn.execute(
                "INSERT INTO sources (run_id, source, title, url, snippet) "
                "VALUES (?, ?, ?, ?, ?)",
                (run_id, r.source, r.title, r.url, snippet),
            )
        conn.commit()
    finally:
        conn.close()


def list_runs() -> list[dict]:
    """Return run summaries, newest first."""
    conn = _connect()
    try:
        rows = conn.execute(
            "SELECT id, query, created_at, model, provider, status "
            "FROM runs ORDER BY created_at DESC, id DESC"
        ).fetchall()
        return [
            {
                "id": row["id"],
                "query": row["query"],
                "created_at": row["created_at"],
                "model": row["model"],
                "provider": row["provider"],
                "status": row["status"],
            }
            for row in rows
        ]
    finally:
        conn.close()


def get_run(run_id: int) -> dict | None:
    """Return a run with its nested sources, or None if not found."""
    conn = _connect()
    try:
        row = conn.execute(
            "SELECT id, query, created_at, model, provider, status, report_markdown "
            "FROM runs WHERE id = ?",
            (run_id,),
        ).fetchone()
        if row is None:
            return None
        source_rows = conn.execute(
            "SELECT source, title, url, snippet FROM sources "
            "WHERE run_id = ? ORDER BY id ASC",
            (run_id,),
        ).fetchall()
        return {
            "id": row["id"],
            "query": row["query"],
            "created_at": row["created_at"],
            "model": row["model"],
            "provider": row["provider"],
            "status": row["status"],
            "report_markdown": row["report_markdown"],
            "sources": [
                {
                    "source": s["source"],
                    "title": s["title"],
                    "url": s["url"],
                    "snippet": s["snippet"],
                }
                for s in source_rows
            ],
        }
    finally:
        conn.close()

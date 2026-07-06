# app/main.py
from __future__ import annotations

import json
from contextlib import asynccontextmanager
from dataclasses import asdict
from pathlib import Path

from fastapi import FastAPI, HTTPException, Query, Request
from fastapi.responses import FileResponse, HTMLResponse, Response, StreamingResponse
from fastapi.staticfiles import StaticFiles

from app.agent.graph import run_research
from app.export.exporter import to_markdown, to_pdf
from app.models import list_models, list_providers
from app.storage.db import get_run, init_db, list_runs

BASE_DIR = Path(__file__).resolve().parent
STATIC_DIR = BASE_DIR / "static"
# Ensure the static directory exists so the mount below never fails on a fresh checkout.
STATIC_DIR.mkdir(parents=True, exist_ok=True)


@asynccontextmanager
async def lifespan(_app: FastAPI):
    # Create the SQLite tables (idempotent) using the currently configured db_path.
    init_db()
    yield


app = FastAPI(title="Autonomous Research Agent", lifespan=lifespan)

app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")


@app.get("/api/providers")
def api_providers() -> dict:
    return {"providers": list_providers()}


@app.get("/api/models")
async def api_models(provider: str, api_key: str | None = None) -> dict:
    # An optional api_key (entered in the UI) overrides the .env key for this
    # request only; it is never stored server-side.
    # Carry-forward fix: list_models raises httpx.HTTPStatusError when a provider
    # key is present but invalid (401). The UI must never see a 500, so degrade
    # gracefully to an empty list plus a clean error payload.
    try:
        models = await list_models(provider, api_key=api_key or None)
    except Exception as exc:  # noqa: BLE001 - any upstream failure -> graceful empty
        return {"models": [], "error": str(exc)}
    return {"models": [asdict(m) for m in models]}


@app.post("/api/research")
async def api_research(request: Request) -> StreamingResponse:
    body = await request.json()
    query = body.get("query", "")
    provider = body.get("provider")
    model = body.get("model")
    sources = body.get("sources")
    api_key = body.get("api_key")  # optional UI-entered LLM key; overrides .env
    source_keys = body.get("source_keys") or {}  # per-source UI keys (tavily/news)

    async def event_stream():
        async for event in run_research(
            query,
            provider=provider,
            model=model,
            sources=sources,
            api_key=api_key,
            source_keys=source_keys,
        ):
            yield "data: " + json.dumps(event) + "\n\n"

    return StreamingResponse(event_stream(), media_type="text/event-stream")


@app.get("/api/history")
def api_history() -> dict:
    return {"runs": list_runs()}


@app.get("/api/history/{run_id}")
def api_history_detail(run_id: int) -> dict:
    run = get_run(run_id)
    if run is None:
        raise HTTPException(status_code=404, detail="run not found")
    return run


@app.get("/api/export/{run_id}")
def api_export(run_id: int, fmt: str = Query("md", alias="format")) -> Response:
    run = get_run(run_id)
    if run is None:
        raise HTTPException(status_code=404, detail="run not found")
    if fmt == "pdf":
        return Response(
            content=to_pdf(run),
            media_type="application/pdf",
            headers={
                "Content-Disposition": f'attachment; filename="research_{run_id}.pdf"'
            },
        )
    return Response(
        content=to_markdown(run),
        media_type="text/markdown",
        headers={
            "Content-Disposition": f'attachment; filename="research_{run_id}.md"'
        },
    )


@app.get("/")
def index() -> Response:
    # index.html is produced by the frontend task (Task 16); guard so a fresh
    # checkout without it serves a placeholder instead of raising a 500.
    index_file = STATIC_DIR / "index.html"
    if index_file.is_file():
        return FileResponse(str(index_file))
    return HTMLResponse(
        "<!DOCTYPE html><html><body>"
        "<h1>Autonomous Research Agent</h1>"
        "<p>Frontend not built yet. API is available under <code>/api</code>.</p>"
        "</body></html>"
    )

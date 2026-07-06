# Autonomous Research Agent

An autonomous, multi-source research agent. Give it a question; it **plans** which
sources to use, **gathers** evidence from several providers concurrently,
**deduplicates & filters** the results, **reflects** on whether the evidence is
sufficient (looping to gather more if not), **synthesizes** a structured Markdown
report, and **persists** the run. A single-page web UI streams live progress,
renders the report, and lets you export to Markdown or PDF and browse history.

Built with **FastAPI**, **LangGraph**, **LangChain** (OpenAI / OpenRouter), stdlib
**sqlite3**, and a zero-build Tailwind + marked.js frontend.

> **All API keys are entered in the web UI** (the LLM provider key plus optional
> Tavily / NewsAPI keys). They are session-only, sent per request, and **never
> stored on the server**. No `.env` keys are needed — the `.env` file is optional
> and holds only non-secret defaults.

> 📖 **Full documentation:** [`docs/DOCUMENTATION.md`](docs/DOCUMENTATION.md)
> (also available as `docs/DOCUMENTATION.pdf` and `docs/DOCUMENTATION.docx`) —
> covers the build process, every component, the exact agent prompts, and the API.

---

## Feature checklist (requirements → implementation)

| # | Requirement | Where | Status |
|---|-------------|-------|--------|
| 1 | Multi-step autonomous agent (plan → act → reflect → synthesize) | `app/agent/graph.py`, `app/agent/nodes.py` | ✅ |
| 2 | Multiple heterogeneous sources | `app/sources/{tavily,wikipedia,news,web_scraper}.py` | ✅ |
| 3 | LLM-driven planning & synthesis | `app/agent/nodes.py`, `app/agent/prompts.py` | ✅ |
| 4 | Deduplication & relevance filtering | `app/processing/dedupe.py` | ✅ |
| 5 | Structured report (Key Points / Important Findings / References / Actionable Insights) | `build_synth_prompt` in `app/agent/prompts.py` | ✅ |
| 6 | Persistence & run history | `app/storage/db.py` (sqlite3) | ✅ |
| 7 | Report export (Markdown **and** PDF) | `app/export/exporter.py` (`to_markdown`, `to_pdf`) | ✅ |
| 8 | Web UI | `app/static/index.html`, `app/static/app.js` | ✅ |
| 9 | REST + streaming API | `app/main.py` (FastAPI) | ✅ |

### Bonus / extra features

| Feature | Where | Status |
|---------|-------|--------|
| LLM autonomously selects sources | `plan_node` + `PLAN_SYSTEM` + `available_sources()` | ✅ |
| Parallel gathering across sources | `gather_node` (`asyncio.gather`) | ✅ |
| Live model picker with **Free/Paid** badges (loaded from your key) | `app/models.py`, `GET /api/models`, `app/static/app.js` | ✅ |
| Multi-provider (OpenAI **and** OpenRouter) | `app/llm.py`, `app/config.py` | ✅ |
| Live streaming progress (SSE via `fetch` + `ReadableStream`) | `POST /api/research`, `app/static/app.js` | ✅ |
| Iterative reflection loop (up to `MAX_ITERATIONS`) | `route_after_reflect` in `app/agent/nodes.py` | ✅ |
| **All keys entered in the UI**, session-only, key-gated sources | `app/main.py`, `available_sources(keys)`, `app/static/app.js` | ✅ |

---

## Architecture

```text
                         Browser (SPA)
        index.html + app.js  ·  Tailwind + marked.js (CDN)
                              │  keys + query (session-only)
                              │  fetch(POST) + ReadableStream (SSE)
                              ▼
┌─────────────────────────────────────────────────────────────┐
│                        FastAPI (app/main.py)                  │
│  /api/providers  /api/models  /api/research(SSE)              │
│  /api/history    /api/history/{id}   /api/export/{id}         │
└───────────────┬───────────────────────────────┬──────────────┘
                │ run_research()                 │ list_runs/get_run
                ▼                                 ▼
┌───────────────────────────────┐     ┌──────────────────────────┐
│   LangGraph agent (agent/)    │     │  sqlite3 storage (db.py) │
│  plan→gather→process→reflect  │────▶│   runs + sources tables  │
│      →(loop)→synth→persist    │     └──────────────────────────┘
└───────┬───────────────┬───────┘
        │ get_llm()      │ adapters (sources/base REGISTRY, key-gated)
        ▼                ▼
┌────────────────┐  ┌──────────────────────────────────────────┐
│ OpenAI /       │  │ tavily · wikipedia · news · web            │
│ OpenRouter LLM │  │ (httpx.AsyncClient, run via asyncio.gather)│
└────────────────┘  └──────────────────────────────────────────┘
        │
        ▼
   export/exporter.py  →  Markdown / PDF (markdown → HTML → xhtml2pdf)
```

### LangGraph flow

```text
  START
    │
    ▼
  plan ──▶ gather ──▶ process ──▶ reflect
             ▲                       │
             │                       │ route_after_reflect(state)
             │                       ▼
             │        ┌──────────────────────────────┐
             └────────┤ not reflection.enough AND    │
   (loop, iteration++)│ iteration < MAX_ITERATIONS   │──▶ gather
                      └──────────────────────────────┘
                                     │
                                     │ enough OR iteration limit reached
                                     ▼
                                 synthesize ──▶ persist ──▶ END
```

Nodes each take a `ResearchState` and return a partial-state dict:
`plan_node` → `gather_node` → `process_node` (dedupe + relevance) →
`reflect_node` → **conditional** → `synthesize_node` → `persist_node`.
The LLM provider key and per-source keys are carried **inside the state** and
threaded to each node — nothing reads secrets from globals.

---

## Setup

Requires **Python 3.12** (a virtualenv is created at `.venv`). Invoke the venv
interpreter explicitly — no activation needed.

```powershell
# Windows (PowerShell)
py -3.12 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
```

```bash
# macOS / Linux (or Git Bash on Windows)
python3.12 -m venv .venv
.venv/bin/python -m pip install -r requirements.txt      # (.venv/Scripts/python.exe on Git Bash)
```

**No API keys are needed to install or start the app** — you enter them in the UI.
There is nothing to configure in `.env`.

### Configuration (`.env` is optional)

`.env` holds only **non-secret defaults** (all have built-in fallbacks). You can
run without a `.env` at all, and you can safely delete it.

| Variable | Default | Purpose |
|----------|---------|---------|
| `MODEL` | `gpt-4o-mini` | Fallback model id when a request doesn't specify one (the UI model picker overrides it). |
| `MAX_ITERATIONS` | `2` | Max gather↔reflect loops before forcing synthesis. |
| `DB_PATH` | `research.db` | SQLite file path for run history. |

API keys are **not** read from `.env` — the OpenAI/OpenRouter key and the Tavily /
NewsAPI keys are entered in the web UI.

---

## Run

```powershell
.\.venv\Scripts\python.exe -m uvicorn app.main:app --reload
```

Then open <http://127.0.0.1:8000/>.

---

## Using the UI

1. **Provider** — pick `openrouter` or `openai` (both are always available).
2. **API key** — paste that provider's API key into the masked **API key** field,
   then click **Load models**. The model list is fetched **using your key** and
   each model shows a **Free** / **Paid** badge; type in the filter box to narrow it.
3. **Source keys (optional)** — paste a **Tavily** and/or **NewsAPI** key to unlock
   those sources. Their **Sources** checkboxes stay disabled until you do.
   `wikipedia` and `web` need no key and are always available.
4. **Query** — type your research question.
5. **Sources** — optionally tick specific sources, or leave all unchecked to let
   the agent auto-pick from the ones you have keys for. For **web**, the agent
   treats each subquery entry as a URL to fetch.
6. **Research** — click to start. The progress timeline updates live as each node
   runs (`plan → gather → process → reflect → …`); the report renders when done.
7. **Export** — use the Markdown / PDF buttons (`/api/export/{id}?format=md|pdf`).
8. **History** — the sidebar lists prior runs; click one to re-open it without
   re-running.

All keys stay in your browser for the session only, are sent to your **local**
backend per request, and are never stored. (This is intended for local,
single-user use — don't expose it publicly with browser-entered keys.)

---

## Running the tests

All tests are fully offline — LLM calls and HTTP sources are faked (`respx` mocks
`httpx`), and the DB is a temp file. No real keys or network are required.

```powershell
.\.venv\Scripts\python.exe -m pytest -q                     # whole suite (106 tests)
.\.venv\Scripts\python.exe -m pytest tests/test_e2e.py -v   # end-to-end acceptance test
.\.venv\Scripts\python.exe -m pytest tests/test_llm.py::test_get_llm_sets_temperature_for_normal_model -v   # one test
```

The end-to-end test (`tests/test_e2e.py`) drives the real FastAPI app with a
`TestClient`, a temp sqlite DB, a deterministic fake LLM, and a fake search
adapter — it asserts `POST /api/research` streams a report, the run persists and
appears in `/api/history`, and Markdown + PDF export succeed.

---

## Project structure

```text
Autonomous Rsrch Agt/
├── app/
│   ├── config.py              # settings + provider helpers (non-secret defaults)
│   ├── llm.py                 # get_llm() -> ChatOpenAI (+ temperature rules)
│   ├── models.py              # live model discovery (+ TTL cache)
│   ├── main.py                # FastAPI app + routes + static mount
│   ├── sources/
│   │   ├── __init__.py        # imports all adapters -> populates REGISTRY
│   │   ├── base.py            # SourceResult, adapter protocol, REGISTRY, available_sources(keys)
│   │   ├── tavily.py  wikipedia.py  news.py  web_scraper.py
│   ├── processing/dedupe.py   # dedupe() + filter_relevant() (fails open)
│   ├── storage/db.py          # sqlite3 runs + sources
│   ├── agent/
│   │   ├── state.py           # Plan, ResearchState TypedDicts
│   │   ├── prompts.py         # *_SYSTEM + build_*_prompt()
│   │   ├── nodes.py           # plan/gather/process/reflect/synth/persist (+ backoff)
│   │   └── graph.py           # build_graph(), run_research()
│   ├── export/exporter.py     # to_markdown(), to_pdf() (designed, font-by-name)
│   └── static/index.html app.js   # no-build SPA
├── tests/                     # pytest suite (hermetic); test_e2e.py = acceptance test
├── docs/
│   ├── DOCUMENTATION.md       # full documentation (+ .pdf / .docx)
│   └── superpowers/           # design specs + implementation plan (historical record)
├── requirements.txt
├── pytest.ini                 # asyncio_mode = auto
├── .env.example               # non-secret defaults only (keys go in the UI)
├── CLAUDE.md
└── README.md
```

---

## Notes

- **All keys are entered in the UI, session-only.** The LLM provider key and the
  Tavily / NewsAPI keys are held in browser memory, sent per request, and never
  persisted server-side. `.env` is optional and holds only non-secret defaults.
- **Key-gated sources.** `available_sources(keys)` returns a source only if it
  needs no key (`wikipedia`, `web`) or you supplied its key this request, so the
  agent is never offered a source it can't use. With no keys it uses Wikipedia +
  Web; add a Tavily/NewsAPI key to unlock those.
- **Graceful degradation.** A per-source failure is recorded and skipped (never
  aborts a run); transient LLM rate-limits (429/502) are retried with backoff;
  relevance filtering fails open (keeps the deduped results) if its LLM call errors.
- **Model compatibility.** `get_llm` omits the `temperature` parameter for models
  that reject it (OpenAI `*-search-preview` and the o1/o3/o4 reasoning models),
  which otherwise return HTTP 400.
- **Windows-friendly PDF.** Export uses `xhtml2pdf` (pure-Python Markdown→HTML→PDF)
  — no `wkhtmltopdf`, GTK/Cairo, or headless browser. It embeds a Unicode system
  font so reports render without missing-glyph boxes; the bytes begin with `%PDF`.
- **No version control.** This project intentionally ships **without git**. Treat
  the folder as a self-contained deliverable.

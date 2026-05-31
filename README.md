# Diamond Miner

Diamond Miner is a local FastAPI application for document risk analysis. It ingests uploaded documents, extracts a knowledge graph with LLM-backed agents, identifies structural conflicts, hub fragility, and schedule issues, then presents the results in a browser-based 3D Spatial Canvas and report views.

## What It Does

- Uploads supported document types for analysis.
- Parses documents into chunks with source provenance.
- Stores chunk text in ChromaDB and graph topology in SQLite.
- Uses analysis agents to detect contradictions, fragility points, and chronological conflicts.
- Provides report endpoints for friction queues, bottlenecks, schedule collapse, risk matrices, executive summaries, narrative reports, and simulations.
- Exports narrative reports to PDF and DOCX.
- Serves a single-file vanilla JavaScript frontend from `static/index.html`.

## Requirements

Install Python dependencies from:

```powershell
python -m pip install -r requirements.txt
```

Pinned dependency versions are project decisions and should be treated as intentional.

Important runtime dependencies include FastAPI, Uvicorn, ChromaDB, PyMuPDF, OpenAI SDK, NumPy, WeasyPrint, python-docx, openpyxl, python-pptx, and pytest.

## Configuration

Runtime configuration is read from environment variables and `.env` when present.

Common variables:

```text
OPENAI_API_KEY
OPENROUTER_API_KEY
LLM_PROVIDER
FAST_MODEL
SMART_MODEL
VAULT_PATH
DIAMOND_MINER_PORT
DIAMOND_MINER_STOP_STALE_SERVER
DIAMOND_MINER_FORCE_STOP_PORT_PROCESS
```

`LLM_PROVIDER` defaults to `openai`. OpenRouter is supported through the OpenAI-compatible SDK path.

## Running Locally

Start the app with:

```powershell
python run.py
```

By default, the app starts at:

```text
http://localhost:8000
```

`run.py` creates required local directories (`vaults`, `static`, and `temp_uploads`) and checks that the configured port is available before starting Uvicorn.

## Testing

Run the full test suite:

```powershell
pytest tests/
```

Run the deterministic evaluation quality gate:

```powershell
python -m pytest -m evaluation -q
```

Live model evaluation is intentionally opt-in:

```powershell
set DIAMOND_MINER_LIVE_EVALUATION=1
python -m pytest -m live_evaluation -q
```

Tests are expected to mock LLM calls unless they are explicitly marked as live evaluation.

Run the V2 frontend checks:

```powershell
cd frontend
npm.cmd run typecheck
npm.cmd run test
npm.cmd run build
npm.cmd run e2e
```

`npm.cmd run e2e` uses Playwright against the FastAPI-served `/app-v2` route. It starts `python ../run.py` when no compatible local server is already running and intentionally avoids report-generation buttons that can trigger live model work.

## Project Layout

```text
api.py                 FastAPI application, routes, SSE report flows, shared vault
run.py                 Local startup script and port handling
core/                  Backend domain modules
static/index.html      Single-file vanilla JavaScript frontend
frontend/              Vite React TypeScript beta frontend for /app-v2
templates/             Report/export templates
tests/                 Pytest suite
docs/                  Design notes and implementation plans
vaults/                Generated local SQLite/ChromaDB data
temp_uploads/          Generated temporary upload files
```

The main Diamond Miner app is `api.py`, launched through `run.py`. Do not treat unrelated sample files as the app entry point unless their purpose has been confirmed.

## Architecture Summary

The application is organized around a small set of layers:

- `api.py` owns HTTP routes, static file serving, in-memory job tracking, and SSE streams.
- `core/orchestrator.py` parses uploaded files and coordinates ingestion.
- `core/agents.py` wraps LLM-backed extraction and analysis agents.
- `core/vault.py` persists document chunks, graph topology, analysis outputs, and cached reports.
- `core/simulator.py` computes blast radius, black swan scenarios, and Monte Carlo forecasts.
- `core/report_assembler.py` builds export payloads for report generation.

Persistence is local and tenant-scoped under `vaults/{tenant_id}/`, combining SQLite with ChromaDB.

## Development Notes

- Keep API routes and frontend `fetch()` calls aligned.
- Preserve report cache semantics: `GET` checks cache, `POST` generates and caches, `DELETE` is idempotent unless the document is unknown.
- Guard long-running report generation against duplicate in-flight work.
- Avoid live LLM or external API calls in deterministic tests.
- Use focused tests first, then broader suite and evaluation checks.
- Do not edit generated runtime data in `vaults/`, `temp_uploads/`, `.pytest_cache/`, or `__pycache__/`.

## Current Quality Gates

The observed CI workflow runs:

```powershell
python -m pytest -m evaluation -q
```

No linting, formatting, or static type-check configuration was observed in the repository.

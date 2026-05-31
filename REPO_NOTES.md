# Repository Notes

This file is a factual orientation guide for future AI/code sessions. It summarizes observed repository structure, commands, conventions, and gotchas without changing application behavior.

## Purpose

Diamond Miner is a local document-risk analysis application. It ingests uploaded documents, extracts a graph of entities and relationships, detects contradictions and risk patterns, and serves an interactive browser UI with reporting and export workflows.

## Entry Points

- `run.py`: local launcher. Loads `.env`, validates required directories, checks the port, and starts Uvicorn.
- `api.py`: FastAPI app and main Diamond Miner backend entry point.
- `static/index.html`: single-file vanilla JavaScript frontend.
- `core/orchestrator.py`: document parsing and ingestion pipeline.
- `core/vault.py`: `HybridVault`, the persistence layer.
- `core/agents.py`: LLM-backed extraction, critique, and report-writing agents.
- `core/simulator.py`: blast radius, black swan, and Monte Carlo simulation logic.

## Local Run Command

```powershell
python run.py
```

Default URL:

```text
http://localhost:8000
```

Useful startup environment variables:

```text
DIAMOND_MINER_PORT=8000
DIAMOND_MINER_STOP_STALE_SERVER=1
DIAMOND_MINER_FORCE_STOP_PORT_PROCESS=1
VAULT_PATH=./vaults
```

## LLM Configuration

The app supports OpenAI and OpenRouter through the OpenAI SDK interface.

Common variables:

```text
LLM_PROVIDER=openai
OPENAI_API_KEY=...
OPENROUTER_API_KEY=...
FAST_MODEL=gpt-4o-mini
SMART_MODEL=gpt-4o
```

`FAST_MODEL` is used for extraction-style work. `SMART_MODEL` is used for reasoning, drafting, and critique workflows.

## Test Commands

Full suite:

```powershell
pytest tests/
```

Focused examples:

```powershell
pytest tests/test_vault_narrative.py
pytest tests/test_vault_executive.py::TestGetExecutiveSummary::test_returns_none_when_no_cache
```

Deterministic evaluation gate:

```powershell
python -m pytest -m evaluation -q
```

Live model evaluation:

```powershell
set DIAMOND_MINER_LIVE_EVALUATION=1
python -m pytest -m live_evaluation -q
```

Live evaluation can call configured LLM providers and is intentionally separate from deterministic CI.

V2 frontend checks:

```powershell
cd frontend
npm.cmd run typecheck
npm.cmd run test
npm.cmd run build
npm.cmd run e2e
```

`npm.cmd run e2e` runs Playwright browser tests against `/app-v2`. The Playwright config can start `python ../run.py`, reuses an existing server when one is already bound, and avoids workflows that trigger live report generation.

## Observed Quality Tooling

- Test runner: `pytest`
- CI evaluation gate: `.github/workflows/evaluation.yml`
- No observed `pyproject.toml`, Ruff, Black, mypy, pyright, ESLint, or Prettier configuration.

## Architecture

High-level flow:

```text
Upload
  -> api.py background job
  -> DiamondOrchestrator
  -> parser by file type
  -> ChromaDB chunk storage
  -> LLM graph extraction
  -> SQLite graph topology
  -> contradiction / fragility / temporal analysis
  -> cached reports
  -> frontend canvas, dashboards, exports
```

`api.py` owns:

- FastAPI route definitions.
- Static UI serving.
- Shared local `HybridVault` instance.
- In-memory `JOB_STORE`.
- In-flight generation guards for report streams.
- SSE report generation responses.

`HybridVault` combines:

- SQLite database under `vaults/{tenant_id}/graph.sqlite`.
- ChromaDB collection under `vaults/{tenant_id}/chroma/`.
- Tables for documents, nodes, edges, friction lines, fragility lines, temporal metadata, narrative reports, executive summaries, and risk simulations.

## Important API Groups

- `POST /api/v1/ingest`
- `GET /api/v1/status/{job_id}`
- `GET /api/v1/documents`
- `DELETE /api/v1/documents/{document_id}`
- `DELETE /api/v1/vault`
- `GET /api/v1/canvas/{document_id}`
- `GET/POST/DELETE /api/v1/reports/executive-summary/{document_id}`
- `GET/POST/DELETE /api/v1/reports/narrative/{document_id}`
- `GET/POST/DELETE /api/v1/reports/risk-simulation/{document_id}`
- `GET /api/v1/export/pdf/{document_id}`
- `GET /api/v1/export/docx/{document_id}`
- `GET/POST /api/v1/config`

## Frontend Notes

`static/index.html` has no build step. It uses CDN dependencies:

```text
three@0.152.2
3d-force-graph@1.73.1
```

All frontend API calls use relative `/api/v1/...` paths. Report generation streams are consumed with `fetch()` and a readable stream reader.

`frontend/` is the Vite + React + TypeScript beta app served at `/app-v2`. It builds into `static/app-v2`, which is generated output and should not be edited manually.

Frontend test layers:

```text
Vitest: frontend/src/**/*.test.ts
Playwright: frontend/e2e/*.spec.ts
```

## Generated / Ignored Files

Do not edit generated runtime data unless explicitly asked:

```text
.env
vaults/
temp_uploads/
.pytest_cache/
__pycache__/
*.pyc
frontend/playwright-report/
frontend/test-results/
```

The repository may contain generated sample PDFs and report artifacts used for manual testing or design reference. Confirm intent before deleting or replacing them.

## Conventions

- Preserve existing user work and unrelated changes.
- Prefer focused edits over broad rewrites.
- Use `rg` for search.
- Keep API paths and frontend calls synchronized.
- Tests should use isolated temp vaults and mock LLM calls.
- Treat pinned dependency versions in `CLAUDE.md` as intentional project decisions.
- Keep report cache behavior consistent: `GET` reads cache, `POST` generates/cache-writes, `DELETE` removes cached output idempotently where documented.
- Long-running generation should be guarded with the existing `_active_*` set pattern.

## Gotchas

- The API currently hardcodes `tenant_id="local_user_01"`.
- The app has multi-tenant storage infrastructure, but the current surface is local single-user.
- Git may require a one-off safe-directory option in sandboxed sessions:

```powershell
git -c safe.directory='C:/Dev/Codex_Projects/Diamond Miner' status --short
```

- Real ingestion can call live LLM providers. Avoid running live workflows unless explicitly requested.
- Some tests and comments reflect Windows-specific startup behavior.
- The frontend is large and single-file; small changes should be carefully localized.

## Common Development Flow

1. Inspect the relevant route/module/test before editing.
2. Add or update focused tests for behavior changes.
3. Implement the smallest safe change.
4. Run the focused test first.
5. Run broader tests or the evaluation gate when the change touches shared behavior.

## Current Stabilization Opportunities

- Add a maintained product roadmap or backlog.
- Add linting, formatting, and type-checking decisions if the project wants them.
- Improve cleanup/retention behavior for generated temp uploads.
- Consider modularizing `static/index.html` if frontend changes become frequent.
- Expand deterministic evaluation fixtures for broader regression coverage.

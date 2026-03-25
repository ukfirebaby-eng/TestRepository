# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Commands

```bash
# Install dependencies
pip install -r requirements.txt

# Run the ERYC API server
uvicorn eryc.main:app --host 0.0.0.0 --port 8000 --reload

# Run all tests
pytest tests/

# Run a single test file
pytest tests/eryc/test_database.py
pytest tests/test_scheduler.py

# Run a single test by name
pytest tests/eryc/test_retrieval.py -k "test_hybrid_fusion"
```

There is no separate build or lint step configured.

## Repository Structure

Two independent components share this repo:

- **`eryc/`** — Document Intelligence Console: a FastAPI service for evidence-grounded document querying
- **`scheduler/`** — Lightweight job scheduler library (interval, cron, one-time, dependency chains)
- **`tests/`** — All tests; mirrors the source layout (`tests/eryc/`, `tests/test_scheduler.py`, etc.)
- **`examples/`** — Scheduler usage examples

## ERYC Architecture

ERYC answers natural-language queries against ingested documents using a multi-stage retrieval + LLM pipeline. All data is stored in SQLite.

### Request Lifecycle

1. `POST /v1/query` → `eryc/workflow/graph.py` (LangGraph state machine)
2. State flows through 7 nodes in `eryc/workflow/nodes.py`:
   `ingress_check → classify_query → plan_retrieval → hybrid_retrieval → evidence_judge → answer_compose → grounding_validate`
3. `evidence_judge` can loop back to `plan_retrieval` (max 3 rounds) if evidence is insufficient
4. `answer_compose` calls the Claude LLM (configured via `ERYC_LLM_MODEL`)
5. `grounding_validate` verifies citations and coverage before returning

The immutable workflow state is `EDICState` (TypedDict) in `eryc/workflow/state.py`.

### Retrieval

`eryc/retrieval/` implements three modes selected at planning time:
- **Lexical** — FTS5 with BM25 ranking
- **Semantic** — sqlite-vec vector search (degrades gracefully if extension unavailable)
- **Hybrid** — Reciprocal Rank Fusion (RRF, k=60) merging both result sets

### Document Ingestion

`POST /v1/documents/ingest` enqueues a job; `eryc/ingestion/worker.py` processes it in the background:
`parse (docx/pdf/md) → chunk (≤400 tokens) → extract metadata → embed → index`

Embeddings use `all-MiniLM-L6-v2` locally (no external calls).

### Temporal Knowledge Graph

Graph nodes (goal/phase/task/resource) and edges (depends_on/contributes_to/blocks) are stored in `graph_nodes` and `graph_edges`. Friction items (structural = red logical paradox, temporal = yellow timing conflict) live in `friction_items`. Managed via `eryc/api/routes/graph.py`.

### Reporting Layer

Three persona-oriented report sets, each in its own route file:
- **Strategic** (`reports_strategic.py`) — vulnerability/SPOF analysis (eigenvector centrality), risk cascade index, GQM alignment
- **Tactical** (`reports_tactical.py`) — schedule-collapse/negative-slack detection, bottleneck triage, ITDO trigger dashboard
- **Operational** (`reports_operational.py`) — friction resolution queue (with provenance text), document trust scores

### Database

`eryc/database/migrations.py` applies versioned migrations at startup. Connection management is in `eryc/database/connection.py` (WAL mode, thread-local pools, `sqlite3.Row` factory, `PRAGMA foreign_keys=ON`).

### Configuration

All settings are Pydantic `BaseSettings` in `eryc/config.py`, overridable via env vars prefixed `ERYC_`. Key defaults: `claude-haiku-4-5-20251001` LLM, 3 max retrieval rounds, RRF k=60, 20 lexical/semantic candidates, 10 max context chunks.

### Auth

`eryc/api/auth.py` validates Bearer tokens (SHA-256 digest lookup or raw `user_id` in dev mode). Workspace access is enforced on every route via `require_workspace_access()`.

## Scheduler Architecture

`scheduler/scheduler.py` runs a background thread pool (default 4 workers). Jobs are registered with a schedule type and optional dependency list. The engine validates the dependency graph for cycles at registration time (`CircularDependencyError`). A deterministic injected clock (`tick()`) makes tests reliable without `time.sleep`.

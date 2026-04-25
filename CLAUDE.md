# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

Do not make any changes untill you have 95% confidence in what you need to build. Ask me followup questions untill you reach that confidence level.

## Applied Learning

Add a one-line bullet here when something fails repeatedly, when I have to re-explain, or when a workaround is found for a platform/tool limitation. Keep each bullet under 15 words. No explanations. Only add things that will save time in future sessions.

- Templates + Puppeteer for visual consistency. AI image generation for one-offs only.
- Agents fail silently on wrong paths. Always verify hardcoded paths.
- New skills need a validation step before rendering. First runs have data gaps.
- Google Slides 'autofit' crashes batchUpdate. Set font sizes explicitly.
- Windows Developer Mode required for symlinks (Paperclip, etc.).

## Running the App

```bash
python run.py
```

Starts a FastAPI/Uvicorn server on `http://localhost:8000`. Required directories (`./vaults`, `./static`, `./temp_uploads`) are created automatically on first run.

**Required environment variables:**

| Variable | Default | Purpose |
|---|---|---|
| `OPENAI_API_KEY` | — | Required when `LLM_PROVIDER=openai` |
| `OPENROUTER_API_KEY` | — | Required when `LLM_PROVIDER=openrouter` |
| `LLM_PROVIDER` | `openai` | Switch between `openai` / `openrouter` |
| `FAST_MODEL` | `gpt-4o-mini` | Used by extraction/classification agents |
| `SMART_MODEL` | `gpt-4o` | Used by reasoning/drafting agents |

## Running Tests

```bash
pytest tests/                                                                                        # all tests
pytest tests/test_vault_narrative.py                                                                 # single file
pytest tests/test_vault_executive.py::TestGetExecutiveSummary::test_returns_none_when_no_cache      # single test
```

Tests use `tmp_path` fixtures for isolated SQLite databases and `unittest.mock.patch` to stub all LLM calls. No live API key is needed to run the test suite.

## Architecture

### Data Flow

```
PDF upload → DiamondOrchestrator → DeconstructorAgent (per chunk, parallel)
                                 → graph_topology table (SQLite)
                                 ↓
                    ContradictionHunterAgent  →  friction_lines table
                    FragilityAgent            →  hub_vulnerabilities
                    ChronosAgent              →  temporal_nodes table
                                 ↓
                    Report agents read from vault → SSE-streamed to browser
                    Results cached as JSON blobs in SQLite report tables
```

### `core/agents.py` — Agent Responsibilities

Nine agent classes, each with a `.run()` method:

| Agent | Temp | Purpose |
|---|---|---|
| `DeconstructorAgent` | 0.0 | Extracts JSON graph (nodes + edges) from a text chunk. Deterministic. |
| `ContradictionHunterAgent` | 0.0 | Detects logical contradictions between graph nodes. |
| `FragilityAgent` | 0.0 | Identifies hub nodes with critical dependency concentrations. |
| `ChronosAgent` | 0.0 | Extracts temporal markers and schedule conflicts. |
| `OutlineAgent` | 0.0 | Plans chapter structure for multi-chapter narrative reports. |
| `StorytellerAgent` | 0.7 | Single-pass narrative draft from raw issues (short reports). |
| `RecursiveDraftingAgent` | 0.7 | Per-chapter narrative drafting for multi-chapter reports. |
| `CriticAgent` | 0.0 | Compares draft against raw issues; triggers re-draft if gaps found. |
| `KDECoverageCheck` | — | Semantic coverage verification using ChromaDB vector similarity. |

`_get_model("fast")` / `_get_model("smart")` resolve the env var model names. `_get_client()` returns the appropriate OpenAI-compatible client.

### `core/vault.py` — HybridVault

Single class wrapping a per-tenant SQLite database (`./vaults/{tenant_id}/graph.sqlite`) and a ChromaDB collection (`./vaults/{tenant_id}/chroma/`). All SQL schema creation happens in `__init__`. Key method groups:

- **Ingestion**: `insert_document()`, `insert_document_chunk()`, `insert_graph_topology()`
- **Analysis results**: `upsert_friction_lines()`, `insert_fragility_lines()`, `insert_temporal_nodes()`
- **Reports (cached JSON blobs)**: `save_executive_summary()` / `get_executive_summary()` / `delete_executive_summary()` — same pattern for `narrative_report` and `risk_simulation`
- **Canvas**: `get_canvas_data()` — returns nodes + edges for the 3D graph
- **Simulator**: `save_risk_simulation()`, `has_temporal_data()`

### `core/orchestrator.py` — DiamondOrchestrator

Coordinates ingestion for a single document. Constructed with `(tenant_id, document_id, document_name, vault, log_fn)`. Main entry point is `run_ingestion_pipeline(file_path, max_workers=3)`, which parses the PDF with PyMuPDF (preserving bbox geometry for provenance), then fans out chunk processing across a `ThreadPoolExecutor`. Separate methods `interrogate_friction()`, `interrogate_fragility()`, and `interrogate_time_friction()` run the analysis agents after ingestion.

### `core/simulator.py` — Risk Simulators

Three independent classes, each with `.run() -> Dict[str, Any]`:

- `BlastRadiusCalculator` — BFS traversal to compute System Vulnerability Index (SVI) per node
- `BlackSwanAgent` — LLM-driven low-probability high-impact scenario generation
- `MonteCarloForecaster` — 5,000-trial Monte Carlo simulation over the risk matrix

### `api.py` — FastAPI Application

**Single vault instance** shared across all requests: `vault = HybridVault(tenant_id="local_user_01")`.

**SSE streaming pattern** (used by executive summary, narrative, and risk simulation POST endpoints):

```python
async def _stream():
    _active_generations.add(document_id)
    try:
        yield f"data: {json.dumps({...})}\n\n"
        result = await asyncio.to_thread(SomeAgent().run, ...)
        yield f"data: {json.dumps({'stage': 'complete', 'report': result})}\n\n"
    finally:
        _active_generations.discard(document_id)
return StreamingResponse(_stream(), media_type="text/event-stream")
```

**Report cache pattern**: GET returns `{"cached": true, "report": {...}}` or `{"cached": false}`. POST generates and caches. DELETE is idempotent (204 whether or not a cached row exists; 404 only if `document_id` is unknown).

**Concurrency guard**: `_active_generations`, `_active_narratives`, `_active_simulations` sets prevent duplicate simultaneous generation (409 if already running).

### `static/index.html`

Single-file vanilla JS frontend. No build step. Uses CDN-only dependencies:

- `three@0.152.2` and `3d-force-graph@1.73.1` for the Spatial Canvas WebGL view
- Google Fonts (Syne, JetBrains Mono)

All API calls use relative paths (`/api/v1/...`). SSE report streams are consumed via `fetch()` with a `ReadableStream` reader, not `EventSource`.

### Pinned Dependencies

These versions are non-negotiable (project ADRs):

```
fastapi==0.135.1
uvicorn[standard]==0.42.0
pydantic==2.12.5
chromadb==1.5.5
PyMuPDF==1.27.2.2
openai==2.29.0
```

### Multi-Tenancy

`HybridVault` supports multiple tenants via physical file isolation (`./vaults/{tenant_id}/`). The API currently hardcodes `tenant_id="local_user_01"` — the infrastructure is multi-tenant but the surface is single-user.

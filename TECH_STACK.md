# Diamond Miner Tech Stack

This document records the observed technology choices, runtime assumptions, tooling, and generated-output boundaries for future development sessions. It is factual based on the current repository state.

## Application Overview

Diamond Miner is a local document-risk analysis application. It ingests uploaded documents, extracts entities and relationships, builds a risk graph, identifies structural/timeline/fragility issues, and presents the results through browser-based graph and report workflows.

The repository currently contains two frontend surfaces:

- Legacy UI at `/`, served from `static/index.html`.
- V2 beta UI at `/app-v2`, built from `frontend/` and emitted to `static/app-v2`.

The backend API, ingestion pipeline, vault storage, report generation, simulation, and export logic remain Python/FastAPI based.

## Backend Stack

### Runtime

- Language: Python
- App framework: FastAPI
- ASGI server: Uvicorn
- Local launcher: `run.py`
- Main app module: `api.py`

Run command:

```powershell
python run.py
```

Default local URL:

```text
http://localhost:8000
```

### Core Backend Libraries

Observed or documented runtime dependencies include:

- `fastapi`
- `uvicorn`
- `chromadb`
- `openai`
- `pymupdf`
- `numpy`
- `weasyprint`
- `python-docx`
- `openpyxl`
- `python-pptx`
- `pytest`

Pinned dependency versions documented in `CLAUDE.md` should be treated as project decisions.

### Backend Entry Points

- `api.py`: FastAPI app, API routes, static serving, report streams, shared local vault, and in-memory job store.
- `run.py`: startup wrapper, `.env` loading, port checks, and Uvicorn launch.
- `core/orchestrator.py`: document ingestion and analysis coordination.
- `core/vault.py`: `HybridVault`, SQLite + ChromaDB persistence.
- `core/agents.py`: LLM-backed extraction, critique, drafting, and coverage agents.
- `core/simulator.py`: blast-radius, black-swan, and Monte Carlo simulation logic.

### Storage

The main persistence layer is `HybridVault`:

- SQLite files under `vaults/{tenant_id}/graph.sqlite`.
- ChromaDB storage under `vaults/{tenant_id}/chroma/`.
- Current API surface uses local tenant id `local_user_01`.

Generated runtime data:

```text
vaults/
temp_uploads/
```

These should not be edited manually unless explicitly requested.

### LLM Configuration

The app supports OpenAI and OpenRouter through OpenAI-compatible SDK usage.

Common environment variables:

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

Live LLM calls should be avoided in deterministic tests.

## Backend API Surface

Important API groups:

```text
POST /api/v1/ingest
GET /api/v1/status/{job_id}
GET /api/v1/documents
DELETE /api/v1/documents/{document_id}
DELETE /api/v1/vault
GET /api/v1/canvas/{document_id}
GET /api/v1/reports/friction-queue/{document_id}
GET /api/v1/reports/bottlenecks/{document_id}
GET /api/v1/reports/schedule-collapse/{document_id}
GET /api/v1/reports/risk-matrix/{document_id}
GET/POST/DELETE /api/v1/reports/executive-summary/{document_id}
GET/POST/DELETE /api/v1/reports/narrative/{document_id}
GET/POST/DELETE /api/v1/reports/risk-simulation/{document_id}
GET /api/v1/export/pdf/{document_id}
GET /api/v1/export/docx/{document_id}
GET/POST /api/v1/config
```

Report cache convention:

- `GET`: read cached report state.
- `POST`: generate and cache report.
- `DELETE`: clear cached report where supported.

Long-running generated report flows use SSE-like streamed `fetch()` responses on the frontend.

## Legacy Frontend Stack

Legacy UI:

```text
static/index.html
```

Characteristics:

- Single-file vanilla JavaScript frontend.
- No local build step.
- Served at `/`.
- Uses relative `/api/v1/...` calls.
- Uses CDN browser dependencies.

Observed CDN dependencies:

```text
three@0.152.2
3d-force-graph@1.73.1
```

Keep the legacy UI available while V2 remains beta.

## V2 Frontend Stack

V2 beta UI:

```text
frontend/
```

Served route:

```text
/app-v2
```

Build output:

```text
static/app-v2/
```

`static/app-v2/` is generated output and should not be manually edited.

### V2 Runtime and Build Tools

- Node package manager: npm
- Build tool: Vite
- UI framework: React
- Language: TypeScript
- React plugin: `@vitejs/plugin-react`

Frontend commands:

```powershell
cd frontend
npm.cmd run typecheck
npm.cmd run test
npm.cmd run build
npm.cmd run e2e
```

Development server:

```powershell
cd frontend
npm.cmd run dev
```

The Vite dev server proxies `/api/v1/*` to FastAPI at `http://localhost:8000`.

### V2 Main Libraries

Production dependencies:

- `react`
- `react-dom`
- `@vitejs/plugin-react`
- `three`
- `@react-three/fiber`
- `sigma`
- `graphology`

Development dependencies:

- `typescript`
- `vite`
- `vitest`
- `jsdom`
- `@testing-library/react`
- `@playwright/test`
- React and Node type packages

### V2 Source Layout

Important directories and files:

```text
frontend/src/api/              API client and shared frontend API types
frontend/src/graph/            normalization, lenses, layout, selection, detail helpers
frontend/src/reports/          report navigation and report data helpers
frontend/src/components/       React UI and graph components
frontend/src/styles.css        V2 global styling
frontend/e2e/                  Playwright browser tests
frontend/playwright.config.ts  Playwright configuration
frontend/vite.config.ts        Vite build/dev-server configuration
```

Important V2 components:

```text
CommandCenterApp.tsx           Main app shell
SpatialCanvas3D.tsx            Three.js/R3F 3D graph view
AnalystMap2D.tsx               Sigma.js 2D graph inspection view
OperationalReportsPanel.tsx    Native operational report panel
GeneratedReportsPanel.tsx      Native generated report panel
```

## Graph Rendering Stack

### 3D Spatial Canvas

Primary graph view:

- Three.js
- React Three Fiber
- Custom layout/focus helpers in `frontend/src/graph/`

Responsibilities:

- Cinematic 3D command-center graph.
- Node/link selection.
- Risk lens highlighting.
- Camera focus controls.
- Label-density controls.

Current known build note:

- The Three.js/R3F chunk triggers a Vite chunk-size warning. This is expected in the current V2 state.

### 2D Analyst Map

Inspection graph view:

- Sigma.js
- Graphology

Responsibilities:

- Readable 2D topology view.
- Risk lens filtering.
- Node/link click selection.
- Right-rail evidence synchronization.
- Critical Attention selection highlighting.

Current convention:

- Analyst Map keeps full graph context visible and highlights selected evidence.
- 3D view handles true camera fly-to behavior.

## Frontend Design System

The V2 UI uses a custom Diamond Miner command-center style rather than a generic SaaS component kit.

Observed design direction:

- Graphite/charcoal base.
- Restrained cyan, amber, red, and green accents.
- Dense executive dashboard layout.
- Left document rail.
- Center graph workspace.
- Right insight/report rail.

Important UI surfaces:

- Top command bar.
- Executive metric strip.
- Risk lens controls.
- Node search.
- 3D canvas / Analyst Map workspace.
- Selected Evidence panel.
- Critical Attention panel.
- Operational Reports panel.
- Generated Intelligence panel.
- Report Channels export links.

## Testing Stack

### Backend Tests

Test runner:

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

Live evaluation can call configured LLM providers and should only be run with explicit opt-in.

### V2 Unit and Contract Tests

Runner:

```powershell
cd frontend
npm.cmd run test
```

Current framework:

- Vitest
- jsdom
- file/source contract tests where useful

### V2 Type Checking

```powershell
cd frontend
npm.cmd run typecheck
```

Uses TypeScript project build mode:

```text
tsc -b
```

### V2 Browser E2E Tests

Runner:

```powershell
cd frontend
npm.cmd run e2e
```

Headed mode:

```powershell
cd frontend
npm.cmd run e2e:headed
```

Stack:

- Playwright
- Chromium project

Playwright config:

```text
frontend/playwright.config.ts
```

E2E specs:

```text
frontend/e2e/*.spec.ts
```

The current Playwright suite checks:

- `/app-v2` loads.
- First available document opens.
- 3D controls render.
- Analyst Map renders.
- Critical Attention selection updates Analyst Map state and selected evidence.
- Label-density dropdown contrast remains readable.

The suite intentionally avoids report-generation buttons because those can trigger live LLM/report work.

Generated Playwright output:

```text
frontend/playwright-report/
frontend/test-results/
```

These are ignored and should not be committed.

## Build and Static Serving

V2 production build:

```powershell
cd frontend
npm.cmd run build
```

Output:

```text
static/app-v2/
```

FastAPI serves:

- `/` from the legacy static UI.
- `/app-v2` from the built Vite output when present.
- `/app-v2/assets/*` from Vite-generated assets.

## Generated and Ignored Paths

Do not manually edit or commit generated runtime/build data:

```text
.env
vaults/
temp_uploads/
.pytest_cache/
__pycache__/
*.pyc
frontend/node_modules/
frontend/dist/
frontend/playwright-report/
frontend/test-results/
static/app-v2/
```

## Implementation Conventions

- Keep API paths and frontend `fetch()` calls aligned.
- Use relative frontend API paths such as `/api/v1/...`.
- Keep V2 backend API usage schema-compatible with existing FastAPI routes.
- Avoid live LLM or external API calls in deterministic tests.
- Prefer focused tests first, then broader checks.
- Preserve existing report cache semantics.
- Guard duplicate long-running generation with existing active-set patterns.
- Do not replace `/` with V2 until beta parity is explicitly accepted.
- Do not manually edit `static/app-v2`; rebuild from `frontend/`.

## Recommended Verification by Change Type

Backend route or vault changes:

```powershell
python -m pytest -q tests/<focused_test>.py
pytest tests/
```

Evaluation behavior:

```powershell
python -m pytest -m evaluation -q
```

V2 frontend logic or component changes:

```powershell
cd frontend
npm.cmd run typecheck
npm.cmd run test
npm.cmd run build
```

V2 browser-facing interaction changes:

```powershell
cd frontend
npm.cmd run e2e
```

Static V2 route changes:

```powershell
python -m pytest -q tests/test_app_v2_static.py tests/test_frontend_v2_contract.py tests/test_frontend_canvas_hud.py
```

## Known Risks and Open Technical Areas

- V2 remains beta at `/app-v2`; root `/` still serves the legacy UI.
- Some generated report flows are native in V2 but still compact right-rail experiences.
- Three.js bundle size currently produces a Vite warning.
- Analyst Map uses a deterministic layout rather than a physics or clustering layout.
- Live report generation can call LLM providers and should not be exercised casually in automated tests.
- The backend appears locally single-user despite multi-tenant vault structure.
- Broader linting/formatting policy is not yet established for the repo.

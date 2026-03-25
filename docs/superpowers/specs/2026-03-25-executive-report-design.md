# Design: Plain-English Executive Report

**Date:** 2026-03-25
**Status:** Approved
**Feature:** Executive Intelligence Report — AI-generated plain-English summary of all detected issues, with guaranteed omission prevention, streaming generation, SQLite caching, and PDF/clipboard export.

---

## Problem Statement

Diamond Miner's existing reporting suite (Friction Queue, Bottlenecks, Schedule Collapse, Risk Matrix) surfaces raw technical data. Non-technical stakeholders — executives, programme sponsors, senior leadership — cannot act on graph centrality scores or raw contradiction lists. They need a single, plain-English narrative that translates every detected issue into business consequences and actionable fixes, with a guarantee that nothing critical has been omitted.

---

## Goals

- Generate a plain-English report from all detected issues (contradictions, chronological conflicts, bottlenecks, risk matrix scores)
- Guarantee no Critical or High severity issue is ever omitted from the report
- Cache the report per document to avoid repeated API cost
- Stream progress to the user during the multi-agent generation pipeline
- Export the report as PDF and plain text for stakeholders without access to Diamond Miner

## Non-Goals

- Persona-based filtering (C-Suite vs PM vs Analyst) — not in scope for this version
- Automatic generation at ingestion time — user-initiated only
- Changes to the existing reporting dashboard (Friction Queue, Bottlenecks, etc.)

---

## Architecture Overview

```
[UI] "📋 Plain English" toolbar button
       ↓  GET  /api/v1/reports/executive-summary/{document_id}  → cache hit: render instantly
       ↓  POST /api/v1/reports/executive-summary/{document_id}  → cache miss: open SSE stream
[Agents]
    1. Hard-stop injection     — Python: Critical-severity issues forced into prompt (no LLM)
    2. StorytellerAgent        — GPT-4, temp=0.7: drafts structured plain-English report_json
    3. CriticAgent             — GPT-4, temp=0.0: audits draft vs raw issue list, triggers revision if gaps found (max 2 retries)
    4. KDECoverageCheck        — Python/numpy: semantic density comparison, appends coverage_warning if cluster gap detected
       ↓  all pass → write to SQLite cache
[Vault] executive_summaries table
[UI]   Report page renders; PDF + clipboard export available
```

---

## Data Layer

### New SQLite table — `executive_summaries`

```sql
CREATE TABLE IF NOT EXISTS executive_summaries (
    document_id   TEXT PRIMARY KEY,
    generated_at  TEXT NOT NULL,
    model         TEXT NOT NULL,
    report_json   TEXT NOT NULL
);
```

### `report_json` schema

```json
{
  "overall_assessment": "Moderate Risk",
  "generated_at": "2026-03-25T14:32:00Z",
  "summary_narrative": "Plain-English overview of the document's risk profile.",
  "business_impact": "Plain-English 'What This Means For You' paragraph.",
  "issues": [
    {
      "severity": "critical | high | medium | low",
      "title": "Short plain-English title",
      "plain_english": "Plain-English description of the problem and its business consequence.",
      "solution": "Plain-English recommended fix.",
      "source_nodes": ["node_id_a", "node_id_b"]
    }
  ],
  "coverage_verified": true,
  "coverage_warning": null
}
```

`generated_at` is an ISO-8601 UTC timestamp written into `report_json` at cache time by `save_executive_summary`. It is also stored in the `generated_at` column of `executive_summaries` for SQL queries. The UI reads `report.generated_at` directly from the returned `report_json` — no separate envelope field is required.

Issues are ordered: Critical first, then High, then Medium, then Low.

**Zero-issues case:** If a document has no detected issues of any severity, `save_executive_summary` is not called. The POST endpoint returns a single SSE `complete` event with a minimal valid report: `overall_assessment: "No Issues Found"`, `summary_narrative: "No conflicts or risks were detected in this document."`, `business_impact: ""`, `issues: []`, `coverage_verified: true`, `coverage_warning: null`. This report is cached normally so repeat views are instant.

### New vault methods (`core/vault.py`)

| Method | Signature | Purpose |
|--------|-----------|---------|
| `get_executive_summary` | `(document_id: str) -> Optional[Dict]` | Returns parsed `report_json` or `None` if not cached |
| `save_executive_summary` | `(document_id: str, report_json: Dict, model: str) -> None` | Writes/overwrites cache row |
| `delete_executive_summary` | `(document_id: str) -> None` | Clears cache row (called on Regenerate) |

---

## Agent Pipeline (`core/agents.py`)

### Stage 0 — Deterministic Hard-Stop Injection (Python, no LLM)

Before any LLM call, the backend queries SQLite for all issues with severity `Critical`. These are serialised into a `MUST INCLUDE` block prepended to the Storyteller's user prompt. The LLM has no discretion over whether to include them.

### Stage 1 — `StorytellerAgent` (GPT-4, temp=0.7)

**Input:** Full raw issue data (friction lines, chronological conflicts, hub vulnerabilities, risk matrix scores) + MUST INCLUDE block.

**System prompt instructs:**
- Write for a non-technical executive audience
- No graph theory, no technical jargon
- Express all issues as business consequences
- Return valid JSON matching the `report_json` schema

**Output:** Draft `report_json`

### Stage 2 — `CriticAgent` (GPT-4, temp=0.0)

**Input:** Draft `report_json` + complete raw issue list.

**Task:** Compare draft issues against raw list. Return a JSON array of any raw issues not represented in the draft.

**Revision loop:** If the array is non-empty, the Storyteller is called again with the missing items injected as additional `MUST INCLUDE` items. Maximum 2 revision cycles. If gaps remain after 2 retries, generation proceeds and a `coverage_warning` is appended to the report.

### Stage 3 — `KDECoverageCheck` (Python / numpy, no LLM)

**Embedding source:** Issues (contradictions, bottlenecks, etc.) are derived artefacts — they are not stored directly in ChromaDB. ChromaDB stores embeddings for the raw text chunks ingested from the PDF. Each issue in the vault has one or more `source_chunk_id` references (already present on `edges` and `friction_lines` rows). The KDE check retrieves embeddings for all source chunks associated with the document via `chromadb_collection.get(ids=source_chunk_ids, include=["embeddings"])`. This is the authoritative set of source vectors.

For the output side, the plain-English text of each issue in the draft `report_json` (`plain_english` field) is embedded using the same ChromaDB collection's embedding function via `chromadb_collection.get` or by calling `embedding_function([text])` directly — the same local model used at ingestion time, so no API call is made.

**Method:** Kernel Density Estimation (via `numpy`) over both vector sets projected to 2D with PCA (also numpy). Any dense cluster in the source embedding space with no corresponding density in the output embedding space is flagged as a potential omission.

**Output:** Sets `coverage_verified: true` if no gaps found. If gaps found, sets `coverage_verified: false` and writes a plain-English `coverage_warning` string.

**Cost:** Zero — uses ChromaDB's existing local embedding model and numpy (transitive dep). No API calls.

---

## API Layer (`api.py`)

### `GET /api/v1/reports/executive-summary/{document_id}`

- Returns `{"cached": true, "report": {...report_json...}}` if cached
- Returns `404` if document not found
- Returns `{"cached": false}` if document exists but report not yet generated

### `POST /api/v1/reports/executive-summary/{document_id}`

- Returns `fastapi.responses.StreamingResponse(generator(), media_type="text/event-stream")` — the route must use `StreamingResponse` with an async generator function, not a standard `JSONResponse`.
- Streams four progress events then a completion event:

```
data: {"stage": "analysing",  "message": "Analysing issues..."}
data: {"stage": "drafting",   "message": "Drafting plain-English narrative..."}
data: {"stage": "auditing",   "message": "Auditing for omissions..."}
data: {"stage": "verifying",  "message": "Verifying coverage..."}
data: {"stage": "complete",   "report": {...report_json...}}
```

- Writes completed report to SQLite cache before sending `complete` event
- Returns `404` if document not found
- Returns `409 Conflict` if generation already in progress for this document

**Concurrent generation guard:** A module-level `set` named `_active_generations: set[str]` is maintained in `api.py`. On POST, if `document_id in _active_generations` return 409 immediately. Otherwise add `document_id` to the set before starting the generator and remove it (in a `finally` block) when the generator exits — whether on success or error. This is safe because FastAPI runs in a single async event loop; no lock is required for a plain Python `set`.

### `DELETE /api/v1/reports/executive-summary/{document_id}`

- Deletes cache row from `executive_summaries`
- Returns `204 No Content` on success — including the case where no cached row existed (idempotent delete)
- Returns `404` only if the `document_id` does not exist in the `documents` table at all
- Called by the UI "Regenerate" button, which immediately fires the POST afterwards. Because DELETE is idempotent (returns 204 even with no row to delete), the UI never needs to handle a 404 from DELETE during normal Regenerate flow.

---

## UI Layer (`static/index.html`)

### Toolbar button

```html
<button class="toolbar-btn" id="plain-english-btn" onclick="openPlainEnglishReport()" style="display:none">
  📋 Plain English
</button>
```

Shown only after a document is loaded (same pattern as existing `📊 Report` button). Positioned between the Report button and the toolbar divider.

### `openPlainEnglishReport()` flow

```
1. Call GET endpoint
2a. cached: true  → call renderReportPage(report)
2b. cached: false → call POST endpoint, open SSE stream, show loading screen
                    on "complete" event → call renderReportPage(report)
```

### Loading screen

Reuses the existing SSE loading screen. Progress messages stream in as each agent stage completes.

### Report page

Replaces the 3D canvas while open (`#graph-container` hidden, `#report-page` shown).

**Structure:**
1. **Header bar** — document name · generated timestamp · `🔄 Regenerate` button · `📄 Download PDF` button · `📋 Copy` button · `✕ Close` button
2. **Health banner** — colour-coded by `overall_assessment` (green/amber/red) + `summary_narrative`
3. **"What This Means For You" box** — `business_impact` field
4. **Issue cards** — all `critical` and `high` severity issues rendered as full expanded cards. Each card shows: severity pill · plain-English title · plain-English description · solution row
5. **Accordion** — all `medium` and `low` severity issues collapsed under "Further Issues · N lower-priority conflicts"
6. **Coverage warning banner** (conditional) — shown in amber if `coverage_verified: false`, text: *"Note: the AI could not fully verify that all issues are represented in this report. Please cross-reference the Friction Queue for the complete technical list."*

### Export

**`📄 Download PDF`** — calls `window.print()`. A `@media print` CSS block hides the toolbar and header bar, renders the report full-width on A4. No dependencies, no build tools.

**`📋 Copy`** — serialises `report_json` into clean plain text (headings + bullet points) and writes to clipboard via `navigator.clipboard.writeText()`.

---

## Files Changed

| File | Change |
|------|--------|
| `core/vault.py` | Add `executive_summaries` table + 3 vault methods |
| `core/agents.py` | Add `StorytellerAgent`, `CriticAgent`, `KDECoverageCheck` |
| `api.py` | Add GET, POST, DELETE endpoints for executive summary |
| `static/index.html` | Add toolbar button, loading screen wiring, report page HTML/CSS/JS, export functions |
| `tests/test_vault_executive.py` | New — unit tests for the 3 vault methods |
| `tests/test_api_executive.py` | New — unit tests for all 3 API endpoints |

---

## Testing Strategy

- **Vault tests:** Verify `save`, `get`, and `delete` against an in-memory SQLite fixture
- **API tests:** Mock vault methods; verify 200/404/409 responses, SSE event sequence, cache read/write calls
- **Agent tests:** Mock OpenAI client; verify Critic Agent triggers revision loop on gap; verify KDE check sets `coverage_warning` when source and output clusters diverge
- **No frontend automated tests** — manual smoke test after UI implementation

---

## Constraints Respected

- Zero-build frontend — vanilla JS only, `window.print()` for PDF (no libraries)
- Local-first — no new cloud dependencies; KDE uses numpy (existing transitive dep)
- Pinned dependencies — no new Python packages required
- Single launch command — `python run.py` unchanged

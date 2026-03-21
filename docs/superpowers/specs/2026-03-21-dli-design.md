# Design Spec: Dynamic Logic Interrogator (DLI)
**Date:** 2026-03-21
**Project:** Diamond Miner
**Status:** Approved

---

## Overview

The Dynamic Logic Interrogator (DLI) is a third analysis pass that runs automatically after the Contradiction Hunter during document ingestion. It identifies **hub nodes** — concepts that many other nodes depend on via `REQUIRES` edges but which have no structural backup — and generates a GPT-4o semantic analysis of what cascades if that node fails. Results are surfaced on the Spatial Canvas as gold-highlighted nodes; clicking one opens a detailed fragility panel.

---

## Architecture

The DLI follows the same two-stage SQL→LLM pattern as the Contradiction Hunter:

1. **SQL** identifies hub node candidates (high in-degree of `REQUIRES` edges).
2. **`FragilityAgent`** verifies each candidate and produces a cascade analysis.
3. **`fragility_lines`** table persists confirmed results.
4. **Canvas endpoint** returns fragility data alongside existing nodes, edges, and friction lines.
5. **Frontend** colours hub nodes gold, renders a detailed panel on click.

---

## Hub Detection

### SQL Query

```sql
SELECT n.id, n.name, COUNT(e.id) AS dependency_count
FROM nodes n
JOIN edges e ON n.id = e.target_id
WHERE e.relationship = 'REQUIRES' AND e.document_id = ?
GROUP BY n.id
HAVING dependency_count >= 3
ORDER BY dependency_count DESC
```

Uses existing `REQUIRES` edges — no new edge types required, works immediately on all existing documents.

### Threshold

`HUB_MIN_DEPENDENTS = 3` defined as a named constant in `core/orchestrator.py`. The LLM acts as a quality gate, so SQL false positives are acceptable.

### New Vault Method

`get_hub_nodes(document_id: str, min_dependents: int = 3) -> List[Dict]`

Returns a list of `{"id": ..., "name": ..., "dependency_count": ..., "dependent_node_ids": [...]}` dicts. The `dependent_node_ids` list is resolved in a second query:

```sql
SELECT source_id FROM edges
WHERE target_id = ? AND relationship = 'REQUIRES' AND document_id = ?
```

---

## FragilityAgent

New static class in `core/agents.py`.

**Model:** `gpt-4o`
**Temperature:** `0.1`
**Response format:** `{"type": "json_object"}`

### Input

- Hub node name
- List of dependent node names
- Raw source text for the hub node's chunk (fetched from ChromaDB via `get_chunk_provenance`)

### System Prompt

```
You are a Professional Skeptic and Risk Architect reviewing a knowledge graph for structural fragility.

You will be given:
1. A HUB NODE: a concept that multiple other nodes explicitly depend on.
2. ITS DEPENDENTS: the nodes that require it.
3. THE SOURCE TEXT: the raw document passage that produced this node.

YOUR TASK — Two mandatory steps:

STEP 1 — VERIFY: Is this a genuine single point of failure?
A hub node is SPURIOUS if:
- It is a generic concept (e.g. "process", "system", "team") that appears frequently as boilerplate.
- The dependents are from unrelated contexts and do not logically share this dependency.
- The dependency is merely administrative or nominal, not operational.

STEP 2 — ANALYSE (only if genuine): Describe the cascade collapse. What fails, in what order, and why does it matter operationally? Be specific and unsparing.

Respond ONLY with valid JSON in exactly this format:
{
  "is_genuine": true or false,
  "confidence": a float between 0.0 and 1.0,
  "cascade_nodes": ["node name 1", "node name 2"],
  "insight": "Your cascade analysis if genuine, or a one-sentence explanation of why it is spurious."
}
```

### Output Contract

```json
{
  "is_genuine": true,
  "confidence": 0.87,
  "cascade_nodes": ["Production Deployment", "Emergency Patch Deployment", "Security Compliance"],
  "insight": "CAB Approval is a single coordination bottleneck..."
}
```

### Confidence Filter

Results with `is_genuine: false` or `confidence < 0.65` are discarded (same threshold as Contradiction Hunter).

---

## Data Storage

### New Table: `fragility_lines`

Added to `HybridVault.initialize_schemas()`:

```sql
CREATE TABLE IF NOT EXISTS fragility_lines (
    id            TEXT PRIMARY KEY,
    document_id   TEXT NOT NULL,
    hub_node_id   TEXT NOT NULL,
    insight       TEXT NOT NULL,
    cascade_nodes TEXT NOT NULL   -- JSON-encoded list of node name strings
)
```

### Index

```sql
CREATE INDEX IF NOT EXISTS idx_fragility_lines_document ON fragility_lines(document_id)
```

Added in `initialize_schemas()` after the `fragility_lines` table definition.

### New Vault Methods

**`upsert_fragility_lines(document_id: str, results: List[Dict]) -> None`**

Deletes existing rows for `document_id`, then inserts new results. Same pattern as `upsert_friction_lines`.

**`get_fragility_lines(document_id: str) -> List[Dict]`**

Returns all fragility results for a document as a list of dicts with keys: `id`, `hub_node_id`, `insight`, `cascade_nodes` (decoded from JSON).

### Deletion

`delete_document()` gains one additional DELETE statement. The full transaction order becomes: `friction_lines` → `fragility_lines` → `edges` → `documents`:

```python
cursor.execute("DELETE FROM fragility_lines WHERE document_id = ?", (document_id,))
```

---

## Pipeline Integration

### New Orchestrator Method

`interrogate_fragility()` added to `DiamondOrchestrator` in `core/orchestrator.py`:

```
1. Call vault.get_hub_nodes(document_id, min_dependents=HUB_MIN_DEPENDENTS)
2. For each hub node:
   a. Resolve dependent node names via vault.get_node_names(dependent_node_ids)
   b. Fetch source chunk text: `chunk_provenance = vault.get_chunk_provenance(source_chunk_id)` then pass `chunk_provenance.get("text", "")` to the agent (same pattern as `interrogate_friction()`)
   c. Call FragilityAgent.analyse(hub_name, dependent_names, source_text)
   d. Filter: skip if not is_genuine or confidence < 0.65
3. Call vault.upsert_fragility_lines(document_id, verified_results)
4. Print summary: "[*] DLI: N fragility point(s) confirmed, M spurious patterns discarded."
```

**Note:** The `nodes` table has no `source_chunk_id` column — that field lives on `edges`. To get representative source text for a hub node, the implementation fetches the `source_chunk_id` from any `REQUIRES` edge that targets the hub node within the same document:

```sql
SELECT source_chunk_id FROM edges
WHERE target_id = ? AND document_id = ? AND relationship = 'REQUIRES'
LIMIT 1
```

A new vault helper `get_node_source_chunk(node_id: str, document_id: str) -> str` wraps this query and returns the `source_chunk_id` string (or `None` if no such edge exists, in which case `interrogate_fragility()` skips that hub node with a log message).

### Call Order in `api.py`

```python
orchestrator.run_ingestion_pipeline(tmp_path)
orchestrator.interrogate_friction()
orchestrator.interrogate_fragility()   # ← new, runs after friction
```

### Job Status Phase

`interrogate_fragility()` prints `"[*] DLI: Mapping fragility..."` to the server console at the start of its run. This is a console log only — no `JOB_STORE` update is made. The job status remains `"processing"` throughout and flips to `"completed"` after `interrogate_fragility()` returns, exactly as it does today after `interrogate_friction()`.

---

## API

### `GET /api/v1/canvas/{document_id}` — updated response

`fragility_lines` added to the existing response body:

```json
{
  "document_id": "doc_abc123",
  "nodes": [...],
  "edges": [...],
  "friction_lines": [...],
  "fragility_lines": [
    {
      "hub_node_id": "node_xyz",
      "insight": "CAB Approval is a single coordination bottleneck...",
      "cascade_nodes": ["Production Deployment", "Emergency Patch Deployment"]
    }
  ]
}
```

No new endpoints required.

`fragility_lines` uses `vault.get_fragility_lines(document_id)` directly with no `DOCUMENT_STORE` in-memory fallback — this is intentional. Unlike `friction_lines` (which has a legacy in-memory fallback), fragility data is always written to SQLite and read from SQLite only.

---

## Frontend (`static/index.html`)

### Node Colouring

`loadCanvasData()` builds a `fragilityNodeIds` Set from `data.fragility_lines` (keyed on `hub_node_id`). Node colour priority (highest wins):

| Condition | Colour | Size (`val`) |
|---|---|---|
| Node ID in `fragilityNodeIds` | `#f5c542` (gold) with glow | `6` |
| Node ID in `frictionNodeIds` | `#f0883e` (amber) | `4` |
| Default | `#4d9ef7` (blue) | `4` |

### Click Handler

Hub node click opens the fragility panel (replaces the generic connections panel):

- Gold dot + node name in gold
- `"Single Point of Failure · N nodes depend on this"` subtitle
- Left-bordered section: **"What fails if this node fails"** → `insight` text
- Left-bordered section: **"Cascade path"** → numbered list of `cascade_nodes`
- **Copy Analysis** button (copies insight + cascade list to clipboard)

Regular node click retains existing behaviour (connections panel).

### Stats HUD

Fourth counter added: `fragility_lines.length` labelled **"Fragility Points"**, rendered in gold (`#f5c542`).

---

## Files Changed

| File | Change |
|---|---|
| `core/vault.py` | Add `fragility_lines` table + index in `initialize_schemas()`; add `get_hub_nodes()`, `get_node_source_chunk()`, `upsert_fragility_lines()`, `get_fragility_lines()`; update `delete_document()` |
| `core/agents.py` | Add `FragilityAgent` class |
| `core/orchestrator.py` | Add `interrogate_fragility()` method; define `HUB_MIN_DEPENDENTS = 3` |
| `api.py` | Call `interrogate_fragility()` after `interrogate_friction()`; add `fragility_lines` to canvas response |
| `static/index.html` | Build `fragilityNodeIds` Set; update node colour/size logic; add hub node click panel; add Fragility Points HUD counter |

---

## Out of Scope

- Friction Slider UI (replaced by automatic pipeline execution)
- `DEPENDS_ON` / `BACKED_BY` edge types (using existing `REQUIRES`)
- Betweenness centrality (in-degree threshold is sufficient at document scale)
- Bulk fragility re-analysis without re-ingestion
- Visualising cascade paths as graph edges
- Deleting orphaned `nodes` rows on document deletion (nodes are shared across documents; this remains out of scope as established in the delete document spec)

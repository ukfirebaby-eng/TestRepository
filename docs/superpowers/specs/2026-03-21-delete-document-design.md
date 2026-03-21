# Design Spec: Delete Document Feature
**Date:** 2026-03-21
**Project:** Diamond Miner
**Status:** Approved

---

## Overview

Allow users to permanently delete a previously analysed document and all its associated data from the vault, directly from the "Previously Analysed" list in the upload overlay.

---

## Data Deletion Scope

| Store | What gets deleted |
|---|---|
| SQLite `documents` | The document record |
| SQLite `edges` | All rows where `document_id` matches |
| SQLite `friction_lines` | All rows where `document_id` matches |
| ChromaDB | All chunk embeddings where metadata `document_id` matches |
| In-memory `DOCUMENT_STORE` | The `document_id` key is popped from the dict (only on success) |
| SQLite `nodes` | **Not deleted** — nodes carry no `document_id`. The canvas queries nodes through the `GET /api/v1/canvas/{document_id}` subquery (which joins through `edges`), so orphaned nodes never appear in any view. Any future feature querying `nodes` directly must apply its own document filter. |
| `JOB_STORE` | **Not cleaned up** — job entries persist for the lifetime of the server session. Explicitly out of scope. |

---

## Deletion Order & Failure Handling

SQLite is committed **first**. From the user's perspective, a committed SQLite deletion means the document is gone — the row disappears from the list and the operation is complete. ChromaDB is cleaned up afterwards.

**Execution order inside `delete_document()`:**

1. Open a SQLite transaction using `with self.conn:` (Python's context manager), which provides automatic rollback on any unhandled exception.

2. `DELETE FROM friction_lines WHERE document_id = ?`

3. `DELETE FROM edges WHERE document_id = ?`

4. `DELETE FROM documents WHERE id = ?`

5. `with` block exits cleanly → automatic commit.

6. Call `collection.delete(where={"document_id": {"$eq": document_id}})` to remove ChromaDB embeddings.
   - If no chunks exist for this `document_id` (e.g. ingestion was interrupted before any chunks were written), this is a permitted no-op.
   - If ChromaDB raises, log the error and propagate — but the SQLite commit has already succeeded.

**Failure scenarios:**

| Failure point | State | User impact |
|---|---|---|
| SQLite raises (steps 1–5) | Nothing deleted | Safe to retry; document still visible |
| ChromaDB raises (step 6) | SQLite deleted, chunks orphaned in ChromaDB | Document is gone from the UI. Orphaned chunks have no reachable edges and will never appear in any query. No user action required. |

**On success:** `DOCUMENT_STORE.pop(document_id, None)` is called in the API handler *after* `delete_document()` returns. On failure, the pop does not execute.

## Concurrent Ingestion Race

The 409 guard (checking `JOB_STORE` for `"processing"` status) eliminates the primary race case. A residual forward race exists — an ingestion could theoretically begin in the sub-millisecond window after the check passes. For this local-first, single-user application, that window is not reachable in practice. This is an **accepted limitation**.

---

## Concurrent Ingestion Race

If a user triggers deletion while an ingestion job for the same document is still in progress (`status = "processing"` in `JOB_STORE`), a race condition can occur: the DELETE commits while the background thread continues inserting chunks and edges.

**Resolution:** The `DELETE /api/v1/documents/{document_id}` handler checks `JOB_STORE` before calling `delete_document()`. If any job for this `document_id` has status `"processing"`, the endpoint returns **409 Conflict** with `detail: "Document ingestion is still in progress."` and takes no action.

---

## API

### `DELETE /api/v1/documents/{document_id}`

**Pre-condition check:** If any job in `JOB_STORE` maps to this `document_id` with status `"processing"`, return 409 immediately.

**Success response `200 OK`:**
```json
{ "status": "deleted", "document_id": "doc_abc123" }
```

**Error responses:**

| Status | Condition | `detail` string |
|---|---|---|
| 404 | `document_id` not found in `documents` table | `"Document not found."` |
| 409 | Ingestion still in progress | `"Document ingestion is still in progress."` |
| 500 | ChromaDB or SQLite failure | Exception message |

### `GET /api/v1/canvas/{document_id}` — related change

This endpoint currently returns an empty 200 for non-existent documents. As part of this feature it should return **404** when `document_id` is not present in the `documents` table, so that stale canvas loads (e.g. from browser history) fail clearly rather than silently rendering an empty graph.

---

## Vault Changes

### New method: `delete_document(document_id: str) -> None`

Implements the deletion order above using `with self.conn:` for the SQLite transaction.

### Schema change: index on `friction_lines(document_id)`

Added to `initialize_schemas()`:

```sql
CREATE INDEX IF NOT EXISTS idx_friction_lines_document ON friction_lines(document_id)
```

Note: `initialize_schemas()` is called on every `HybridVault.__init__()`. The `IF NOT EXISTS` guard makes this idempotent and safe.

---

## Vault Singleton in `api.py`

`api.py` currently instantiates a new `HybridVault` inside each request handler. ChromaDB's `PersistentClient` at version 0.4.22 is not safe to have multiple instances pointing at the same directory concurrently within the same process (the background ingestion task already holds one). As part of this feature, `api.py` is updated to use a **module-level vault singleton**:

```python
vault = HybridVault(tenant_id="local_user_01")
```

All request handlers that previously instantiated `HybridVault` locally will use this shared instance instead. This also eliminates the per-request `initialize_schemas()` overhead.

---

## Files Changed

| File | Change |
|---|---|
| `core/vault.py` | Add `delete_document()`; add `idx_friction_lines_document` index in `initialize_schemas()` |
| `api.py` | Add `DELETE /api/v1/documents/{document_id}`; add 409 guard; pop `DOCUMENT_STORE` on success; add module-level vault singleton; update `GET /api/v1/canvas/{document_id}` to return 404 for missing documents |
| `static/index.html` | Bin icon + inline confirmation; reset `activeDocumentId = null`; handle 409 in delete flow |

---

## UI Interaction

Changes are confined to the "Previously Analysed" list inside the upload overlay (`#doc-list`).

### Default state
Each document row shows filename (left), date (right), and a small muted bin icon (far right). The bin does not compete visually with the primary row click target.

### Confirmation state (triggered by bin click)
The row content is replaced in place (same height, no layout shift) with:
- Text: `Permanently delete "[filename]"?` — if the filename (including extension) exceeds 40 characters, it is truncated before the extension: `"Q3_Strategic_Review_Final_A….pdf"`
- A red **Delete** button
- A greyed **Cancel** button

### On Delete confirmed
1. Call `DELETE /api/v1/documents/{document_id}`
2. **On 200:** fade the row out and remove it from the DOM. If this was the active document: set `activeDocumentId = null`, clear canvas (`Graph.graphData({ nodes: [], links: [] })`), hide toolbar and stats HUD, show the upload overlay.
3. **On 409:** revert row to default state; show toast: "Cannot delete — ingestion still in progress."
4. **On any other error:** revert row to default state; show toast: "Deletion failed. Please try again."

### On Cancel clicked
Row reverts to its default state immediately. No action taken.

---

## Out of Scope

- Bulk delete (select multiple documents)
- Undo / restore after deletion
- Deleting orphaned nodes from the `nodes` table
- Deleting the ChromaDB collection itself
- Cleaning up `JOB_STORE` entries on deletion

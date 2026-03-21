# Delete Document Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Allow users to permanently delete a previously analysed document and all its associated data (SQLite records + ChromaDB embeddings) from within the "Previously Analysed" list in the upload overlay.

**Architecture:** Three layers touched in sequence — vault method, API endpoint, frontend UX. SQLite is committed first (user-visible deletion); ChromaDB cleaned up afterwards (orphaned chunks are harmless if that step fails). A module-level vault singleton in `api.py` replaces per-request instantiation to avoid concurrent `PersistentClient` conflicts.

**Tech Stack:** Python 3.11, FastAPI, SQLite3 (`with conn:` context manager for transactions), ChromaDB 0.4.22, vanilla JS (no framework).

**Spec:** `docs/superpowers/specs/2026-03-21-delete-document-design.md`

---

## File Map

| File | Action | What changes |
|---|---|---|
| `core/vault.py` | Modify | Add `idx_friction_lines_document` index in `initialize_schemas()`; add `delete_document()` method |
| `api.py` | Modify | Add module-level vault singleton; update `list_documents` and `get_canvas_data` handlers to use it; add 404 guard to `get_canvas_data`; add `DELETE /api/v1/documents/{document_id}` endpoint |
| `static/index.html` | Modify | Add bin icon to each doc row; inline confirmation state; handle 200/409/error responses; reset canvas + state on active-document deletion |
| `tests/test_vault_delete.py` | Create | Unit tests for `delete_document()` |
| `tests/test_api_delete.py` | Create | Integration tests for the DELETE and canvas endpoints |

---

## Task 1: Add `friction_lines` index to vault schema

**Files:**
- Modify: `core/vault.py` — `initialize_schemas()` method

### Background
`initialize_schemas()` is called on every `HybridVault.__init__()`. The `IF NOT EXISTS` guard makes all `CREATE INDEX` calls idempotent. The `friction_lines` table currently has no index on `document_id`, making the deletion query a full table scan. This is inconsistent with the pattern used for `edges`.

- [ ] **Step 1: Add the index**

In `core/vault.py`, inside `initialize_schemas()`, after the existing `idx_edges_document` line, add:

```python
cursor.execute("CREATE INDEX IF NOT EXISTS idx_friction_lines_document ON friction_lines(document_id)")
```

- [ ] **Step 2: Verify the index is created**

```bash
cd "C:\Users\windo\Downloads\Diamond Miner"
python -c "
from core.vault import HybridVault
v = HybridVault(tenant_id='test_idx')
cur = v.conn.cursor()
cur.execute(\"SELECT name FROM sqlite_master WHERE type='index' AND name='idx_friction_lines_document'\")
print(cur.fetchone())
import shutil; shutil.rmtree('./vaults/test_idx')
"
```

Expected output: `('idx_friction_lines_document',)`

- [ ] **Step 3: Commit**

```bash
git add core/vault.py
git commit -m "feat: add idx_friction_lines_document index to vault schema"
```

---

## Task 2: Add `delete_document()` to HybridVault

**Files:**
- Modify: `core/vault.py` — add method after `list_documents()`
- Create: `tests/test_vault_delete.py`

### Background
Deletion order: SQLite transaction first (auto-rollback via `with self.conn:`), ChromaDB second. ChromaDB 0.4.22's `collection.delete(where=...)` raises when no documents match the filter, so the implementation must check for existing chunks before calling delete — if none exist, skip the call entirely (permitted no-op). If ChromaDB fails for any other reason, the SQLite commit has already succeeded; the document is gone from the UI and the orphaned chunks are unreachable.

- [ ] **Step 1: Install pytest and create the tests directory**

```bash
cd "C:\Users\windo\Downloads\Diamond Miner"
pip install pytest
mkdir tests
```

- [ ] **Step 2: Create the test file**

Create `tests/test_vault_delete.py`:

```python
import pytest
from core.vault import HybridVault


@pytest.fixture
def vault(tmp_path):
    """Creates a fresh HybridVault in a temporary directory."""
    v = HybridVault(tenant_id="test_delete", base_dir=str(tmp_path))
    yield v
    v.conn.close()


def _seed_document(vault, document_id="doc_test"):
    """Inserts a minimal document with one edge and one friction line."""
    vault.insert_document(document_id, "test.pdf")

    vault.collection.add(
        ids=[f"{document_id}_chunk_1"],
        documents=["some text"],
        metadatas=[{"document_id": document_id, "page_number": 1,
                    "x0": 0.0, "y0": 0.0, "x1": 1.0, "y1": 1.0}]
    )

    cursor = vault.conn.cursor()
    cursor.execute("INSERT OR IGNORE INTO nodes (id, label, name) VALUES (?, ?, ?)",
                   ("node_a", "Concept", "Alpha"))
    cursor.execute("INSERT OR IGNORE INTO nodes (id, label, name) VALUES (?, ?, ?)",
                   ("node_b", "Concept", "Beta"))
    cursor.execute(
        "INSERT OR IGNORE INTO edges (id, document_id, source_id, target_id, relationship, source_chunk_id) "
        "VALUES (?, ?, ?, ?, ?, ?)",
        (f"{document_id}_edge_1", document_id, "node_a", "node_b", "REQUIRES", f"{document_id}_chunk_1")
    )
    vault.conn.commit()

    vault.upsert_friction_lines(document_id, [{
        "source": "node_a",
        "target": "node_b",
        "diamond": "A conflicts with B.",
        "provenance_ids": [f"{document_id}_chunk_1"]
    }])


class TestDeleteDocument:
    def test_deletes_document_record(self, vault):
        _seed_document(vault)
        vault.delete_document("doc_test")
        cursor = vault.conn.cursor()
        cursor.execute("SELECT id FROM documents WHERE id = 'doc_test'")
        assert cursor.fetchone() is None

    def test_deletes_edges(self, vault):
        _seed_document(vault)
        vault.delete_document("doc_test")
        cursor = vault.conn.cursor()
        cursor.execute("SELECT id FROM edges WHERE document_id = 'doc_test'")
        assert cursor.fetchall() == []

    def test_deletes_friction_lines(self, vault):
        _seed_document(vault)
        vault.delete_document("doc_test")
        cursor = vault.conn.cursor()
        cursor.execute("SELECT id FROM friction_lines WHERE document_id = 'doc_test'")
        assert cursor.fetchall() == []

    def test_deletes_chroma_embeddings(self, vault):
        _seed_document(vault)
        vault.delete_document("doc_test")
        result = vault.collection.get(where={"document_id": {"$eq": "doc_test"}})
        assert result["ids"] == []

    def test_does_not_delete_nodes(self, vault):
        """Nodes are shared and must not be deleted."""
        _seed_document(vault)
        vault.delete_document("doc_test")
        cursor = vault.conn.cursor()
        cursor.execute("SELECT COUNT(*) FROM nodes")
        assert cursor.fetchone()[0] == 2

    def test_no_op_when_document_has_no_chunks(self, vault):
        """delete_document() must not raise when the document has zero ChromaDB chunks."""
        vault.insert_document("doc_empty", "empty.pdf")
        # No chunks added — ChromaDB delete would raise if called blindly
        vault.delete_document("doc_empty")
        cursor = vault.conn.cursor()
        cursor.execute("SELECT id FROM documents WHERE id = 'doc_empty'")
        assert cursor.fetchone() is None

    def test_does_not_affect_other_documents(self, vault):
        """Deleting one document must not touch another document's data."""
        _seed_document(vault, "doc_a")
        _seed_document(vault, "doc_b")
        vault.delete_document("doc_a")
        cursor = vault.conn.cursor()
        cursor.execute("SELECT id FROM documents WHERE id = 'doc_b'")
        assert cursor.fetchone() is not None
        cursor.execute("SELECT COUNT(*) FROM edges WHERE document_id = 'doc_b'")
        assert cursor.fetchone()[0] == 1
```

- [ ] **Step 3: Run tests to confirm they all fail**

```bash
python -m pytest tests/test_vault_delete.py -v
```

Expected: all 7 tests fail with `AttributeError: 'HybridVault' object has no attribute 'delete_document'`

- [ ] **Step 4: Implement `delete_document()` in `core/vault.py`**

Add after the `list_documents()` method:

```python
def delete_document(self, document_id: str) -> None:
    """
    Permanently removes a document and all its associated data.
    SQLite is committed first; ChromaDB is cleaned up afterwards.
    If ChromaDB fails, the SQLite deletion has already committed — the document
    is gone from all UI queries and the orphaned chunks are unreachable.
    """
    with self.conn:
        cursor = self.conn.cursor()
        cursor.execute("DELETE FROM friction_lines WHERE document_id = ?", (document_id,))
        cursor.execute("DELETE FROM edges WHERE document_id = ?", (document_id,))
        cursor.execute("DELETE FROM documents WHERE id = ?", (document_id,))

    # ChromaDB 0.4.22 raises when collection.delete() matches zero documents.
    # Check first; skip the call if no chunks exist for this document.
    try:
        existing = self.collection.get(where={"document_id": {"$eq": document_id}})
        if existing["ids"]:
            self.collection.delete(where={"document_id": {"$eq": document_id}})
    except Exception as e:
        print(f"[!] Vault: ChromaDB cleanup failed for {document_id}: {e}")
        raise
```

- [ ] **Step 5: Run tests to confirm they all pass**

```bash
python -m pytest tests/test_vault_delete.py -v
```

Expected: all 7 tests pass.

- [ ] **Step 6: Commit**

```bash
git add core/vault.py tests/test_vault_delete.py
git commit -m "feat: add HybridVault.delete_document() with full test coverage"
```

---

## Task 3: Vault singleton + canvas 404 fix in `api.py`

**Files:**
- Modify: `api.py` — replace per-request vault instantiation with module-level singleton; add 404 guard to `get_canvas_data`
- Create: `tests/test_api_delete.py` (canvas 404 test only at this stage)

### Background
Currently every request handler instantiates a new `HybridVault`. With ChromaDB 0.4.22, multiple `PersistentClient` instances in the same process pointing at the same directory are unsafe. A module-level singleton reduces this to one API-side instance.

The `get_canvas_data` handler currently returns an empty 200 for non-existent documents. After deletion, stale canvas loads must return 404.

The test file imports `app` at module scope (outside the fixture) so pytest's module caching does not interfere with the `patch`. Each test uses a fresh `MagicMock` cursor via `side_effect` to prevent shared mock state across cursor calls.

- [ ] **Step 1: Write the canvas 404 test**

Create `tests/test_api_delete.py`:

```python
import pytest
from fastapi.testclient import TestClient
from unittest.mock import patch, MagicMock

# Import app at module scope so pytest caching does not interfere with patching
from api import app


def _make_mock_vault(fetchone_value=None, fetchall_value=None):
    """Returns a MagicMock vault where each cursor() call returns a fresh cursor stub."""
    mock_vault = MagicMock()
    mock_vault.list_documents.return_value = []
    mock_vault.get_friction_lines.return_value = []

    def fresh_cursor():
        cur = MagicMock()
        cur.fetchone.return_value = fetchone_value
        cur.fetchall.return_value = fetchall_value or []
        return cur

    mock_vault.conn.cursor.side_effect = fresh_cursor
    return mock_vault


@pytest.fixture
def client():
    """Test client with a mocked vault singleton. Yields (TestClient, mock_vault)."""
    mock_vault = _make_mock_vault()
    with patch("api.vault", mock_vault):
        with TestClient(app) as c:
            yield c, mock_vault


class TestCanvasEndpoint:
    def test_canvas_returns_404_for_missing_document(self, client):
        test_client, _ = client
        mock_vault = _make_mock_vault(fetchone_value=None)
        with patch("api.vault", mock_vault):
            response = test_client.get("/api/v1/canvas/doc_doesnotexist")
        assert response.status_code == 404
        assert response.json()["detail"] == "Document not found."
```

- [ ] **Step 2: Run the canvas 404 test to confirm it fails**

```bash
python -m pytest tests/test_api_delete.py::TestCanvasEndpoint -v
```

Expected: FAIL — endpoint currently returns 200 with empty data.

- [ ] **Step 3: Add vault singleton and fix canvas 404 in `api.py`**

**3a.** After the import block in `api.py`, add the singleton (keep `JOB_STORE` and `DOCUMENT_STORE` where they are):

```python
# --- Shared Vault Singleton ---
# Single instance shared across all request handlers to avoid multiple
# concurrent PersistentClient connections to the same ChromaDB directory.
vault = HybridVault(tenant_id="local_user_01")
```

**3b.** Replace the body of `list_documents` to use the singleton (remove the local `vault = HybridVault(...)` line inside it):

```python
@app.get("/api/v1/documents")
async def list_documents():
    """Returns all previously ingested documents so the UI can restore them without re-processing."""
    return {"documents": vault.list_documents()}
```

**3c.** Replace the full body of `get_canvas_data` with:

```python
@app.get("/api/v1/canvas/{document_id}")
async def get_canvas_data(document_id: str):
    """Returns the unified graph topology for the WebGL renderer."""
    try:
        cursor = vault.conn.cursor()

        # 404 if document does not exist
        cursor.execute("SELECT id FROM documents WHERE id = ?", (document_id,))
        if cursor.fetchone() is None:
            raise HTTPException(status_code=404, detail="Document not found.")

        cursor.execute("""
            SELECT DISTINCT n.id, n.label, n.name FROM nodes n
            WHERE n.id IN (
                SELECT source_id FROM edges WHERE document_id = ?
                UNION
                SELECT target_id FROM edges WHERE document_id = ?
            )
        """, (document_id, document_id))
        nodes = [dict(row) for row in cursor.fetchall()]

        cursor.execute("""
            SELECT source_id AS source, target_id AS target, relationship, source_chunk_id
            FROM edges WHERE document_id = ?
        """, (document_id,))
        edges = [dict(row) for row in cursor.fetchall()]

        friction_lines = vault.get_friction_lines(document_id) or DOCUMENT_STORE.get(document_id, [])

        return {
            "document_id": document_id,
            "nodes": nodes,
            "edges": edges,
            "friction_lines": friction_lines
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
```

- [ ] **Step 4: Run the canvas 404 test to confirm it passes**

```bash
python -m pytest tests/test_api_delete.py::TestCanvasEndpoint -v
```

Expected: PASS.

- [ ] **Step 5: Smoke-test the running server**

```bash
python run.py
# In another terminal:
curl -s -o /dev/null -w "%{http_code}" http://localhost:8000/api/v1/canvas/doc_doesnotexist
```

Expected: `404`

- [ ] **Step 6: Commit**

```bash
git add api.py tests/test_api_delete.py
git commit -m "feat: vault singleton in api.py; canvas endpoint returns 404 for missing documents"
```

---

## Task 4: Add `DELETE /api/v1/documents/{document_id}` endpoint

**Files:**
- Modify: `api.py` — add the DELETE endpoint
- Modify: `tests/test_api_delete.py` — add DELETE endpoint tests

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_api_delete.py`:

```python
class TestDeleteEndpoint:
    def test_delete_returns_200_on_success(self):
        mock_vault = _make_mock_vault(fetchone_value={"id": "doc_abc"})
        with patch("api.vault", mock_vault):
            with TestClient(app) as c:
                response = c.delete("/api/v1/documents/doc_abc")
        assert response.status_code == 200
        assert response.json() == {"status": "deleted", "document_id": "doc_abc"}

    def test_delete_calls_delete_document(self):
        mock_vault = _make_mock_vault(fetchone_value={"id": "doc_abc"})
        with patch("api.vault", mock_vault):
            with TestClient(app) as c:
                c.delete("/api/v1/documents/doc_abc")
        mock_vault.delete_document.assert_called_once_with("doc_abc")

    def test_delete_pops_document_store(self):
        mock_vault = _make_mock_vault(fetchone_value={"id": "doc_abc"})
        store = {"doc_abc": [{"diamond": "test"}]}
        with patch("api.vault", mock_vault), patch("api.DOCUMENT_STORE", store):
            with TestClient(app) as c:
                c.delete("/api/v1/documents/doc_abc")
        assert "doc_abc" not in store

    def test_delete_returns_404_for_missing_document(self):
        mock_vault = _make_mock_vault(fetchone_value=None)
        with patch("api.vault", mock_vault):
            with TestClient(app) as c:
                response = c.delete("/api/v1/documents/doc_missing")
        assert response.status_code == 404
        assert response.json()["detail"] == "Document not found."

    def test_delete_returns_409_when_ingestion_in_progress(self):
        mock_vault = _make_mock_vault(fetchone_value={"id": "doc_busy"})
        job_store = {"job_1": {"status": "processing", "document_id": "doc_busy"}}
        with patch("api.vault", mock_vault), patch("api.JOB_STORE", job_store):
            with TestClient(app) as c:
                response = c.delete("/api/v1/documents/doc_busy")
        assert response.status_code == 409
        assert response.json()["detail"] == "Document ingestion is still in progress."

    def test_delete_returns_500_on_vault_error(self):
        mock_vault = _make_mock_vault(fetchone_value={"id": "doc_broken"})
        mock_vault.delete_document.side_effect = Exception("ChromaDB connection refused")
        with patch("api.vault", mock_vault):
            with TestClient(app) as c:
                response = c.delete("/api/v1/documents/doc_broken")
        assert response.status_code == 500
```

- [ ] **Step 2: Run tests to confirm they all fail**

```bash
python -m pytest tests/test_api_delete.py::TestDeleteEndpoint -v
```

Expected: all 6 tests fail with 404 or 405 (route does not exist yet).

- [ ] **Step 3: Implement the DELETE endpoint in `api.py`**

Add after the `list_documents` endpoint:

```python
@app.delete("/api/v1/documents/{document_id}")
async def delete_document_endpoint(document_id: str):
    """Permanently deletes a document and all its associated vault data."""
    cursor = vault.conn.cursor()

    cursor.execute("SELECT id FROM documents WHERE id = ?", (document_id,))
    if cursor.fetchone() is None:
        raise HTTPException(status_code=404, detail="Document not found.")

    is_processing = any(
        job.get("document_id") == document_id and job.get("status") == "processing"
        for job in JOB_STORE.values()
    )
    if is_processing:
        raise HTTPException(status_code=409, detail="Document ingestion is still in progress.")

    try:
        vault.delete_document(document_id)
        DOCUMENT_STORE.pop(document_id, None)
        return {"status": "deleted", "document_id": document_id}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
```

Note: the function is named `delete_document_endpoint` (not `delete_document`) to avoid shadowing `vault.delete_document`.

- [ ] **Step 4: Run all API tests**

```bash
python -m pytest tests/test_api_delete.py -v
```

Expected: all tests pass.

- [ ] **Step 5: Smoke-test the running server**

```bash
python run.py
# In another terminal:
curl -s -X DELETE http://localhost:8000/api/v1/documents/doc_doesnotexist | python -m json.tool
```

Expected:
```json
{"detail": "Document not found."}
```

- [ ] **Step 6: Commit**

```bash
git add api.py tests/test_api_delete.py
git commit -m "feat: add DELETE /api/v1/documents/{document_id} endpoint"
```

---

## Task 5: Frontend — bin icon and inline confirmation UX

**Files:**
- Modify: `static/index.html` — CSS block and `loadStoredDocs()` function

### Background
Changes are entirely within the CSS block and `loadStoredDocs()`. Each document row gets a bin icon. Clicking it replaces the row content in-place (same height) with a confirmation prompt. The delete flow calls the API and handles 200/409/error responses. If the deleted document is currently active, the canvas clears and the overlay is shown.

No JS test framework is configured — verify with manual browser steps.

- [ ] **Step 1: Add bin icon CSS**

In `static/index.html`, locate the line `.doc-entry .doc-badge {` in the `<style>` block. Add the following CSS **after** the `.doc-entry .doc-badge` rule (after its closing `}`):

```css
.doc-delete-btn {
    background: none; border: none; color: #8b949e; cursor: pointer;
    padding: 4px 6px; border-radius: 4px; font-size: 1rem; line-height: 1;
    transition: color 0.2s, background 0.2s; flex-shrink: 0;
}
.doc-delete-btn:hover { color: #ff7b72; background: rgba(255,123,114,0.1); }

.doc-confirm { display: flex; align-items: center; gap: 8px; width: 100%; }
.doc-confirm-text { flex: 1; font-size: 0.85rem; color: #c9d1d9; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.doc-confirm-delete {
    background: #b91c1c; color: white; border: none; border-radius: 4px;
    padding: 4px 12px; cursor: pointer; font-size: 0.8rem; flex-shrink: 0;
    transition: background 0.2s;
}
.doc-confirm-delete:hover { background: #dc2626; }
.doc-confirm-cancel {
    background: none; color: #8b949e; border: 1px solid #30363d; border-radius: 4px;
    padding: 4px 10px; cursor: pointer; font-size: 0.8rem; flex-shrink: 0;
    transition: border-color 0.2s, color 0.2s;
}
.doc-confirm-cancel:hover { border-color: #8b949e; color: #c9d1d9; }
```

- [ ] **Step 2: Add `truncateFilename` helper**

In the `<script>` block, add the following function **immediately before** the `async function loadStoredDocs()` declaration:

```javascript
function truncateFilename(name, maxLen = 40) {
    if (name.length <= maxLen) return name;
    const dot = name.lastIndexOf('.');
    const ext = dot > 0 ? name.slice(dot) : '';
    const base = dot > 0 ? name.slice(0, dot) : name;
    const allowed = maxLen - ext.length - 1;
    return base.slice(0, allowed) + '\u2026' + ext;
}
```

- [ ] **Step 3: Replace the doc-entry rendering block inside `loadStoredDocs()`**

Inside `loadStoredDocs()`, find and **replace** this exact block — the four lines that create the entry element and attach its click listener:

```javascript
                    const entry = document.createElement('div');
                        entry.className = 'doc-entry' + (doc.id === activeDocumentId ? ' active' : '');
                        entry.innerHTML = `
                            <div class="doc-info">
                                <span class="doc-name">${doc.name}</span>
                                <span class="doc-meta">${date}</span>
                            </div>
                        `;
                        entry.addEventListener('click', () => {
                            overlay.style.display = 'none';
                            loadCanvasData(doc.id, doc.name);
                        });
                        docList.appendChild(entry);
```

Replace with:

```javascript
                    const entry = document.createElement('div');
                        entry.className = 'doc-entry' + (doc.id === activeDocumentId ? ' active' : '');
                        const truncated = truncateFilename(doc.name);

                        function renderDefault() {
                            entry.innerHTML = `
                                <div class="doc-info">
                                    <span class="doc-name">${doc.name}</span>
                                    <span class="doc-meta">${date}</span>
                                </div>
                                <button class="doc-delete-btn" title="Delete document" aria-label="Delete ${doc.name}">&#128465;</button>
                            `;
                            entry.querySelector('.doc-info').addEventListener('click', () => {
                                overlay.style.display = 'none';
                                loadCanvasData(doc.id, doc.name);
                            });
                            entry.querySelector('.doc-delete-btn').addEventListener('click', (e) => {
                                e.stopPropagation();
                                renderConfirm();
                            });
                        }

                        function renderConfirm() {
                            entry.innerHTML = `
                                <div class="doc-confirm">
                                    <span class="doc-confirm-text">Permanently delete &ldquo;${truncated}&rdquo;?</span>
                                    <button class="doc-confirm-cancel">Cancel</button>
                                    <button class="doc-confirm-delete">Delete</button>
                                </div>
                            `;
                            entry.querySelector('.doc-confirm-cancel').addEventListener('click', renderDefault);
                            entry.querySelector('.doc-confirm-delete').addEventListener('click', async () => {
                                entry.querySelector('.doc-confirm-delete').disabled = true;
                                try {
                                    const res = await fetch(`/api/v1/documents/${doc.id}`, { method: 'DELETE' });
                                    if (res.status === 200) {
                                        entry.style.transition = 'opacity 0.3s';
                                        entry.style.opacity = '0';
                                        setTimeout(() => entry.remove(), 300);
                                        if (doc.id === activeDocumentId) {
                                            activeDocumentId = null;
                                            Graph.graphData({ nodes: [], links: [] });
                                            document.getElementById('toolbar').style.display = 'none';
                                            document.getElementById('stats-hud').style.display = 'none';
                                            showOverlay();
                                        }
                                    } else if (res.status === 409) {
                                        renderDefault();
                                        showToast('Cannot delete \u2014 ingestion still in progress.');
                                    } else {
                                        renderDefault();
                                        showToast('Deletion failed. Please try again.');
                                    }
                                } catch {
                                    renderDefault();
                                    showToast('Deletion failed. Please try again.');
                                }
                            });
                        }

                        renderDefault();
                        docList.appendChild(entry);
```

- [ ] **Step 4: Manual browser verification — happy path**

Start the server, upload a PDF, wait for ingestion to complete.

1. Click the **Documents** toolbar button to open the overlay.
2. Confirm the document row shows a bin icon (🗑) on the right.
3. Click the bin — confirm the row transforms to `Permanently delete "…"?` with **Delete** and **Cancel** buttons at the same height.
4. Click **Cancel** — confirm the row returns to normal.
5. Click the bin again, then **Delete** — confirm the row fades out and is removed.
6. Re-open the overlay — confirm the document is gone from the list.

- [ ] **Step 5: Manual browser verification — active document deletion**

1. Load a document onto the canvas. Close the overlay.
2. Click **Documents**, bin the active document, click **Delete**.
3. Confirm: canvas clears to empty, toolbar and stats HUD disappear, upload overlay appears.
4. In browser DevTools → Network: confirm `GET /api/v1/canvas/{document_id}` now returns 404.

- [ ] **Step 6: Manual browser verification — edge cases**

1. Filename > 40 chars: confirm confirmation text shows `Base….ext` format; default row still shows full name.
2. Open browser console — confirm zero JS errors throughout the full delete flow.

- [ ] **Step 7: Commit**

```bash
git add static/index.html
git commit -m "feat: document delete UI with inline confirmation and full response handling"
```

---

## Task 6: Final smoke test

- [ ] **Step 1: Run all tests**

```bash
cd "C:\Users\windo\Downloads\Diamond Miner"
python -m pytest tests/ -v
```

Expected: all tests pass.

- [ ] **Step 2: End-to-end manual test**

1. Start fresh: `python run.py`
2. Upload two different PDFs, wait for both ingestions to complete.
3. Open the overlay — confirm both appear in the list.
4. Load document A onto the canvas. Close the overlay.
5. Open the overlay. Delete document B (not the active one). Confirm B disappears; canvas and toolbar unchanged.
6. Delete document A (the active one). Confirm canvas clears and overlay appears.
7. Confirm the "Previously Analysed" section no longer appears (empty list).
8. Verify via `curl http://localhost:8000/api/v1/documents` — confirms empty list.

- [ ] **Step 3: Final commit**

```bash
git add .
git commit -m "feat: complete delete document feature — vault, API, and frontend"
```

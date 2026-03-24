# Reporting Engine Phase 1 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the Phase 1 "Quick Wins" reporting suite — a Friction Resolution Queue and a Hub & Spoke Bottleneck Report — surfaced via a slide-up Executive Dashboard panel in the existing WebGL UI.

**Architecture:** Two new read-only API endpoints pull data directly from SQLite (zero LLM cost). A new `get_hub_vulnerabilities()` vault method counts in-degree centrality across REQUIRES and STARTS_AFTER edges. A dashboard overlay in `index.html` renders both reports and links each item back to the 3D canvas via camera flyto and side-panel open.

**Tech Stack:** Python + FastAPI + SQLite (existing HybridVault) + Vanilla JS (existing 3d-force-graph canvas)

---

## Design Decisions

**Friction queue uses `document_id`, not `job_id`.**
The spec draft shows `/friction-queue/{job_id}` but `JOB_STORE` is in-memory and wiped on server restart, making the endpoint useless for documents loaded from the document list. Using `document_id` allows the queue to be served from persisted vault data every time.

**Friction queue combines structural + chronological.**
The functional spec says the queue surfaces "all structural and chronological paradoxes." Both types are already persisted in separate vault tables after ingestion. The endpoint merges them with a `type` field so the UI can colour-code them.

**`get_hub_vulnerabilities` is document-scoped.**
The spec's SQL lacks a document filter, which would mix data across all ingested documents. Since the bottleneck endpoint is scoped to `document_id`, the vault method must be too.

---

## File Map

| File | Change |
|------|--------|
| `core/vault.py` | Add `get_hub_vulnerabilities(document_id, limit)` method |
| `api.py` | Add `GET /api/v1/reports/friction-queue/{document_id}` and `GET /api/v1/reports/bottlenecks/{document_id}` |
| `static/index.html` | Add dashboard CSS, HTML, JS; add toolbar "Report" button; call `loadReportingDashboard` from `loadCanvasData` |
| `tests/test_vault_reporting.py` | New — tests for `get_hub_vulnerabilities` |
| `tests/test_api_reporting.py` | New — tests for both reporting endpoints |

---

## Task 1: `get_hub_vulnerabilities()` in vault.py

**Files:**
- Modify: `core/vault.py`
- Create: `tests/test_vault_reporting.py`

- [ ] **Step 1: Write the failing test**

Create `tests/test_vault_reporting.py`:

```python
import pytest
from core.vault import HybridVault


@pytest.fixture
def vault(tmp_path):
    v = HybridVault(tenant_id="test_reporting", base_dir=str(tmp_path))
    yield v
    v.conn.close()


def _seed_hub_graph(vault, document_id="doc_hubs"):
    """Seeds a graph where node_b has 2 REQUIRES + 1 STARTS_AFTER = 3 inbound,
    and node_c has 1 REQUIRES = 1 inbound (below any reasonable threshold)."""
    vault.insert_document(document_id, "hub_report_test.pdf")
    cursor = vault.conn.cursor()
    for name in ["node_a", "node_b", "node_c", "node_d", "node_e"]:
        cursor.execute(
            "INSERT OR IGNORE INTO nodes (id, label, name) VALUES (?, ?, ?)",
            (name, "Concept", name.replace("_", " ").title())
        )
    # node_b: 2x REQUIRES + 1x STARTS_AFTER = 3 inbound
    for src, rel in [("node_a", "REQUIRES"), ("node_d", "REQUIRES"), ("node_e", "STARTS_AFTER")]:
        cursor.execute(
            "INSERT OR IGNORE INTO edges (id, document_id, source_id, target_id, relationship, source_chunk_id) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            (f"{document_id}_{src}_{rel}_b", document_id, src, "node_b", rel, f"{document_id}_chunk_1")
        )
    # node_c: 1x REQUIRES only
    cursor.execute(
        "INSERT OR IGNORE INTO edges (id, document_id, source_id, target_id, relationship, source_chunk_id) "
        "VALUES (?, ?, ?, ?, ?, ?)",
        (f"{document_id}_a_req_c", document_id, "node_a", "node_c", "REQUIRES", f"{document_id}_chunk_1")
    )
    vault.conn.commit()


class TestGetHubVulnerabilities:
    def test_returns_list(self, vault):
        _seed_hub_graph(vault)
        result = vault.get_hub_vulnerabilities("doc_hubs")
        assert isinstance(result, list)

    def test_hub_node_returned_with_correct_count(self, vault):
        _seed_hub_graph(vault)
        result = vault.get_hub_vulnerabilities("doc_hubs")
        assert len(result) == 2
        top = result[0]
        assert top["id"] == "node_b"
        assert top["dependency_count"] == 3

    def test_result_includes_name_and_label(self, vault):
        _seed_hub_graph(vault)
        result = vault.get_hub_vulnerabilities("doc_hubs")
        top = result[0]
        assert top["name"] == "Node B"
        assert top["label"] == "Concept"

    def test_ordered_by_dependency_count_descending(self, vault):
        _seed_hub_graph(vault)
        result = vault.get_hub_vulnerabilities("doc_hubs")
        counts = [r["dependency_count"] for r in result]
        assert counts == sorted(counts, reverse=True)

    def test_limit_respected(self, vault):
        _seed_hub_graph(vault)
        result = vault.get_hub_vulnerabilities("doc_hubs", limit=1)
        assert len(result) == 1

    def test_scoped_to_document(self, vault):
        _seed_hub_graph(vault, "doc_a")
        # Seed a second document with its own hub — should NOT appear in doc_a results
        vault.insert_document("doc_b", "other.pdf")
        cursor = vault.conn.cursor()
        for name in ["b_x", "b_y", "b_z", "b_hub"]:
            cursor.execute(
                "INSERT OR IGNORE INTO nodes (id, label, name) VALUES (?, ?, ?)",
                (name, "Concept", name)
            )
        for src in ["b_x", "b_y", "b_z"]:
            cursor.execute(
                "INSERT OR IGNORE INTO edges (id, document_id, source_id, target_id, relationship, source_chunk_id) "
                "VALUES (?, ?, ?, ?, ?, ?)",
                (f"doc_b_{src}_req_hub", "doc_b", src, "b_hub", "REQUIRES", "doc_b_chunk_1")
            )
        vault.conn.commit()
        result = vault.get_hub_vulnerabilities("doc_a")
        ids = [r["id"] for r in result]
        assert "b_hub" not in ids

    def test_empty_document_returns_empty_list(self, vault):
        vault.insert_document("doc_empty", "empty.pdf")
        result = vault.get_hub_vulnerabilities("doc_empty")
        assert result == []
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_vault_reporting.py -v`
Expected: FAIL with `AttributeError: 'HybridVault' object has no attribute 'get_hub_vulnerabilities'`

- [ ] **Step 3: Implement `get_hub_vulnerabilities` in vault.py**

Add this method to `HybridVault` in `core/vault.py`, after `get_fragility_lines`:

```python
def get_hub_vulnerabilities(self, document_id: str, limit: int = 10) -> List[Dict[str, Any]]:
    """
    Calculates In-Degree Centrality to identify single points of failure.
    Counts all REQUIRES and STARTS_AFTER edges pointing at each node,
    scoped to the given document, ordered by dependency count descending.
    """
    cursor = self.conn.cursor()
    cursor.execute("""
        SELECT
            n.id,
            n.name,
            n.label,
            COUNT(e.id) AS dependency_count
        FROM nodes n
        JOIN edges e ON n.id = e.target_id
        WHERE e.relationship IN ('REQUIRES', 'STARTS_AFTER')
          AND e.document_id = ?
        GROUP BY n.id
        ORDER BY dependency_count DESC
        LIMIT ?
    """, (document_id, limit))
    return [dict(row) for row in cursor.fetchall()]
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_vault_reporting.py -v`
Expected: All 7 tests PASS

- [ ] **Step 5: Commit**

```bash
git add core/vault.py tests/test_vault_reporting.py
git commit -m "feat(vault): add get_hub_vulnerabilities for in-degree centrality reporting"
```

---

## Task 2: Reporting API endpoints

**Files:**
- Modify: `api.py`
- Create: `tests/test_api_reporting.py`

- [ ] **Step 1: Write the failing tests**

Create `tests/test_api_reporting.py`:

```python
import pytest
from fastapi.testclient import TestClient
from unittest.mock import patch, MagicMock

from api import app


def _make_mock_vault(doc_exists=True, friction_lines=None, chron_lines=None, bottlenecks=None):
    mock_vault = MagicMock()
    mock_vault.list_documents.return_value = []

    def fresh_cursor():
        cur = MagicMock()
        cur.fetchone.return_value = {"id": "doc_abc"} if doc_exists else None
        cur.fetchall.return_value = []
        return cur

    mock_vault.conn.cursor.side_effect = fresh_cursor
    mock_vault.get_friction_lines.return_value = friction_lines or []
    mock_vault.get_chronological_friction_lines.return_value = chron_lines or []
    mock_vault.get_hub_vulnerabilities.return_value = bottlenecks or []
    return mock_vault


class TestFrictionQueueEndpoint:
    def test_returns_200_with_empty_queues(self):
        mock_vault = _make_mock_vault()
        with patch("api.vault", mock_vault):
            with TestClient(app) as c:
                response = c.get("/api/v1/reports/friction-queue/doc_abc")
        assert response.status_code == 200

    def test_response_has_friction_queue_key(self):
        mock_vault = _make_mock_vault()
        with patch("api.vault", mock_vault):
            with TestClient(app) as c:
                response = c.get("/api/v1/reports/friction-queue/doc_abc")
        assert "friction_queue" in response.json()

    def test_structural_friction_included_with_type_field(self):
        structural = [{"source": "node_a", "target": "node_b", "diamond": "conflict", "provenance_ids": []}]
        mock_vault = _make_mock_vault(friction_lines=structural)
        with patch("api.vault", mock_vault):
            with TestClient(app) as c:
                response = c.get("/api/v1/reports/friction-queue/doc_abc")
        queue = response.json()["friction_queue"]
        assert len(queue) == 1
        assert queue[0]["type"] == "structural"

    def test_chronological_friction_included_with_type_field(self):
        chron = [{"source": "node_a", "target": "node_b", "diamond": "schedule clash", "provenance_ids": []}]
        mock_vault = _make_mock_vault(chron_lines=chron)
        with patch("api.vault", mock_vault):
            with TestClient(app) as c:
                response = c.get("/api/v1/reports/friction-queue/doc_abc")
        queue = response.json()["friction_queue"]
        assert len(queue) == 1
        assert queue[0]["type"] == "chronological"

    def test_combines_both_types(self):
        structural = [{"source": "a", "target": "b", "diamond": "s", "provenance_ids": []}]
        chron = [{"source": "c", "target": "d", "diamond": "c", "provenance_ids": []}]
        mock_vault = _make_mock_vault(friction_lines=structural, chron_lines=chron)
        with patch("api.vault", mock_vault):
            with TestClient(app) as c:
                response = c.get("/api/v1/reports/friction-queue/doc_abc")
        queue = response.json()["friction_queue"]
        assert len(queue) == 2

    def test_returns_404_for_missing_document(self):
        mock_vault = _make_mock_vault(doc_exists=False)
        with patch("api.vault", mock_vault):
            with TestClient(app) as c:
                response = c.get("/api/v1/reports/friction-queue/doc_missing")
        assert response.status_code == 404


class TestBottlenecksEndpoint:
    def test_returns_200(self):
        mock_vault = _make_mock_vault()
        with patch("api.vault", mock_vault):
            with TestClient(app) as c:
                response = c.get("/api/v1/reports/bottlenecks/doc_abc")
        assert response.status_code == 200

    def test_response_has_bottlenecks_key(self):
        mock_vault = _make_mock_vault()
        with patch("api.vault", mock_vault):
            with TestClient(app) as c:
                response = c.get("/api/v1/reports/bottlenecks/doc_abc")
        assert "bottlenecks" in response.json()

    def test_bottlenecks_data_returned(self):
        hubs = [{"id": "node_b", "name": "Node B", "label": "Concept", "dependency_count": 5}]
        mock_vault = _make_mock_vault(bottlenecks=hubs)
        with patch("api.vault", mock_vault):
            with TestClient(app) as c:
                response = c.get("/api/v1/reports/bottlenecks/doc_abc")
        assert response.json()["bottlenecks"] == hubs

    def test_returns_404_for_missing_document(self):
        mock_vault = _make_mock_vault(doc_exists=False)
        with patch("api.vault", mock_vault):
            with TestClient(app) as c:
                response = c.get("/api/v1/reports/bottlenecks/doc_missing")
        assert response.status_code == 404

    def test_calls_get_hub_vulnerabilities_with_limit_5(self):
        mock_vault = _make_mock_vault()
        with patch("api.vault", mock_vault):
            with TestClient(app) as c:
                c.get("/api/v1/reports/bottlenecks/doc_abc")
        mock_vault.get_hub_vulnerabilities.assert_called_once_with("doc_abc", limit=5)
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_api_reporting.py -v`
Expected: All 11 tests FAIL with 404/AttributeError — endpoints don't exist yet

- [ ] **Step 3: Implement the two endpoints in api.py**

Add these two endpoints to `api.py`, after the existing `delete_document_endpoint` and before the `canvas` endpoint:

```python
@app.get("/api/v1/reports/friction-queue/{document_id}")
async def get_friction_queue(document_id: str):
    """
    Delivers the ITDO Operational Dashboard.
    Returns all structural and chronological friction lines for a document,
    tagged with their type. Uses persisted vault data — works after server restart.
    """
    cursor = vault.conn.cursor()
    cursor.execute("SELECT id FROM documents WHERE id = ?", (document_id,))
    if cursor.fetchone() is None:
        raise HTTPException(status_code=404, detail="Document not found.")

    structural = [
        {**line, "type": "structural"}
        for line in vault.get_friction_lines(document_id)
    ]
    chronological = [
        {**line, "type": "chronological"}
        for line in vault.get_chronological_friction_lines(document_id)
    ]
    return {"friction_queue": structural + chronological}


@app.get("/api/v1/reports/bottlenecks/{document_id}")
async def get_bottlenecks(document_id: str):
    """
    Delivers the Hub & Spoke Tactical Dashboard.
    Returns the top 5 nodes by in-degree centrality (REQUIRES + STARTS_AFTER).
    """
    cursor = vault.conn.cursor()
    cursor.execute("SELECT id FROM documents WHERE id = ?", (document_id,))
    if cursor.fetchone() is None:
        raise HTTPException(status_code=404, detail="Document not found.")

    vulnerabilities = vault.get_hub_vulnerabilities(document_id, limit=5)
    return {"bottlenecks": vulnerabilities}
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_api_reporting.py -v`
Expected: All 11 tests PASS

- [ ] **Step 5: Commit**

```bash
git add api.py tests/test_api_reporting.py
git commit -m "feat(api): add friction-queue and bottlenecks reporting endpoints"
```

---

## Task 3: Executive Dashboard UI

**Files:**
- Modify: `static/index.html`

There are no automated tests for the frontend. After each sub-step, do a manual check by running `python run.py` and loading the app.

### Step 3a — CSS

- [ ] **Step 1: Add dashboard CSS**

In `static/index.html`, inside the `<style>` block, add the following after the `.stat-value.chronological` rule (line 224), before `</style>`:

```css
        /* ── Executive Dashboard ── */
        #reporting-dashboard {
            position: absolute; bottom: 0; left: 0; right: 0; z-index: 20;
            background: #161b22; border-top: 1px solid #30363d;
            transform: translateY(100%); transition: transform 0.35s ease-in-out;
            max-height: 55vh; display: flex; flex-direction: column;
        }
        #reporting-dashboard.open { transform: translateY(0); }

        .dashboard-header {
            display: flex; align-items: center; justify-content: space-between;
            padding: 12px 20px; border-bottom: 1px solid #30363d; flex-shrink: 0;
        }
        .dashboard-header h2 { margin: 0; font-size: 0.95rem; color: #c9d1d9; font-weight: 600; }
        .dashboard-header button {
            background: transparent; border: 1px solid #30363d; color: #8b949e;
            padding: 4px 12px; border-radius: 6px; cursor: pointer; font-size: 0.8rem;
            transition: border-color 0.2s, color 0.2s;
        }
        .dashboard-header button:hover { border-color: #8b949e; color: #c9d1d9; }

        .dashboard-grid {
            display: grid; grid-template-columns: 1fr 1fr; gap: 0;
            overflow-y: auto; flex-grow: 1;
        }
        .dashboard-grid::-webkit-scrollbar { width: 4px; }
        .dashboard-grid::-webkit-scrollbar-thumb { background: #30363d; border-radius: 2px; }

        .report-card { padding: 16px 20px; border-right: 1px solid #30363d; }
        .report-card:last-child { border-right: none; }
        .report-card h3 { margin: 0 0 4px; font-size: 0.85rem; color: #c9d1d9; font-weight: 600; }
        .report-card .subtitle { margin: 0 0 12px; font-size: 0.75rem; color: #8b949e; }

        #bottleneck-table { width: 100%; border-collapse: collapse; font-size: 0.82rem; }
        #bottleneck-table th {
            text-align: left; color: #8b949e; font-size: 0.7rem; text-transform: uppercase;
            letter-spacing: 0.08em; padding: 0 0 8px; font-weight: 500;
        }
        #bottleneck-table td { padding: 6px 0; border-bottom: 1px solid #21262d; }
        #bottleneck-table tr:last-child td { border-bottom: none; }

        #friction-list { list-style: none; margin: 0; padding: 0; }
        #friction-list li {
            cursor: pointer; border-left: 3px solid #ff7b72; margin-bottom: 8px;
            padding: 8px 10px; background: #0d1117; border-radius: 0 4px 4px 0;
            font-size: 0.8rem; line-height: 1.4; transition: background 0.15s;
        }
        #friction-list li.chronological { border-left-color: #d29922; }
        #friction-list li:hover { background: #1c2128; }
        #friction-list li .friction-type {
            font-size: 0.68rem; text-transform: uppercase; letter-spacing: 0.08em;
            margin-bottom: 3px; color: #ff7b72; font-weight: 600;
        }
        #friction-list li.chronological .friction-type { color: #d29922; }
        #friction-list li .friction-snippet { color: #c9d1d9; }

        #report-btn { display: none; }
```

- [ ] **Step 2: Add toolbar button and dashboard HTML**

In `static/index.html`, find the `#toolbar` div (line 254):
```html
    <div id="toolbar">
        <button class="toolbar-btn" onclick="showOverlay()">&#128196; Documents</button>
        <div id="toolbar-divider"></div>
```

Replace with:
```html
    <div id="toolbar">
        <button class="toolbar-btn" onclick="showOverlay()">&#128196; Documents</button>
        <button class="toolbar-btn" id="report-btn" onclick="toggleDashboard()">&#128202; Report</button>
        <div id="toolbar-divider"></div>
```

Then, add the dashboard HTML immediately before `<div id="toast">` (line 311):

```html
    <div id="reporting-dashboard">
        <div class="dashboard-header">
            <h2>&#128202; Executive Intelligence Report</h2>
            <button onclick="toggleDashboard()">Close</button>
        </div>
        <div class="dashboard-grid">
            <div class="report-card">
                <h3>Top Systemic Bottlenecks</h3>
                <p class="subtitle">Nodes with the highest concentration of inbound dependencies.</p>
                <table id="bottleneck-table">
                    <thead>
                        <tr>
                            <th>Concept / Node</th>
                            <th style="text-align:right;">Inbound Links</th>
                        </tr>
                    </thead>
                    <tbody id="bottleneck-body"></tbody>
                </table>
            </div>
            <div class="report-card">
                <h3>Friction Resolution Queue</h3>
                <p class="subtitle">Click any item to fly to it in the knowledge graph.</p>
                <ul id="friction-list"></ul>
            </div>
        </div>
    </div>
```

- [ ] **Step 3: Add JS functions**

In `static/index.html`, inside the `<script>` block, add these functions after the `showToast` function (after line 851):

```javascript
        // ── 9. Executive Dashboard ──
        let dashboardOpen = false;

        function toggleDashboard() {
            dashboardOpen = !dashboardOpen;
            document.getElementById('reporting-dashboard').classList.toggle('open', dashboardOpen);
        }

        async function loadReportingDashboard(documentId) {
            try {
                // ── Bottlenecks ──
                const bottleneckRes = await fetch(`/api/v1/reports/bottlenecks/${documentId}`);
                const bottleneckData = await bottleneckRes.json();
                const tbody = document.getElementById('bottleneck-body');
                tbody.innerHTML = '';
                if (bottleneckData.bottlenecks.length === 0) {
                    tbody.innerHTML = '<tr><td colspan="2" style="color:#8b949e;font-size:0.8rem;padding:8px 0;">No hub nodes detected.</td></tr>';
                } else {
                    bottleneckData.bottlenecks.forEach(b => {
                        const tr = document.createElement('tr');
                        tr.innerHTML = `
                            <td style="color:#58a6ff;font-weight:500;">${escHtml(b.name)}</td>
                            <td style="color:#ff7b72;text-align:right;font-weight:600;">${b.dependency_count}</td>
                        `;
                        tbody.appendChild(tr);
                    });
                }

                // ── Friction Queue ──
                const queueRes = await fetch(`/api/v1/reports/friction-queue/${documentId}`);
                const queueData = await queueRes.json();
                const list = document.getElementById('friction-list');
                list.innerHTML = '';
                if (queueData.friction_queue.length === 0) {
                    list.innerHTML = '<li style="border-left-color:#30363d;cursor:default;"><span style="color:#8b949e;">No friction detected.</span></li>';
                } else {
                    queueData.friction_queue.forEach(f => {
                        const isChron = f.type === 'chronological';
                        const typeLabel = isChron ? 'Timeline Collapse' : 'Logic Paradox';
                        const snippet = (f.diamond || '').substring(0, 100).trimEnd();
                        const li = document.createElement('li');
                        if (isChron) li.classList.add('chronological');
                        li.innerHTML = `
                            <div class="friction-type">${escHtml(typeLabel)}</div>
                            <div class="friction-snippet">${escHtml(snippet)}${f.diamond && f.diamond.length > 100 ? '…' : ''}</div>
                        `;
                        li.addEventListener('click', () => {
                            // Find the resolved link object in the live graph data
                            const graphData = Graph.graphData();
                            const match = graphData.links.find(l => {
                                const srcId = l.source?.id || l.source;
                                const tgtId = l.target?.id || l.target;
                                return srcId === f.source && tgtId === f.target && l.diamond === f.diamond;
                            });
                            if (match) {
                                if (isChron) openChronologicalPanel(match);
                                else openFrictionPanel(match);
                            }
                        });
                        list.appendChild(li);
                    });
                }
            } catch (err) {
                console.error('Failed to load reporting dashboard:', err);
            }
        }
```

- [ ] **Step 4: Wire `loadReportingDashboard` into `loadCanvasData`**

In `static/index.html`, find this line near the end of `loadCanvasData` (inside the `try` block, after the stats HUD section, before `} catch(e)`):

```javascript
            } catch(e) {
                console.error('Failed to load graph data:', e);
            }
```

Add the dashboard call and report button reveal just before `} catch(e)`:

```javascript
                // Show Report button and pre-load dashboard data
                document.getElementById('report-btn').style.display = 'inline-block';
                loadReportingDashboard(documentId);

            } catch(e) {
                console.error('Failed to load graph data:', e);
            }
```

- [ ] **Step 5: Manual smoke test**

Run: `python run.py`

Open `http://localhost:8000` in a browser.

Verify:
1. Upload a PDF — ingestion completes, canvas renders.
2. A "Report" button appears in the toolbar.
3. Clicking "Report" slides up the Executive Dashboard panel.
4. The Bottlenecks table shows hub nodes (or "No hub nodes detected." if the document has no hubs).
5. The Friction Queue lists paradoxes (or "No friction detected.").
6. Clicking a friction queue item closes the overlay and opens the side panel with the analysis.
7. Clicking "Close" on the dashboard slides it back down.
8. Loading a previously ingested document from the document list also shows the Report button and loads the dashboard.

- [ ] **Step 6: Commit**

```bash
git add static/index.html
git commit -m "feat(ui): add Executive Dashboard with Friction Queue and Bottleneck Report"
```

---

## Run the Full Test Suite

After all three tasks are complete, run the full suite to confirm nothing is broken:

- [ ] **Run all tests**

```bash
pytest tests/ -v
```

Expected: All tests PASS (including pre-existing tests for vault delete, fragility, temporal, chronos agent, and API delete).

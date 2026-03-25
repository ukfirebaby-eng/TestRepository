# Executive Intelligence Report Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a "📋 Plain English" toolbar button that generates, caches, and displays an AI-written plain-English executive summary of all detected issues, with three layers of omission prevention and PDF/clipboard export.

**Architecture:** A streamed multi-agent pipeline (StorytellerAgent → CriticAgent → KDECoverageCheck) is triggered by a new POST endpoint that returns `text/event-stream`. The completed report is cached in a new `executive_summaries` SQLite table and served instantly on repeat visits via a GET endpoint. The UI renders a full-page report that replaces the 3D canvas while open.

**Tech Stack:** Python + FastAPI + OpenAI (via existing `_get_client()`) + ChromaDB (existing vault collection) + numpy (transitive dep) + Vanilla JS (`StreamingResponse`, `EventSource`, `window.print()`, `navigator.clipboard`)

**Spec:** `docs/superpowers/specs/2026-03-25-executive-report-design.md`

---

## Design Decisions

**`_gather_raw_issues` is a private helper in `api.py`, not a vault method.**
It collates data from four existing vault methods (`get_friction_lines`, `get_chronological_friction_lines`, `get_hub_vulnerabilities`, `get_risk_matrix_data`) into a single dict for the Storyteller prompt. It belongs in `api.py` alongside the endpoint that calls it.

**KDE coverage check uses cosine similarity gap detection, not full KDE.**
The spec describes the goal (flag uncovered semantic clusters) and names numpy as the tool. scipy is not a guaranteed transitive dependency. A cosine similarity gap check — embed output texts, compute max similarity of each source chunk to any output text, flag gaps below a threshold — achieves the same guarantee using only numpy and is fully testable.

**`_active_generations` is a module-level `set` in `api.py`.**
FastAPI's async event loop is single-threaded. A plain Python `set` is safe without a lock. The set is declared at module level so it persists across requests within a server session.

**SSE progress events are sent before the blocking LLM call they announce.**
"Drafting..." fires before `StorytellerAgent.run()`. This means the UI shows meaningful progress rather than silence during long API calls.

**StorytellerAgent and CriticAgent call `_get_client()` and `_get_model()` from agents.py.**
This gives them automatic OpenRouter support and environment-variable model overrides — consistent with every other agent in the file.

---

## File Map

| File | Change |
|------|--------|
| `core/vault.py` | Add `executive_summaries` table to `initialize_schemas()`; add `get_executive_summary`, `save_executive_summary`, `delete_executive_summary` methods |
| `core/agents.py` | Add `StorytellerAgent`, `CriticAgent`, `KDECoverageCheck` classes |
| `api.py` | Add `StreamingResponse` import; add `_active_generations` set; add `_gather_raw_issues` helper; add GET, POST, DELETE endpoints |
| `static/index.html` | Add toolbar button; add `#report-page` HTML + CSS; add JS: `openPlainEnglishReport`, `renderReportPage`, `regenerateReport`, `downloadReportPDF`, `copyReportToClipboard`; add `@media print` CSS |
| `tests/test_vault_executive.py` | New — unit tests for 3 vault methods |
| `tests/test_api_executive.py` | New — unit tests for all 3 API endpoints |

---

## Task 1: Vault layer — `executive_summaries` table and methods

**Files:**
- Modify: `core/vault.py`
- Create: `tests/test_vault_executive.py`

---

- [ ] **Step 1: Write the failing tests**

Create `tests/test_vault_executive.py`:

```python
import json
import pytest
from core.vault import HybridVault


@pytest.fixture
def vault(tmp_path):
    v = HybridVault(tenant_id="test_exec", base_dir=str(tmp_path))
    yield v
    v.conn.close()


def _sample_report():
    return {
        "overall_assessment": "Moderate Risk",
        "generated_at": "2026-03-25T12:00:00Z",
        "summary_narrative": "Three issues detected.",
        "business_impact": "Risk of delay.",
        "issues": [{"severity": "high", "title": "Test", "plain_english": "Test.", "solution": "Fix it.", "source_nodes": []}],
        "coverage_verified": True,
        "coverage_warning": None,
    }


class TestGetExecutiveSummary:
    def test_returns_none_when_no_cache(self, vault):
        vault.insert_document("doc_1", "test.pdf")
        assert vault.get_executive_summary("doc_1") is None

    def test_returns_none_for_unknown_document(self, vault):
        assert vault.get_executive_summary("doc_missing") is None


class TestSaveExecutiveSummary:
    def test_save_and_retrieve(self, vault):
        vault.insert_document("doc_1", "test.pdf")
        report = _sample_report()
        vault.save_executive_summary("doc_1", report, "gpt-4o")
        result = vault.get_executive_summary("doc_1")
        assert result is not None
        assert result["overall_assessment"] == "Moderate Risk"

    def test_returned_dict_matches_saved(self, vault):
        vault.insert_document("doc_1", "test.pdf")
        report = _sample_report()
        vault.save_executive_summary("doc_1", report, "gpt-4o")
        result = vault.get_executive_summary("doc_1")
        assert result["issues"][0]["title"] == "Test"
        assert result["coverage_verified"] is True

    def test_overwrite_replaces_existing(self, vault):
        vault.insert_document("doc_1", "test.pdf")
        vault.save_executive_summary("doc_1", _sample_report(), "gpt-4o")
        updated = _sample_report()
        updated["overall_assessment"] = "High Risk"
        vault.save_executive_summary("doc_1", updated, "gpt-4o")
        result = vault.get_executive_summary("doc_1")
        assert result["overall_assessment"] == "High Risk"


class TestDeleteExecutiveSummary:
    def test_delete_removes_cache(self, vault):
        vault.insert_document("doc_1", "test.pdf")
        vault.save_executive_summary("doc_1", _sample_report(), "gpt-4o")
        vault.delete_executive_summary("doc_1")
        assert vault.get_executive_summary("doc_1") is None

    def test_delete_is_idempotent(self, vault):
        vault.insert_document("doc_1", "test.pdf")
        # No cache row exists — should not raise
        vault.delete_executive_summary("doc_1")
        vault.delete_executive_summary("doc_1")  # second call also safe
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
pytest tests/test_vault_executive.py -v
```

Expected: FAIL — `AttributeError: 'HybridVault' object has no attribute 'get_executive_summary'`

---

- [ ] **Step 3: Add `executive_summaries` table to `initialize_schemas` in `core/vault.py`**

Inside `initialize_schemas()`, after the `temporal_metadata` table creation and before `self.conn.commit()`, add:

```python
        # Executive Summaries Cache — persists AI-generated plain-English reports
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS executive_summaries (
                document_id   TEXT PRIMARY KEY,
                generated_at  TEXT NOT NULL,
                model         TEXT NOT NULL,
                report_json   TEXT NOT NULL
            )
        """)
```

---

- [ ] **Step 4: Add the three vault methods to `core/vault.py`**

Add these methods to `HybridVault` after `get_hub_vulnerabilities`:

```python
    def get_executive_summary(self, document_id: str) -> Optional[Dict[str, Any]]:
        """Returns the cached plain-English report for a document, or None if not yet generated."""
        cursor = self.conn.cursor()
        cursor.execute(
            "SELECT report_json FROM executive_summaries WHERE document_id = ?",
            (document_id,)
        )
        row = cursor.fetchone()
        if row is None:
            return None
        return json.loads(row["report_json"])

    def save_executive_summary(self, document_id: str, report: Dict[str, Any], model: str) -> None:
        """Writes or overwrites the cached plain-English report for a document."""
        generated_at = report.get("generated_at", datetime.now(timezone.utc).isoformat())
        with self._write_lock:
            cursor = self.conn.cursor()
            cursor.execute(
                """
                INSERT INTO executive_summaries (document_id, generated_at, model, report_json)
                VALUES (?, ?, ?, ?)
                ON CONFLICT(document_id) DO UPDATE SET
                    generated_at = excluded.generated_at,
                    model        = excluded.model,
                    report_json  = excluded.report_json
                """,
                (document_id, generated_at, model, json.dumps(report))
            )
            self.conn.commit()

    def delete_executive_summary(self, document_id: str) -> None:
        """Removes the cached report for a document. Safe to call even if no cache exists."""
        with self._write_lock:
            cursor = self.conn.cursor()
            cursor.execute(
                "DELETE FROM executive_summaries WHERE document_id = ?",
                (document_id,)
            )
            self.conn.commit()
```

---

- [ ] **Step 5: Run tests to verify they pass**

```bash
pytest tests/test_vault_executive.py -v
```

Expected: All 7 tests PASS

---

- [ ] **Step 6: Commit**

```bash
git add core/vault.py tests/test_vault_executive.py
git commit -m "feat(vault): add executive_summaries cache table and get/save/delete methods"
```

---

## Task 2: Agent pipeline — StorytellerAgent, CriticAgent, KDECoverageCheck

**Files:**
- Modify: `core/agents.py`
- Create: `tests/test_agents_executive.py`

---

- [ ] **Step 1: Write the failing tests**

Create `tests/test_agents_executive.py`:

```python
import json
import pytest
import numpy as np
from unittest.mock import MagicMock, patch


# ── Helpers ──────────────────────────────────────────────────────────────────

def _raw_issues():
    return {
        "friction_lines": [
            {"source": "node_a", "target": "node_b", "diamond": "Conflict A", "severity": 5, "probability": 4}
        ],
        "chronological_friction_lines": [],
        "hub_vulnerabilities": [],
        "risk_matrix": [],
    }


def _draft_report(issues=None):
    return {
        "overall_assessment": "High Risk",
        "generated_at": "2026-03-25T12:00:00Z",
        "summary_narrative": "One issue found.",
        "business_impact": "May cause delay.",
        "issues": issues or [
            {
                "severity": "critical",
                "title": "Launch before legal",
                "plain_english": "Legal review not complete.",
                "solution": "Delay launch.",
                "source_nodes": ["node_a", "node_b"],
            }
        ],
        "coverage_verified": True,
        "coverage_warning": None,
    }


def _make_openai_response(content: str):
    mock_response = MagicMock()
    mock_response.choices[0].message.content = content
    return mock_response


# ── StorytellerAgent ──────────────────────────────────────────────────────────

class TestStorytellerAgent:
    def test_run_returns_dict(self):
        from core.agents import StorytellerAgent
        agent = StorytellerAgent()
        mock_client = MagicMock()
        mock_client.chat.completions.create.return_value = _make_openai_response(
            json.dumps(_draft_report())
        )
        with patch("core.agents._get_client", return_value=mock_client):
            result = agent.run(_raw_issues())
        assert isinstance(result, dict)

    def test_run_includes_required_keys(self):
        from core.agents import StorytellerAgent
        agent = StorytellerAgent()
        mock_client = MagicMock()
        mock_client.chat.completions.create.return_value = _make_openai_response(
            json.dumps(_draft_report())
        )
        with patch("core.agents._get_client", return_value=mock_client):
            result = agent.run(_raw_issues())
        for key in ["overall_assessment", "summary_narrative", "business_impact", "issues", "coverage_verified"]:
            assert key in result

    def test_run_injects_must_include_for_critical_issues(self):
        from core.agents import StorytellerAgent
        agent = StorytellerAgent()
        mock_client = MagicMock()
        mock_client.chat.completions.create.return_value = _make_openai_response(
            json.dumps(_draft_report())
        )
        raw = _raw_issues()
        raw["friction_lines"][0]["severity"] = 5  # Critical
        with patch("core.agents._get_client", return_value=mock_client):
            agent.run(raw)
        call_args = mock_client.chat.completions.create.call_args
        prompt_text = str(call_args)
        assert "MUST INCLUDE" in prompt_text

    def test_zero_issues_returns_no_issues_found_report(self):
        from core.agents import StorytellerAgent
        agent = StorytellerAgent()
        empty_raw = {"friction_lines": [], "chronological_friction_lines": [], "hub_vulnerabilities": [], "risk_matrix": []}
        result = agent.run(empty_raw)
        assert result["overall_assessment"] == "No Issues Found"
        assert result["issues"] == []
        assert result["coverage_verified"] is True


# ── CriticAgent ───────────────────────────────────────────────────────────────

class TestCriticAgent:
    def test_returns_report_unchanged_when_no_gaps(self):
        from core.agents import CriticAgent
        agent = CriticAgent()
        mock_client = MagicMock()
        # Critic returns empty list — no gaps
        mock_client.chat.completions.create.return_value = _make_openai_response("[]")
        with patch("core.agents._get_client", return_value=mock_client):
            result = agent.run(_draft_report(), _raw_issues())
        assert result["overall_assessment"] == "High Risk"

    def test_triggers_revision_when_gaps_found(self):
        from core.agents import StorytellerAgent, CriticAgent
        critic = CriticAgent()
        storyteller = MagicMock()
        revised = _draft_report()
        revised["overall_assessment"] = "Revised"
        storyteller.run.return_value = revised

        mock_client = MagicMock()
        # First critic call finds a gap; second finds none
        mock_client.chat.completions.create.side_effect = [
            _make_openai_response('[{"diamond": "Missing issue"}]'),
            _make_openai_response("[]"),
        ]
        with patch("core.agents._get_client", return_value=mock_client):
            result = critic.run(_draft_report(), _raw_issues(), storyteller=storyteller)

        assert storyteller.run.called
        assert result["overall_assessment"] == "Revised"

    def test_appends_coverage_warning_after_max_retries(self):
        from core.agents import StorytellerAgent, CriticAgent
        critic = CriticAgent()
        storyteller = MagicMock()
        storyteller.run.return_value = _draft_report()

        mock_client = MagicMock()
        # Critic always finds gaps across both retry attempts
        mock_client.chat.completions.create.side_effect = [
            _make_openai_response('[{"diamond": "Persistent gap"}]'),
            _make_openai_response('[{"diamond": "Persistent gap"}]'),
        ]
        with patch("core.agents._get_client", return_value=mock_client):
            result = critic.run(_draft_report(), _raw_issues(), storyteller=storyteller)

        assert result["coverage_verified"] is False
        assert result["coverage_warning"] is not None


# ── KDECoverageCheck ──────────────────────────────────────────────────────────

class TestKDECoverageCheck:
    def _make_vault_with_embeddings(self, source_embeddings, source_ids):
        mock_vault = MagicMock()
        mock_vault.conn.cursor.return_value.fetchall.return_value = [
            {"source_chunk_id": sid} for sid in source_ids
        ]
        mock_vault.collection.get.return_value = {
            "embeddings": source_embeddings,
            "ids": source_ids,
        }
        return mock_vault

    def test_coverage_verified_true_when_output_covers_source(self):
        from core.agents import KDECoverageCheck
        # Source and output are identical vectors — maximum similarity
        vecs = [[1.0, 0.0, 0.0], [0.0, 1.0, 0.0]]
        mock_vault = self._make_vault_with_embeddings(vecs, ["chunk_1", "chunk_2"])
        # Attach a mock embedding function to the vault's collection
        mock_vault.collection._embedding_function = MagicMock(
            return_value=[[1.0, 0.0, 0.0], [0.0, 1.0, 0.0]]
        )
        report = _draft_report(issues=[
            {"severity": "high", "title": "T", "plain_english": "covered text", "solution": "s", "source_nodes": []},
        ])
        checker = KDECoverageCheck(mock_vault)
        result = checker.check("doc_1", report)
        assert result["coverage_verified"] is True
        assert result["coverage_warning"] is None

    def test_coverage_warning_set_when_cluster_uncovered(self):
        from core.agents import KDECoverageCheck
        # Source has a vector in a very different direction from the output
        source_vecs = [[1.0, 0.0, 0.0], [0.0, 0.0, 1.0]]  # second is orthogonal to output
        mock_vault = self._make_vault_with_embeddings(source_vecs, ["chunk_1", "chunk_2"])
        # Output embedding only covers the first vector direction
        mock_vault.collection._embedding_function = MagicMock(
            return_value=[[1.0, 0.0, 0.0]]
        )
        report = _draft_report(issues=[
            {"severity": "high", "title": "T", "plain_english": "covered", "solution": "s", "source_nodes": []},
        ])
        checker = KDECoverageCheck(mock_vault)
        result = checker.check("doc_1", report)
        assert result["coverage_verified"] is False
        assert result["coverage_warning"] is not None

    def test_returns_report_unchanged_when_no_source_chunks(self):
        from core.agents import KDECoverageCheck
        mock_vault = MagicMock()
        mock_vault.conn.cursor.return_value.fetchall.return_value = []
        mock_vault.collection.get.return_value = {"embeddings": [], "ids": []}
        checker = KDECoverageCheck(mock_vault)
        result = checker.check("doc_empty", _draft_report())
        assert result["coverage_verified"] is True
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
pytest tests/test_agents_executive.py -v
```

Expected: FAIL — `ImportError: cannot import name 'StorytellerAgent' from 'core.agents'`

---

- [ ] **Step 3: Add `StorytellerAgent` to `core/agents.py`**

Add after the last existing agent class:

```python
class StorytellerAgent:
    """
    Translates raw issue data into a plain-English executive report.
    Temperature 0.7 for natural prose. Returns a structured report_json dict.
    """

    SYSTEM_PROMPT = """You are an Executive Communication Specialist. Translate complex technical project risks into clear, plain-English summaries for senior business leaders who are not technical.

RULES:
1. Never use technical terms (no "node", "edge", "graph", "centrality", "vector", "contradiction").
2. Express every issue as a business consequence (cost, compliance, delay, dependency).
3. Use "issue" not "paradox" or "diamond".
4. Return ONLY valid JSON matching the schema below. No markdown, no preamble.

OUTPUT SCHEMA:
{
  "overall_assessment": "No Issues Found | Low Risk | Moderate Risk | High Risk | Critical Risk",
  "generated_at": "<ISO 8601 UTC timestamp>",
  "summary_narrative": "<2-3 sentence plain-English overview>",
  "business_impact": "<plain-English What This Means For You paragraph — mention specific business risks>",
  "issues": [
    {
      "severity": "critical | high | medium | low",
      "title": "<short plain-English title, max 10 words>",
      "plain_english": "<plain-English description of the problem and its business consequence>",
      "solution": "<plain-English recommended fix>",
      "source_nodes": ["<node_id>"]
    }
  ],
  "coverage_verified": true,
  "coverage_warning": null
}

Order issues: critical first, then high, then medium, then low."""

    def __init__(self):
        self.model = _get_model("smart")

    def run(self, raw_issues: Dict[str, Any]) -> Dict[str, Any]:
        """
        Generates a plain-English report from raw issue data.
        Returns immediately with a minimal report if no issues exist.
        """
        all_issues = (
            raw_issues.get("friction_lines", [])
            + raw_issues.get("chronological_friction_lines", [])
            + raw_issues.get("hub_vulnerabilities", [])
            + raw_issues.get("risk_matrix", [])
        )

        if not all_issues:
            return {
                "overall_assessment": "No Issues Found",
                "generated_at": datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ"),
                "summary_narrative": "No conflicts or risks were detected in this document.",
                "business_impact": "",
                "issues": [],
                "coverage_verified": True,
                "coverage_warning": None,
            }

        # Stage 0 — deterministic hard-stop injection
        critical = [
            i for i in all_issues
            if isinstance(i.get("severity"), int) and i["severity"] >= 5
        ]
        must_include_block = ""
        if critical:
            must_include_block = "\n\nMUST INCLUDE (these issues are mandatory — do not omit them):\n"
            must_include_block += json.dumps(critical, indent=2)

        user_prompt = (
            f"Here is the complete list of issues detected in this document:\n\n"
            f"{json.dumps(raw_issues, indent=2)}"
            f"{must_include_block}"
        )

        client = _get_client()
        response = client.chat.completions.create(
            model=self.model,
            temperature=0.7,
            response_format={"type": "json_object"},
            messages=[
                {"role": "system", "content": self.SYSTEM_PROMPT},
                {"role": "user", "content": user_prompt},
            ],
        )
        return json.loads(response.choices[0].message.content)
```

---

- [ ] **Step 4: Add `CriticAgent` to `core/agents.py`**

Add after `StorytellerAgent`:

```python
class CriticAgent:
    """
    Audits a draft report against the raw issue list.
    Finds omissions and triggers Storyteller revision (max 2 retries).
    Temperature 0.0 for deterministic auditing.
    """

    SYSTEM_PROMPT = """You are a meticulous audit specialist. You will be given:
1. A draft executive report (JSON)
2. A complete list of raw issues (JSON array)

Your ONLY job: identify raw issues that have NO representation in the draft report's issues array.

Return a JSON array of missing raw issues. If nothing is missing, return an empty array: []
Return ONLY valid JSON. No markdown, no explanation."""

    MAX_RETRIES = 2

    def run(
        self,
        draft: Dict[str, Any],
        raw_issues: Dict[str, Any],
        storyteller: Any = None,
    ) -> Dict[str, Any]:
        """
        Compares draft against raw_issues. Triggers Storyteller revision if gaps found.
        After MAX_RETRIES, appends a coverage_warning to the report instead of failing.
        """
        if storyteller is None:
            storyteller = StorytellerAgent()

        client = _get_client()
        current_draft = draft
        all_raw = (
            raw_issues.get("friction_lines", [])
            + raw_issues.get("chronological_friction_lines", [])
            + raw_issues.get("hub_vulnerabilities", [])
            + raw_issues.get("risk_matrix", [])
        )

        for attempt in range(self.MAX_RETRIES):
            response = client.chat.completions.create(
                model=_get_model("fast"),
                temperature=0.0,
                # No response_format here — the Critic returns a bare JSON array ([])
                # and json_object mode forbids bare arrays.
                messages=[
                    {"role": "system", "content": self.SYSTEM_PROMPT},
                    {"role": "user", "content": (
                        f"Draft report:\n{json.dumps(current_draft, indent=2)}\n\n"
                        f"Complete raw issue list:\n{json.dumps(all_raw, indent=2)}"
                    )},
                ],
            )
            content = response.choices[0].message.content
            try:
                parsed = json.loads(content)
                # Model should return a bare array; handle any wrapping defensively
                if isinstance(parsed, list):
                    gaps = parsed
                elif isinstance(parsed, dict):
                    # Flatten any top-level list value regardless of key name
                    list_values = [v for v in parsed.values() if isinstance(v, list)]
                    gaps = list_values[0] if list_values else []
                else:
                    gaps = []
            except (json.JSONDecodeError, AttributeError):
                gaps = []

            if not gaps:
                return current_draft

            # Inject missing items and regenerate
            injected = dict(raw_issues)
            injected["_forced_inclusions"] = gaps
            current_draft = storyteller.run(injected)

        # Max retries exhausted — append warning and return
        current_draft["coverage_verified"] = False
        current_draft["coverage_warning"] = (
            "Note: the AI could not fully verify that all issues are represented in this report. "
            "Please cross-reference the Friction Queue for the complete technical list."
        )
        return current_draft
```

---

- [ ] **Step 5: Add `KDECoverageCheck` to `core/agents.py`**

Add the import at the top of `core/agents.py` alongside existing imports:

```python
import numpy as np
```

Then add the class after `CriticAgent`:

```python
class KDECoverageCheck:
    """
    Verifies that the generated report semantically covers all source material.
    Uses cosine similarity gap detection with numpy — no API calls, no extra cost.

    For each source chunk embedding, finds the maximum cosine similarity to any
    output issue embedding. If any source chunk's max similarity is below the
    threshold, it is considered uncovered and a coverage_warning is appended.

    IMPORTANT: uses vault.collection._embedding_function — the same model used at
    ingestion time — so source and output embeddings are in the same vector space.
    """

    SIMILARITY_THRESHOLD = 0.25

    def __init__(self, vault: Any):
        self.vault = vault

    def check(self, document_id: str, report: Dict[str, Any]) -> Dict[str, Any]:
        """
        Compares source chunk embeddings to output issue embeddings.
        Returns the report dict with coverage_verified and coverage_warning set.
        """
        # 1. Collect source_chunk_ids from edges and friction_lines for this document
        cursor = self.vault.conn.cursor()
        cursor.execute(
            """
            SELECT DISTINCT source_chunk_id FROM edges WHERE document_id = ?
            UNION
            SELECT DISTINCT provenance_ids FROM friction_lines WHERE document_id = ?
            """,
            (document_id, document_id)
        )
        rows = cursor.fetchall()
        source_chunk_ids = [r["source_chunk_id"] for r in rows if r["source_chunk_id"]]

        if not source_chunk_ids:
            report["coverage_verified"] = True
            report["coverage_warning"] = None
            return report

        # 2. Fetch source embeddings from ChromaDB
        chroma_result = self.vault.collection.get(
            ids=source_chunk_ids,
            include=["embeddings"]
        )
        source_embeddings = chroma_result.get("embeddings") or []
        if not source_embeddings:
            report["coverage_verified"] = True
            report["coverage_warning"] = None
            return report

        source_matrix = np.array(source_embeddings, dtype=np.float32)

        # 3. Embed report issue texts using the SAME embedding function as ingestion.
        #    vault.collection._embedding_function is the ChromaDB collection's own EF —
        #    guaranteed to be in the same vector space as the stored source embeddings.
        issue_texts = [
            i.get("plain_english", "") for i in report.get("issues", [])
            if i.get("plain_english")
        ]
        if not issue_texts:
            report["coverage_verified"] = False
            report["coverage_warning"] = (
                "Note: the AI could not fully verify that all issues are represented in this report. "
                "Please cross-reference the Friction Queue for the complete technical list."
            )
            return report

        ef = self.vault.collection._embedding_function
        output_embeddings = ef(issue_texts)
        output_matrix = np.array(output_embeddings, dtype=np.float32)

        # 4. Cosine similarity: normalise both matrices then compute dot product
        def _l2_norm(m: np.ndarray) -> np.ndarray:
            norms = np.linalg.norm(m, axis=1, keepdims=True)
            norms = np.where(norms == 0, 1e-10, norms)
            return m / norms

        source_norm = _l2_norm(source_matrix)
        output_norm = _l2_norm(output_matrix)

        # similarity[i, j] = cosine similarity between source[i] and output[j]
        similarity = source_norm @ output_norm.T  # shape: (n_source, n_output)
        max_similarity_per_source = similarity.max(axis=1)  # shape: (n_source,)

        # 5. Flag if any source chunk is below threshold
        uncovered = np.sum(max_similarity_per_source < self.SIMILARITY_THRESHOLD)
        if uncovered > 0:
            report["coverage_verified"] = False
            report["coverage_warning"] = (
                "Note: the AI could not fully verify that all issues are represented in this report. "
                "Please cross-reference the Friction Queue for the complete technical list."
            )
        else:
            report["coverage_verified"] = True
            report["coverage_warning"] = None

        return report
```

---

- [ ] **Step 6: Run tests to verify they pass**

```bash
pytest tests/test_agents_executive.py -v
```

Expected: All 10 tests PASS

---

- [ ] **Step 7: Run full test suite to check nothing is broken**

```bash
pytest tests/ -v
```

Expected: All existing tests still PASS

---

- [ ] **Step 8: Commit**

```bash
git add core/agents.py tests/test_agents_executive.py
git commit -m "feat(agents): add StorytellerAgent, CriticAgent, and KDECoverageCheck"
```

---

## Task 3: API layer — GET, POST, DELETE endpoints

**Files:**
- Modify: `api.py`
- Create: `tests/test_api_executive.py`

---

- [ ] **Step 1: Write the failing tests**

Create `tests/test_api_executive.py`:

```python
import json
import pytest
from fastapi.testclient import TestClient
from unittest.mock import patch, MagicMock

from api import app


def _make_mock_vault(doc_exists=True, cached_report=None):
    mock_vault = MagicMock()

    def fresh_cursor():
        cur = MagicMock()
        cur.fetchone.return_value = {"id": "doc_abc"} if doc_exists else None
        cur.fetchall.return_value = []
        return cur

    mock_vault.conn.cursor.side_effect = fresh_cursor
    mock_vault.get_executive_summary.return_value = cached_report
    mock_vault.get_friction_lines.return_value = []
    mock_vault.get_chronological_friction_lines.return_value = []
    mock_vault.get_hub_vulnerabilities.return_value = []
    mock_vault.get_risk_matrix_data.return_value = []
    return mock_vault


def _minimal_report():
    return {
        "overall_assessment": "No Issues Found",
        "generated_at": "2026-03-25T12:00:00Z",
        "summary_narrative": "No issues.",
        "business_impact": "",
        "issues": [],
        "coverage_verified": True,
        "coverage_warning": None,
    }


class TestGetExecutiveSummary:
    def test_returns_404_for_missing_document(self):
        mock_vault = _make_mock_vault(doc_exists=False)
        with patch("api.vault", mock_vault):
            with TestClient(app) as c:
                response = c.get("/api/v1/reports/executive-summary/doc_missing")
        assert response.status_code == 404

    def test_returns_cached_false_when_no_cache(self):
        mock_vault = _make_mock_vault(cached_report=None)
        with patch("api.vault", mock_vault):
            with TestClient(app) as c:
                response = c.get("/api/v1/reports/executive-summary/doc_abc")
        assert response.status_code == 200
        assert response.json()["cached"] is False

    def test_returns_cached_true_with_report_when_cached(self):
        mock_vault = _make_mock_vault(cached_report=_minimal_report())
        with patch("api.vault", mock_vault):
            with TestClient(app) as c:
                response = c.get("/api/v1/reports/executive-summary/doc_abc")
        data = response.json()
        assert data["cached"] is True
        assert data["report"]["overall_assessment"] == "No Issues Found"


class TestPostExecutiveSummary:
    def _run_post_stream(self, mock_vault):
        """Fires the POST and collects all SSE event lines."""
        mock_storyteller = MagicMock()
        mock_storyteller.run.return_value = _minimal_report()
        mock_storyteller.model = "gpt-4o"

        mock_critic = MagicMock()
        mock_critic.run.return_value = _minimal_report()

        mock_kde = MagicMock()
        mock_kde.check.return_value = _minimal_report()

        with patch("api.vault", mock_vault), \
             patch("api.StorytellerAgent", return_value=mock_storyteller), \
             patch("api.CriticAgent", return_value=mock_critic), \
             patch("api.KDECoverageCheck", return_value=mock_kde), \
             patch("api._active_generations", set()):
            with TestClient(app) as c:
                with c.stream("POST", "/api/v1/reports/executive-summary/doc_abc") as r:
                    lines = [line for line in r.iter_lines() if line.startswith("data:")]
        return lines

    def test_returns_404_for_missing_document(self):
        mock_vault = _make_mock_vault(doc_exists=False)
        with patch("api.vault", mock_vault):
            with TestClient(app) as c:
                response = c.post("/api/v1/reports/executive-summary/doc_missing")
        assert response.status_code == 404

    def test_returns_409_when_already_generating(self):
        mock_vault = _make_mock_vault()
        with patch("api.vault", mock_vault), \
             patch("api._active_generations", {"doc_abc"}):
            with TestClient(app) as c:
                response = c.post("/api/v1/reports/executive-summary/doc_abc")
        assert response.status_code == 409

    def test_streams_four_progress_events(self):
        lines = self._run_post_stream(_make_mock_vault())
        stages = [json.loads(l[5:])["stage"] for l in lines]
        assert "analysing" in stages
        assert "drafting" in stages
        assert "auditing" in stages
        assert "verifying" in stages

    def test_streams_complete_event_with_report(self):
        lines = self._run_post_stream(_make_mock_vault())
        complete_lines = [l for l in lines if '"complete"' in l]
        assert len(complete_lines) == 1
        data = json.loads(complete_lines[0][5:])
        assert "report" in data
        assert data["report"]["overall_assessment"] == "No Issues Found"

    def test_writes_to_cache_on_complete(self):
        mock_vault = _make_mock_vault()
        self._run_post_stream(mock_vault)
        mock_vault.save_executive_summary.assert_called_once()


class TestDeleteExecutiveSummary:
    def test_returns_404_for_missing_document(self):
        mock_vault = _make_mock_vault(doc_exists=False)
        with patch("api.vault", mock_vault):
            with TestClient(app) as c:
                response = c.delete("/api/v1/reports/executive-summary/doc_missing")
        assert response.status_code == 404

    def test_returns_204_when_cache_exists(self):
        mock_vault = _make_mock_vault()
        with patch("api.vault", mock_vault):
            with TestClient(app) as c:
                response = c.delete("/api/v1/reports/executive-summary/doc_abc")
        assert response.status_code == 204

    def test_returns_204_when_no_cache_row_idempotent(self):
        mock_vault = _make_mock_vault(cached_report=None)
        with patch("api.vault", mock_vault):
            with TestClient(app) as c:
                response = c.delete("/api/v1/reports/executive-summary/doc_abc")
        assert response.status_code == 204

    def test_calls_delete_executive_summary(self):
        mock_vault = _make_mock_vault()
        with patch("api.vault", mock_vault):
            with TestClient(app) as c:
                c.delete("/api/v1/reports/executive-summary/doc_abc")
        mock_vault.delete_executive_summary.assert_called_once_with("doc_abc")
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
pytest tests/test_api_executive.py -v
```

Expected: All FAIL — endpoints don't exist yet

---

- [ ] **Step 3: Add imports and `_active_generations` to `api.py`**

At the top of `api.py`, add to the existing imports:

```python
import asyncio
import json as _json
from fastapi.responses import StreamingResponse
from core.agents import StorytellerAgent, CriticAgent, KDECoverageCheck
```

After the `DOCUMENT_STORE` declaration, add:

```python
# --- In-flight generation tracker ---
# Prevents concurrent generation for the same document.
# Safe as a plain set — FastAPI's async loop is single-threaded.
_active_generations: set = set()
```

---

- [ ] **Step 4: Add `_gather_raw_issues` helper to `api.py`**

Add this private function before the first `@app` route:

```python
def _gather_raw_issues(document_id: str) -> dict:
    """Collates all raw issue data from the vault for the Storyteller prompt."""
    return {
        "friction_lines": vault.get_friction_lines(document_id),
        "chronological_friction_lines": vault.get_chronological_friction_lines(document_id),
        "hub_vulnerabilities": vault.get_hub_vulnerabilities(document_id),
        "risk_matrix": vault.get_risk_matrix_data(document_id),
    }
```

---

- [ ] **Step 5: Add the three endpoints to `api.py`**

Add these endpoints after `get_risk_matrix` and before `get_canvas_data`:

```python
@app.get("/api/v1/reports/executive-summary/{document_id}")
async def get_executive_summary(document_id: str):
    """
    Returns the cached plain-English executive report for a document.
    Returns {"cached": false} if the document exists but report has not been generated yet.
    """
    cursor = vault.conn.cursor()
    cursor.execute("SELECT id FROM documents WHERE id = ?", (document_id,))
    if cursor.fetchone() is None:
        raise HTTPException(status_code=404, detail="Document not found.")

    cached = vault.get_executive_summary(document_id)
    if cached is None:
        return {"cached": False}
    return {"cached": True, "report": cached}


@app.post("/api/v1/reports/executive-summary/{document_id}")
async def generate_executive_summary(document_id: str):
    """
    Triggers multi-agent plain-English report generation and streams progress via SSE.
    Caches the completed report in SQLite. Returns 409 if already generating.
    """
    cursor = vault.conn.cursor()
    cursor.execute("SELECT id FROM documents WHERE id = ?", (document_id,))
    if cursor.fetchone() is None:
        raise HTTPException(status_code=404, detail="Document not found.")

    if document_id in _active_generations:
        raise HTTPException(status_code=409, detail="Report generation already in progress for this document.")

    async def _stream():
        _active_generations.add(document_id)
        try:
            yield f"data: {_json.dumps({'stage': 'analysing', 'message': 'Analysing issues...'})}\n\n"
            raw_issues = await asyncio.to_thread(_gather_raw_issues, document_id)

            yield f"data: {_json.dumps({'stage': 'drafting', 'message': 'Drafting plain-English narrative...'})}\n\n"
            storyteller = StorytellerAgent()
            draft = await asyncio.to_thread(storyteller.run, raw_issues)

            yield f"data: {_json.dumps({'stage': 'auditing', 'message': 'Auditing for omissions...'})}\n\n"
            critic = CriticAgent()
            audited = await asyncio.to_thread(critic.run, draft, raw_issues, storyteller)

            yield f"data: {_json.dumps({'stage': 'verifying', 'message': 'Verifying coverage...'})}\n\n"
            kde = KDECoverageCheck(vault)
            final = await asyncio.to_thread(kde.check, document_id, audited)

            vault.save_executive_summary(document_id, final, storyteller.model)
            yield f"data: {_json.dumps({'stage': 'complete', 'report': final})}\n\n"
        finally:
            _active_generations.discard(document_id)

    return StreamingResponse(_stream(), media_type="text/event-stream")


@app.delete("/api/v1/reports/executive-summary/{document_id}", status_code=204)
async def delete_executive_summary(document_id: str):
    """
    Clears the cached executive report for a document (called by the Regenerate button).
    Returns 204 even if no cached row exists — idempotent.
    Returns 404 only if the document_id does not exist at all.
    """
    cursor = vault.conn.cursor()
    cursor.execute("SELECT id FROM documents WHERE id = ?", (document_id,))
    if cursor.fetchone() is None:
        raise HTTPException(status_code=404, detail="Document not found.")

    vault.delete_executive_summary(document_id)
```

---

- [ ] **Step 6: Run tests to verify they pass**

```bash
pytest tests/test_api_executive.py -v
```

Expected: All 12 tests PASS

---

- [ ] **Step 7: Run full test suite**

```bash
pytest tests/ -v
```

Expected: All tests PASS

---

- [ ] **Step 8: Commit**

```bash
git add api.py tests/test_api_executive.py
git commit -m "feat(api): add executive summary GET/POST/DELETE endpoints with SSE streaming"
```

---

## Task 4: UI layer — toolbar button, report page, export

**Files:**
- Modify: `static/index.html`

There are no automated tests for the frontend. After each sub-step, verify manually by running `python run.py` and loading `http://localhost:8000`.

---

- [ ] **Step 1: Add CSS for the report page**

In `static/index.html`, inside the `<style>` block, add the following before `</style>`:

```css
        /* ── Plain English Report Page ── */
        #report-page {
            display: none;
            position: absolute; inset: 44px 0 0 0;
            background: #0d1117; overflow-y: auto; z-index: 15;
        }
        #report-page.open { display: block; }

        .rp-body {
            max-width: 860px; margin: 0 auto; padding: 32px 24px 80px;
        }
        .rp-header-bar {
            display: flex; align-items: center; gap: 10px;
            margin-bottom: 28px; flex-wrap: wrap;
        }
        .rp-title-block { flex: 1; min-width: 200px; }
        .rp-eyebrow { font-size: 11px; text-transform: uppercase; letter-spacing: .1em; color: #8b949e; margin-bottom: 4px; }
        .rp-title { font-size: 20px; font-weight: 700; color: #e6edf3; }
        .rp-meta { font-size: 12px; color: #8b949e; margin-top: 2px; }
        .rp-actions { display: flex; gap: 8px; flex-shrink: 0; }
        .rp-btn {
            background: transparent; border: 1px solid #30363d; color: #8b949e;
            padding: 6px 14px; border-radius: 6px; cursor: pointer; font-size: 12px;
            transition: border-color .2s, color .2s;
        }
        .rp-btn:hover { border-color: #8b949e; color: #c9d1d9; }
        .rp-btn.danger:hover { border-color: #ff7b72; color: #ff7b72; }

        /* Health banner */
        .rp-health {
            border-radius: 10px; padding: 18px 20px; margin-bottom: 24px;
            display: flex; gap: 14px; align-items: flex-start;
            border: 1px solid #30363d; background: #161b22;
        }
        .rp-health.critical { border-color: #ff7b72; }
        .rp-health.high     { border-color: #d29922; }
        .rp-health.moderate { border-color: #d29922; }
        .rp-health.low      { border-color: #3fb950; }
        .rp-health.none     { border-color: #3fb950; }
        .rp-health-icon { font-size: 22px; flex-shrink: 0; margin-top: 1px; }
        .rp-health-label {
            font-size: 10px; text-transform: uppercase; letter-spacing: .1em;
            font-weight: 700; margin-bottom: 4px; color: #8b949e;
        }
        .rp-health.critical .rp-health-label { color: #ff7b72; }
        .rp-health.high .rp-health-label,
        .rp-health.moderate .rp-health-label { color: #d29922; }
        .rp-health.low .rp-health-label,
        .rp-health.none .rp-health-label { color: #3fb950; }
        .rp-health-text { font-size: 14px; color: #e6edf3; line-height: 1.6; }

        /* What This Means For You */
        .rp-means {
            background: #161b22; border: 1px solid #30363d; border-radius: 10px;
            padding: 18px 20px; margin-bottom: 28px;
        }
        .rp-means-label {
            font-size: 10px; text-transform: uppercase; letter-spacing: .1em;
            color: #8b949e; font-weight: 700; margin-bottom: 8px;
        }
        .rp-means-text { font-size: 14px; color: #c9d1d9; line-height: 1.7; }

        /* Section heading */
        .rp-section-heading {
            font-size: 11px; text-transform: uppercase; letter-spacing: .1em;
            color: #8b949e; font-weight: 700; margin-bottom: 14px;
            padding-bottom: 8px; border-bottom: 1px solid #21262d;
        }

        /* Issue cards */
        .rp-issue {
            border: 1px solid #30363d; border-left: 4px solid #ff7b72;
            background: #161b22; border-radius: 0 8px 8px 0;
            padding: 16px 18px; margin-bottom: 12px;
        }
        .rp-issue.high   { border-left-color: #d29922; }
        .rp-issue.medium { border-left-color: #388bfd; }
        .rp-issue.low    { border-left-color: #8b949e; }
        .rp-issue-meta { display: flex; align-items: center; gap: 8px; margin-bottom: 6px; }
        .rp-pill {
            font-size: 10px; font-weight: 700; text-transform: uppercase;
            padding: 2px 8px; border-radius: 20px;
            background: #ff7b7222; color: #ff7b72;
        }
        .rp-issue.high   .rp-pill { background: #d2992222; color: #d29922; }
        .rp-issue.medium .rp-pill { background: #388bfd22; color: #388bfd; }
        .rp-issue.low    .rp-pill { background: #8b949e22; color: #8b949e; }
        .rp-issue-title { font-size: 15px; font-weight: 600; color: #e6edf3; margin-bottom: 6px; line-height: 1.4; }
        .rp-issue-desc { font-size: 13px; color: #8b949e; line-height: 1.6; margin-bottom: 12px; }
        .rp-solution {
            display: flex; align-items: flex-start; gap: 8px;
            background: #0d1117; border: 1px solid #21262d;
            border-radius: 6px; padding: 10px 12px;
        }
        .rp-solution-label {
            font-size: 10px; font-weight: 700; text-transform: uppercase;
            letter-spacing: .08em; color: #3fb950; margin-bottom: 2px;
        }
        .rp-solution-text { font-size: 12px; color: #c9d1d9; line-height: 1.5; }

        /* Further issues accordion */
        .rp-accordion-toggle {
            width: 100%; background: #161b22; border: 1px solid #30363d;
            border-radius: 8px; padding: 12px 16px;
            display: flex; align-items: center; justify-content: space-between;
            cursor: pointer; margin-top: 8px; transition: background .15s;
            color: inherit; font-size: 13px; font-weight: 600;
        }
        .rp-accordion-toggle:hover { background: #1c2128; }
        .rp-accordion-count {
            font-size: 11px; background: #21262d; color: #8b949e;
            padding: 2px 8px; border-radius: 20px; margin-left: 8px;
        }
        .rp-accordion-body {
            border: 1px solid #30363d; border-top: none;
            border-radius: 0 0 8px 8px; background: #161b22;
            padding: 12px 16px; display: none;
        }
        .rp-accordion-body.open { display: block; }
        .rp-minor {
            display: flex; align-items: flex-start; gap: 10px;
            padding: 8px 0; border-bottom: 1px solid #21262d;
            font-size: 12px; color: #8b949e; line-height: 1.5;
        }
        .rp-minor:last-child { border-bottom: none; }
        .rp-minor-dot {
            width: 6px; height: 6px; border-radius: 50%;
            background: #388bfd; margin-top: 4px; flex-shrink: 0;
        }

        /* Coverage warning */
        .rp-coverage-warning {
            background: #2d2000; border: 1px solid #d29922; border-radius: 8px;
            padding: 14px 16px; margin-top: 16px;
            font-size: 13px; color: #d29922; line-height: 1.6;
        }

        /* Print styles */
        @media print {
            #toolbar, #report-page .rp-actions { display: none !important; }
            #report-page { position: static !important; overflow: visible !important; }
            .rp-body { max-width: 100%; padding: 0; }
            body { background: #fff !important; color: #000 !important; }
            .rp-health, .rp-means, .rp-issue, .rp-solution { border-color: #ccc !important; background: #f9f9f9 !important; }
            .rp-title, .rp-health-text, .rp-means-text, .rp-issue-title { color: #000 !important; }
            .rp-issue-desc, .rp-solution-text { color: #333 !important; }
        }
```

---

- [ ] **Step 2: Add the `📋 Plain English` toolbar button**

In `static/index.html`, find the existing `#report-btn` line in the toolbar:

```html
        <button class="toolbar-btn" id="report-btn" onclick="toggleDashboard()">&#128202; Report</button>
```

Add the new button immediately after it:

```html
        <button class="toolbar-btn" id="plain-english-btn" style="display:none" onclick="openPlainEnglishReport()">&#128203; Plain English</button>
```

---

- [ ] **Step 3: Add the `#report-page` HTML structure**

In `static/index.html`, find `<div id="reporting-dashboard">`. Add the following immediately before it:

```html
    <!-- Plain English Report Page -->
    <div id="report-page">
      <div class="rp-body">
        <div class="rp-header-bar">
          <div class="rp-title-block">
            <div class="rp-eyebrow">Executive Intelligence Report</div>
            <div class="rp-title" id="rp-doc-name"></div>
            <div class="rp-meta" id="rp-meta"></div>
          </div>
          <div class="rp-actions">
            <button class="rp-btn danger" onclick="regenerateReport()">&#128260; Regenerate</button>
            <button class="rp-btn" onclick="downloadReportPDF()">&#128196; Download PDF</button>
            <button class="rp-btn" id="rp-copy-btn" onclick="copyReportToClipboard()">&#128203; Copy</button>
            <button class="rp-btn" onclick="closeReportPage()">&#10005; Close</button>
          </div>
        </div>
        <div id="rp-content"></div>
      </div>
    </div>
```

---

- [ ] **Step 4: Add the JavaScript functions**

In `static/index.html`, inside the `<script>` block, add these functions after the `loadReportingDashboard` function:

```javascript
        // ── 10. Plain English Executive Report ──
        let _currentReportDocumentId = null;
        let _currentReport = null;

        async function openPlainEnglishReport() {
            const documentId = activeDocumentId; // module-level var set by loadCanvasData
            if (!documentId) return;
            _currentReportDocumentId = documentId;

            // Check cache first
            try {
                const res = await fetch(`/api/v1/reports/executive-summary/${documentId}`);
                const data = await res.json();
                if (data.cached) {
                    _currentReport = data.report;
                    renderReportPage(data.report);
                    return;
                }
            } catch (e) {
                console.error('Failed to check report cache:', e);
            }

            // Not cached — stream generation
            showLoadingOverlay('Generating plain-English report...');
            try {
                const evtSource = new EventSource(`/api/v1/reports/executive-summary/${documentId}`, {method: 'POST'});
                // EventSource doesn't support POST — use fetch with ReadableStream instead
                evtSource.close();

                const response = await fetch(`/api/v1/reports/executive-summary/${documentId}`, { method: 'POST' });
                const reader = response.body.getReader();
                const decoder = new TextDecoder();
                let buffer = '';

                while (true) {
                    const { done, value } = await reader.read();
                    if (done) break;
                    buffer += decoder.decode(value, { stream: true });
                    const lines = buffer.split('\n');
                    buffer = lines.pop();
                    for (const line of lines) {
                        if (!line.startsWith('data:')) continue;
                        const event = JSON.parse(line.slice(5).trim());
                        if (event.stage === 'complete') {
                            _currentReport = event.report;
                            hideLoadingOverlay();
                            renderReportPage(event.report);
                        } else {
                            updateLoadingMessage(event.message);
                        }
                    }
                }
            } catch (e) {
                hideLoadingOverlay();
                console.error('Report generation failed:', e);
                showToast('Report generation failed. Please try again.');
            }
        }

        function renderReportPage(report) {
            document.getElementById('graph-container').style.display = 'none';
            document.getElementById('report-page').classList.add('open');

            document.getElementById('rp-doc-name').textContent = activeDocumentName || 'Document';
            const genAt = report.generated_at ? new Date(report.generated_at).toLocaleString('en-GB') : '';
            document.getElementById('rp-meta').textContent = `Generated ${genAt} · ${report.issues ? report.issues.length : 0} issues`;

            const content = document.getElementById('rp-content');
            content.innerHTML = '';

            // Health banner
            const assessment = (report.overall_assessment || '').toLowerCase().replace(/\s+/g, '-');
            const healthIcon = assessment.includes('critical') ? '🚨' : assessment.includes('high') ? '⚠️' : assessment.includes('moderate') ? '⚠️' : '✅';
            const healthEl = document.createElement('div');
            healthEl.className = `rp-health ${assessment.split('-')[0]}`;
            healthEl.innerHTML = `
                <div class="rp-health-icon">${healthIcon}</div>
                <div>
                    <div class="rp-health-label">Overall Assessment: ${escHtml(report.overall_assessment || '')}</div>
                    <div class="rp-health-text">${escHtml(report.summary_narrative || '')}</div>
                </div>`;
            content.appendChild(healthEl);

            // What This Means For You
            if (report.business_impact) {
                const meansEl = document.createElement('div');
                meansEl.className = 'rp-means';
                meansEl.innerHTML = `<div class="rp-means-label">What This Means For You</div>
                    <div class="rp-means-text">${escHtml(report.business_impact)}</div>`;
                content.appendChild(meansEl);
            }

            const issues = report.issues || [];
            const critical = issues.filter(i => i.severity === 'critical' || i.severity === 'high');
            const minor    = issues.filter(i => i.severity === 'medium'   || i.severity === 'low');

            // Critical/High issue cards
            if (critical.length > 0) {
                const heading = document.createElement('div');
                heading.className = 'rp-section-heading';
                heading.textContent = `Critical Issues · Action Required`;
                content.appendChild(heading);

                critical.forEach((issue, idx) => {
                    const card = document.createElement('div');
                    card.className = `rp-issue ${issue.severity}`;
                    card.innerHTML = `
                        <div class="rp-issue-meta">
                            <span class="rp-pill">${escHtml(issue.severity)}</span>
                            <span style="font-size:11px;color:#8b949e">Issue ${idx + 1} of ${issues.length}</span>
                        </div>
                        <div class="rp-issue-title">${escHtml(issue.title)}</div>
                        <div class="rp-issue-desc">${escHtml(issue.plain_english)}</div>
                        <div class="rp-solution">
                            <span style="font-size:13px;flex-shrink:0;margin-top:1px">✅</span>
                            <div>
                                <div class="rp-solution-label">Suggested Fix</div>
                                <div class="rp-solution-text">${escHtml(issue.solution)}</div>
                            </div>
                        </div>`;
                    content.appendChild(card);
                });
            }

            // Further issues accordion
            if (minor.length > 0) {
                const toggle = document.createElement('button');
                toggle.className = 'rp-accordion-toggle';
                toggle.innerHTML = `<span>▾ Further Issues <span class="rp-accordion-count">${minor.length} lower-priority conflict${minor.length > 1 ? 's' : ''}</span></span>
                    <span style="font-size:11px;color:#8b949e">These do not require immediate action</span>`;
                const body = document.createElement('div');
                body.className = 'rp-accordion-body';
                minor.forEach(issue => {
                    const row = document.createElement('div');
                    row.className = 'rp-minor';
                    row.innerHTML = `<div class="rp-minor-dot"></div><div><strong style="color:#c9d1d9">${escHtml(issue.title)}</strong><br>${escHtml(issue.plain_english)}</div>`;
                    body.appendChild(row);
                });
                toggle.addEventListener('click', () => {
                    body.classList.toggle('open');
                    const arrow = toggle.querySelector('span > span').previousSibling;
                    toggle.querySelector('span').childNodes[0].textContent = body.classList.contains('open') ? '▴ Further Issues ' : '▾ Further Issues ';
                });
                content.appendChild(toggle);
                content.appendChild(body);
            }

            // Coverage warning
            if (report.coverage_warning) {
                const warn = document.createElement('div');
                warn.className = 'rp-coverage-warning';
                warn.textContent = report.coverage_warning;
                content.appendChild(warn);
            }
        }

        function closeReportPage() {
            document.getElementById('report-page').classList.remove('open');
            document.getElementById('graph-container').style.display = '';
        }

        async function regenerateReport() {
            const documentId = _currentReportDocumentId;
            if (!documentId) return;
            closeReportPage();
            await fetch(`/api/v1/reports/executive-summary/${documentId}`, { method: 'DELETE' });
            await openPlainEnglishReport();
        }

        function downloadReportPDF() {
            window.print();
        }

        async function copyReportToClipboard() {
            if (!_currentReport) return;
            const report = _currentReport;
            let text = `EXECUTIVE INTELLIGENCE REPORT\n`;
            text += `${'='.repeat(40)}\n\n`;
            text += `Overall Assessment: ${report.overall_assessment}\n\n`;
            text += `${report.summary_narrative}\n\n`;
            if (report.business_impact) text += `WHAT THIS MEANS FOR YOU\n${report.business_impact}\n\n`;
            (report.issues || []).forEach((issue, i) => {
                text += `ISSUE ${i + 1}: ${issue.title.toUpperCase()}\n`;
                text += `Severity: ${issue.severity}\n`;
                text += `${issue.plain_english}\n`;
                text += `Suggested Fix: ${issue.solution}\n\n`;
            });
            if (report.coverage_warning) text += `\nNote: ${report.coverage_warning}\n`;
            try {
                await navigator.clipboard.writeText(text);
                const btn = document.getElementById('rp-copy-btn');
                btn.textContent = '✓ Copied';
                setTimeout(() => { btn.textContent = '📋 Copy'; }, 2000);
            } catch (e) {
                showToast('Copy failed — please select and copy manually.');
            }
        }
```

---

- [ ] **Step 5: Add `activeDocumentName` and show the `📋 Plain English` button when a document loads**

In `static/index.html`, find the existing `let activeDocumentId` declaration (near the top of the `<script>` block) and add the name variable on the next line:

```javascript
        let activeDocumentName = null;
```

Find where `activeDocumentId` is assigned inside `loadCanvasData` (it will look like `activeDocumentId = documentId;`) and add the name assignment on the next line:

```javascript
                activeDocumentName = documentName; // documentName is a parameter of loadCanvasData
```

Then find the line that shows the `report-btn`:

```javascript
                document.getElementById('report-btn').style.display = 'inline-block';
```

Add the plain-english button reveal immediately after it:

```javascript
                document.getElementById('plain-english-btn').style.display = 'inline-block';
```

---

- [ ] **Step 6: Manual smoke test**

Run: `python run.py`

Open `http://localhost:8000` and verify:

1. Upload a PDF — ingestion completes, canvas renders
2. A `📋 Plain English` button appears in the toolbar alongside `📊 Report`
3. Clicking `📋 Plain English` shows a loading overlay with streaming progress messages
4. After generation, the full-page report renders (canvas hidden)
5. The health banner, "What This Means For You" box, and issue cards all display
6. Clicking an issue card's node IDs in future is preserved via `source_nodes`
7. The "Further Issues" accordion expands/collapses correctly
8. `📄 Download PDF` triggers the browser print dialog; report renders cleanly
9. `📋 Copy` copies plain-text report to clipboard; button briefly shows "✓ Copied"
10. `✕ Close` returns to the 3D canvas
11. `🔄 Regenerate` clears cache and triggers fresh generation
12. Clicking `📋 Plain English` a second time loads instantly from cache (no loading screen)
13. Load a previously ingested document from the Documents list — `📋 Plain English` button appears and cached report loads instantly

---

- [ ] **Step 7: Commit**

```bash
git add static/index.html
git commit -m "feat(ui): add Plain English report page with streaming generation and PDF/clipboard export"
```

---

## Run the Full Test Suite

- [ ] **Final check**

```bash
pytest tests/ -v
```

Expected: All tests PASS across all test files.

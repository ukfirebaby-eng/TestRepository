import pytest
import json
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
    mock_vault.get_narrative_report.return_value = cached_report
    mock_vault.get_friction_lines.return_value = []
    mock_vault.get_chronological_friction_lines.return_value = []
    mock_vault.get_hub_vulnerabilities.return_value = []
    mock_vault.get_risk_matrix_data.return_value = []
    mock_vault.save_narrative_report.return_value = None
    mock_vault.delete_narrative_report.return_value = None
    return mock_vault


def _make_raw_issues_empty():
    return {
        "friction_lines": [],
        "chronological_friction_lines": [],
        "hub_vulnerabilities": [],
        "risk_matrix": [],
    }


def _make_raw_issues_with_data():
    return {
        "friction_lines": [{"severity": 4, "diamond": "conflict A"}],
        "chronological_friction_lines": [{"severity": 3, "diamond": "schedule clash"}],
        "hub_vulnerabilities": [{"severity": 5, "insight": "hub risk"}],
        "risk_matrix": [],
    }


def _sse_events(response_text: str) -> list:
    """Parse SSE text/event-stream into a list of decoded dicts."""
    events = []
    for line in response_text.splitlines():
        if line.startswith("data: "):
            events.append(json.loads(line[len("data: "):]))
    return events


class TestGetNarrativeReport:
    def test_get_returns_404_for_unknown_document(self):
        mock_vault = _make_mock_vault(doc_exists=False)
        with patch("api.vault", mock_vault):
            with TestClient(app) as c:
                response = c.get("/api/v1/reports/narrative/doc_missing")
        assert response.status_code == 404

    def test_get_returns_cached_false_when_absent(self):
        mock_vault = _make_mock_vault(doc_exists=True, cached_report=None)
        with patch("api.vault", mock_vault):
            with TestClient(app) as c:
                response = c.get("/api/v1/reports/narrative/doc_abc")
        assert response.status_code == 200
        assert response.json() == {"cached": False}

    def test_get_returns_cached_report_when_present(self):
        sample_report = {"overall_assessment": "High Risk", "chapters": []}
        mock_vault = _make_mock_vault(doc_exists=True, cached_report=sample_report)
        with patch("api.vault", mock_vault):
            with TestClient(app) as c:
                response = c.get("/api/v1/reports/narrative/doc_abc")
        assert response.status_code == 200
        data = response.json()
        assert data["cached"] is True
        assert data["report"] == sample_report


class TestPostNarrativeReport:
    def test_post_streams_correct_sse_stages(self):
        """Outline returns 2 chapters → drafting stages appear, then auditing/verifying/complete."""
        mock_vault = _make_mock_vault(doc_exists=True)
        raw_issues = _make_raw_issues_with_data()

        outline = [
            {"title": "Chapter One", "indices": [0]},
            {"title": "Chapter Two", "indices": [1]},
        ]
        draft_result_1 = {"title": "Chapter One", "narrative": "prose one", "indices": [0]}
        draft_result_2 = {"title": "Chapter Two", "narrative": "prose two", "indices": [1]}
        audited = {"overall_assessment": "High Risk", "chapters": [], "issues": [], "coverage_verified": False, "coverage_warning": None, "generated_at": "x", "executive_summary": ""}
        final = {**audited, "coverage_verified": True}

        mock_outline_agent = MagicMock()
        mock_outline_agent.run.return_value = outline

        mock_drafter = MagicMock()
        mock_drafter.run.side_effect = [draft_result_1, draft_result_2]
        mock_drafter.model = "gpt-4o"

        mock_critic = MagicMock()
        mock_critic.run.return_value = audited

        mock_kde = MagicMock()
        mock_kde.check.return_value = final

        with patch("api.vault", mock_vault), \
             patch("api._gather_raw_issues", return_value=raw_issues), \
             patch("api.OutlineAgent", return_value=mock_outline_agent), \
             patch("api.RecursiveDraftingAgent", return_value=mock_drafter), \
             patch("api.CriticAgent", return_value=mock_critic), \
             patch("api.KDECoverageCheck", return_value=mock_kde), \
             patch("api._active_narratives", set()):
            with TestClient(app) as c:
                response = c.post("/api/v1/reports/narrative/doc_abc")

        assert response.status_code == 200
        events = _sse_events(response.text)
        stages = [e["stage"] for e in events]
        assert stages[0] == "analysing"
        assert stages[1] == "outlining"
        assert "drafting_1_of_2" in stages
        assert "drafting_2_of_2" in stages
        assert "auditing" in stages
        assert "verifying" in stages
        assert stages[-1] == "complete"
        complete_event = events[-1]
        assert complete_event["report"] == final

    def test_post_returns_409_if_already_generating(self):
        mock_vault = _make_mock_vault(doc_exists=True)
        active = {"doc_abc"}
        with patch("api.vault", mock_vault), \
             patch("api._active_narratives", active):
            with TestClient(app) as c:
                response = c.post("/api/v1/reports/narrative/doc_abc")
        assert response.status_code == 409

    def test_post_fallback_when_outline_single_group(self):
        """When outline returns <= 1 item, StorytellerAgent is used instead of RecursiveDraftingAgent."""
        mock_vault = _make_mock_vault(doc_exists=True)
        raw_issues = _make_raw_issues_empty()
        outline = [{"title": "Everything", "indices": []}]
        storyteller_draft = {"overall_assessment": "No Issues Found", "chapters": [], "issues": [],
                             "coverage_verified": False, "coverage_warning": None,
                             "generated_at": "x", "executive_summary": ""}
        audited = {**storyteller_draft}
        final = {**storyteller_draft, "coverage_verified": True}

        mock_outline_agent = MagicMock()
        mock_outline_agent.run.return_value = outline

        mock_storyteller = MagicMock()
        mock_storyteller.run.return_value = storyteller_draft
        mock_storyteller.model = "gpt-4o"

        mock_critic = MagicMock()
        mock_critic.run.return_value = audited

        mock_kde = MagicMock()
        mock_kde.check.return_value = final

        with patch("api.vault", mock_vault), \
             patch("api._gather_raw_issues", return_value=raw_issues), \
             patch("api.OutlineAgent", return_value=mock_outline_agent), \
             patch("api.StorytellerAgent", return_value=mock_storyteller), \
             patch("api.CriticAgent", return_value=mock_critic), \
             patch("api.KDECoverageCheck", return_value=mock_kde), \
             patch("api._active_narratives", set()):
            with TestClient(app) as c:
                response = c.post("/api/v1/reports/narrative/doc_abc")

        assert response.status_code == 200
        events = _sse_events(response.text)
        stages = [e["stage"] for e in events]
        assert "outlining" in stages
        # No drafting_N_of_N stages when using storyteller fallback
        assert not any(s.startswith("drafting_") for s in stages)
        assert stages[-1] == "complete"
        mock_storyteller.run.assert_called_once_with(raw_issues)

    def test_post_returns_404_for_unknown_document(self):
        mock_vault = _make_mock_vault(doc_exists=False)
        with patch("api.vault", mock_vault):
            with TestClient(app) as c:
                response = c.post("/api/v1/reports/narrative/doc_missing")
        assert response.status_code == 404


class TestDeleteNarrativeReport:
    def test_delete_returns_204(self):
        mock_vault = _make_mock_vault(doc_exists=True)
        with patch("api.vault", mock_vault):
            with TestClient(app) as c:
                response = c.delete("/api/v1/reports/narrative/doc_abc")
        assert response.status_code == 204
        mock_vault.delete_narrative_report.assert_called_once_with("doc_abc")

    def test_delete_idempotent(self):
        """Second delete on a document with no cached row still returns 204."""
        mock_vault = _make_mock_vault(doc_exists=True)
        with patch("api.vault", mock_vault):
            with TestClient(app) as c:
                r1 = c.delete("/api/v1/reports/narrative/doc_abc")
                r2 = c.delete("/api/v1/reports/narrative/doc_abc")
        assert r1.status_code == 204
        assert r2.status_code == 204
        assert mock_vault.delete_narrative_report.call_count == 2

    def test_delete_returns_404_for_unknown_document(self):
        mock_vault = _make_mock_vault(doc_exists=False)
        with patch("api.vault", mock_vault):
            with TestClient(app) as c:
                response = c.delete("/api/v1/reports/narrative/doc_missing")
        assert response.status_code == 404

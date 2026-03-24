import pytest
from fastapi.testclient import TestClient
from unittest.mock import patch, MagicMock

from api import app


def _make_mock_vault(doc_exists=True, friction_lines=None, chron_lines=None, bottlenecks=None, schedule_collapse=None, risk_matrix=None):
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
    mock_vault.get_schedule_collapse_forecast.return_value = schedule_collapse if schedule_collapse is not None else []
    mock_vault.get_risk_matrix_data.return_value = risk_matrix if risk_matrix is not None else []
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


class TestScheduleCollapseEndpoint:
    def test_returns_200(self):
        mock_vault = _make_mock_vault()
        with patch("api.vault", mock_vault):
            with TestClient(app) as c:
                response = c.get("/api/v1/reports/schedule-collapse/doc_test_01")
        assert response.status_code == 200

    def test_response_has_schedule_collapse_key(self):
        mock_vault = _make_mock_vault()
        with patch("api.vault", mock_vault):
            with TestClient(app) as c:
                response = c.get("/api/v1/reports/schedule-collapse/doc_test_01")
        assert "schedule_collapse" in response.json()

    def test_items_have_expected_fields(self):
        item = {
            "predecessor_name": "Phase A",
            "successor_name": "Phase B",
            "pred_end_date": "2026-04-15",
            "succ_start_date": "2026-04-01",
            "days_at_risk": 14,
            "analysis": "Reschedule Phase B."
        }
        mock_vault = _make_mock_vault(schedule_collapse=[item])
        with patch("api.vault", mock_vault):
            with TestClient(app) as c:
                response = c.get("/api/v1/reports/schedule-collapse/doc_test_01")
        data = response.json()
        assert data["schedule_collapse"][0]["predecessor_name"] == "Phase A"
        assert data["schedule_collapse"][0]["days_at_risk"] == 14

    def test_returns_404_for_missing_document(self):
        mock_vault = _make_mock_vault(doc_exists=False)
        with patch("api.vault", mock_vault):
            with TestClient(app) as c:
                response = c.get("/api/v1/reports/schedule-collapse/nonexistent")
        assert response.status_code == 404

    def test_calls_vault_with_document_id(self):
        mock_vault = _make_mock_vault()
        with patch("api.vault", mock_vault):
            with TestClient(app) as c:
                c.get("/api/v1/reports/schedule-collapse/doc_test_01")
        mock_vault.get_schedule_collapse_forecast.assert_called_once_with("doc_test_01")


class TestRiskMatrixEndpoint:
    def test_returns_200(self):
        mock_vault = _make_mock_vault()
        with patch("api.vault", mock_vault):
            with TestClient(app) as c:
                response = c.get("/api/v1/reports/risk-matrix/doc_test_01")
        assert response.status_code == 200

    def test_response_has_risk_matrix_key(self):
        mock_vault = _make_mock_vault()
        with patch("api.vault", mock_vault):
            with TestClient(app) as c:
                response = c.get("/api/v1/reports/risk-matrix/doc_test_01")
        assert "risk_matrix" in response.json()

    def test_items_include_severity_and_probability(self):
        item = {
            "type": "structural",
            "source": "node_a",
            "target": "node_b",
            "analysis": "Fix the conflict.",
            "severity": 4,
            "probability": 3
        }
        mock_vault = _make_mock_vault(risk_matrix=[item])
        with patch("api.vault", mock_vault):
            with TestClient(app) as c:
                response = c.get("/api/v1/reports/risk-matrix/doc_test_01")
        data = response.json()
        assert data["risk_matrix"][0]["severity"] == 4
        assert data["risk_matrix"][0]["probability"] == 3

    def test_returns_404_for_missing_document(self):
        mock_vault = _make_mock_vault(doc_exists=False)
        with patch("api.vault", mock_vault):
            with TestClient(app) as c:
                response = c.get("/api/v1/reports/risk-matrix/nonexistent")
        assert response.status_code == 404

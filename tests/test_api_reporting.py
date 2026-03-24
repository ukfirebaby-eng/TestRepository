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

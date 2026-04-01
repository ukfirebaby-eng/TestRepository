import json
import pytest
from unittest.mock import patch, MagicMock
from fastapi.testclient import TestClient

from api import app


def _fake_blast_result():
    return {
        "svi": 0.42,
        "nodes": [
            {
                "id": "n1", "name": "Alpha", "svi_contribution": 0.42,
                "dependency_count": 2, "cascade_depth": 2, "blast_radius_count": 2,
                "in_degree": 0.0, "out_degree": 0.5, "betweenness": 0.5,
                "ripa": {"li": 0.8, "re": 0.33, "criticality": 0.5, "svi": 0.42},
            },
        ],
        "cascade_paths": [
            {
                "trigger_node": "n1", "affected_node": "n2",
                "path": ["n1", "n2"], "hops": [{"from": "n1", "to": "n2", "edge_type": "REQUIRES", "probability": 0.95}],
                "depth": 1, "cumulative_probability": 0.95,
            },
        ],
        "centrality_scores": {
            "n1": {"in_degree": 0.0, "out_degree": 0.5, "betweenness": 0.5},
        },
        "ripa_summary": {
            "total_systemic_risk": 0.42,
            "top_vulnerabilities": [
                {"node_id": "n1", "name": "Alpha", "li": 0.8, "re": 0.33, "criticality": 0.5, "svi": 0.42},
            ],
        },
    }


class TestApiBlastRadius:
    def test_cached_result_includes_new_fields(self):
        mock_vault = MagicMock()
        mock_vault.list_documents.return_value = []
        mock_vault.get_risk_simulation.return_value = {
            "blast_radius": _fake_blast_result(),
            "black_swan": {"scenarios": []},
            "monte_carlo": {"available": False},
        }
        cursor = MagicMock()
        mock_vault.conn.cursor.return_value = cursor
        cursor.fetchone.return_value = {"id": "doc1"}

        with patch("api.vault", mock_vault):
            client = TestClient(app)
            response = client.get("/api/v1/reports/risk-simulation/doc1")
        assert response.status_code == 200
        body = response.json()
        assert body["cached"] is True
        blast = body["result"]["blast_radius"]
        assert "centrality_scores" in blast
        assert "ripa_summary" in blast
        assert "cascade_paths" in blast

    def test_blast_radius_node_has_ripa(self):
        mock_vault = MagicMock()
        mock_vault.list_documents.return_value = []
        mock_vault.get_risk_simulation.return_value = {
            "blast_radius": _fake_blast_result(),
            "black_swan": {"scenarios": []},
            "monte_carlo": {"available": False},
        }
        cursor = MagicMock()
        mock_vault.conn.cursor.return_value = cursor
        cursor.fetchone.return_value = {"id": "doc1"}

        with patch("api.vault", mock_vault):
            client = TestClient(app)
            response = client.get("/api/v1/reports/risk-simulation/doc1")
        blast = response.json()["result"]["blast_radius"]
        node = blast["nodes"][0]
        assert "ripa" in node
        assert "li" in node["ripa"]
        assert "re" in node["ripa"]
        assert "criticality" in node["ripa"]
        assert "svi" in node["ripa"]

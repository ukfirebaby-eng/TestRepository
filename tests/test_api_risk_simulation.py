import pytest
import json
from fastapi.testclient import TestClient
from unittest.mock import patch, MagicMock

from api import app


def _make_mock_vault(doc_exists=True, cached_result=None):
    mock_vault = MagicMock()

    def fresh_cursor():
        cur = MagicMock()
        cur.fetchone.return_value = {"id": "doc_abc"} if doc_exists else None
        cur.fetchall.return_value = []
        return cur

    mock_vault.conn.cursor.side_effect = fresh_cursor
    mock_vault.get_risk_simulation.return_value = cached_result
    mock_vault.save_risk_simulation.return_value = None
    mock_vault.delete_risk_simulation.return_value = None
    return mock_vault


def _sse_events(response_text: str) -> list:
    """Parse SSE text/event-stream into a list of decoded dicts."""
    events = []
    for line in response_text.splitlines():
        if line.startswith("data: "):
            events.append(json.loads(line[len("data: "):]))
    return events


class TestGetRiskSimulation:
    def test_get_returns_cached_false_when_absent(self):
        mock_vault = _make_mock_vault(doc_exists=True, cached_result=None)
        with patch("api.vault", mock_vault):
            with TestClient(app) as c:
                response = c.get("/api/v1/reports/risk-simulation/doc_abc")
        assert response.status_code == 200
        assert response.json() == {"cached": False}

    def test_get_returns_cached_result_when_present(self):
        sample_result = {"blast_radius": {"nodes": []}, "black_swan": [], "monte_carlo": {}}
        mock_vault = _make_mock_vault(doc_exists=True, cached_result=sample_result)
        with patch("api.vault", mock_vault):
            with TestClient(app) as c:
                response = c.get("/api/v1/reports/risk-simulation/doc_abc")
        assert response.status_code == 200
        data = response.json()
        assert data["cached"] is True
        assert data["result"] == sample_result

    def test_get_returns_404_for_unknown_document(self):
        mock_vault = _make_mock_vault(doc_exists=False)
        with patch("api.vault", mock_vault):
            with TestClient(app) as c:
                response = c.get("/api/v1/reports/risk-simulation/doc_missing")
        assert response.status_code == 404


class TestPostRiskSimulation:
    def test_post_streams_correct_sse_stages(self):
        """blast_radius → black_swan → monte_carlo → complete stages all present."""
        mock_vault = _make_mock_vault(doc_exists=True)

        blast_result = {"nodes": ["A", "B"], "impact_score": 0.8}
        black_swan_result = [{"scenario": "vendor collapse", "probability": 0.05}]
        monte_carlo_result = {"p50": 120, "p90": 180, "trials": 5000}
        final_result = {
            "blast_radius": blast_result,
            "black_swan": black_swan_result,
            "monte_carlo": monte_carlo_result,
        }

        mock_blast_instance = MagicMock()
        mock_blast_instance.run.return_value = blast_result

        mock_black_swan_instance = MagicMock()
        mock_black_swan_instance.run.return_value = black_swan_result

        mock_monte_carlo_instance = MagicMock()
        mock_monte_carlo_instance.run.return_value = monte_carlo_result

        with patch("api.vault", mock_vault), \
             patch("api.BlastRadiusCalculator", return_value=mock_blast_instance), \
             patch("api.BlackSwanAgent", return_value=mock_black_swan_instance), \
             patch("api.MonteCarloForecaster", return_value=mock_monte_carlo_instance), \
             patch("api._active_simulations", set()):
            with TestClient(app) as c:
                response = c.post("/api/v1/reports/risk-simulation/doc_abc")

        assert response.status_code == 200
        events = _sse_events(response.text)
        stages = [e["stage"] for e in events]
        assert stages[0] == "blast_radius"
        assert stages[1] == "black_swan"
        assert stages[2] == "monte_carlo"
        assert stages[-1] == "complete"
        complete_event = events[-1]
        assert complete_event["result"] == final_result
        mock_vault.save_risk_simulation.assert_called_once_with("doc_abc", final_result)

    def test_post_returns_409_if_already_simulating(self):
        mock_vault = _make_mock_vault(doc_exists=True)
        active = {"doc_abc"}
        with patch("api.vault", mock_vault), \
             patch("api._active_simulations", active):
            with TestClient(app) as c:
                response = c.post("/api/v1/reports/risk-simulation/doc_abc")
        assert response.status_code == 409

    def test_post_returns_404_for_unknown_document(self):
        mock_vault = _make_mock_vault(doc_exists=False)
        with patch("api.vault", mock_vault):
            with TestClient(app) as c:
                response = c.post("/api/v1/reports/risk-simulation/doc_missing")
        assert response.status_code == 404


class TestDeleteRiskSimulation:
    def test_delete_returns_204(self):
        mock_vault = _make_mock_vault(doc_exists=True)
        with patch("api.vault", mock_vault):
            with TestClient(app) as c:
                response = c.delete("/api/v1/reports/risk-simulation/doc_abc")
        assert response.status_code == 204
        mock_vault.delete_risk_simulation.assert_called_once_with("doc_abc")

    def test_delete_idempotent(self):
        """Second delete on a document with no cached row still returns 204."""
        mock_vault = _make_mock_vault(doc_exists=True)
        with patch("api.vault", mock_vault):
            with TestClient(app) as c:
                r1 = c.delete("/api/v1/reports/risk-simulation/doc_abc")
                r2 = c.delete("/api/v1/reports/risk-simulation/doc_abc")
        assert r1.status_code == 204
        assert r2.status_code == 204
        assert mock_vault.delete_risk_simulation.call_count == 2

    def test_delete_returns_404_for_unknown_document(self):
        mock_vault = _make_mock_vault(doc_exists=False)
        with patch("api.vault", mock_vault):
            with TestClient(app) as c:
                response = c.delete("/api/v1/reports/risk-simulation/doc_missing")
        assert response.status_code == 404

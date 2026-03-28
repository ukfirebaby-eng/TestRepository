import json
import pytest
from fastapi.testclient import TestClient
from unittest.mock import patch, MagicMock

from api import app


def _make_vault(doc_exists=True, friction_row=None, chron_row=None, chunk_text="Source evidence here."):
    mock_vault = MagicMock()

    # Each call to vault.conn.cursor() returns a fresh cursor with its own fetchone value.
    # The endpoint makes 3 separate cursor() calls: doc check, friction_lines, chron_friction_lines.
    responses = [
        {"id": "doc_abc"} if doc_exists else None,
        friction_row,
        chron_row,
    ]
    call_index = {"i": 0}

    def fresh_cursor():
        idx = call_index["i"]
        call_index["i"] += 1
        cur = MagicMock()
        if idx < len(responses):
            cur.fetchone.return_value = responses[idx]
        return cur

    mock_vault.conn.cursor.side_effect = fresh_cursor
    mock_vault.get_chunk_provenance.return_value = {"text": chunk_text}
    return mock_vault


def _friction_row(diamond="A REQUIRES B but C BLOCKS B", provenance_ids=None):
    return {
        "diamond": diamond,
        "provenance_ids": json.dumps(provenance_ids or ["chunk_1"]),
    }


class TestGenerateMitigation:
    def test_404_when_document_missing(self):
        mock_vault = _make_vault(doc_exists=False)
        with patch("api.vault", mock_vault):
            with TestClient(app) as c:
                r = c.post(
                    "/api/v1/reports/mitigation/doc_missing",
                    params={"source_node_id": "A", "target_node_id": "B"},
                )
        assert r.status_code == 404
        assert "Document not found" in r.json()["detail"]

    def test_404_when_friction_item_missing(self):
        mock_vault = _make_vault(friction_row=None, chron_row=None)
        with patch("api.vault", mock_vault):
            with TestClient(app) as c:
                r = c.post(
                    "/api/v1/reports/mitigation/doc_abc",
                    params={"source_node_id": "X", "target_node_id": "Y"},
                )
        assert r.status_code == 404
        assert "Friction item not found" in r.json()["detail"]

    def test_422_when_query_params_missing(self):
        mock_vault = _make_vault()
        with patch("api.vault", mock_vault):
            with TestClient(app) as c:
                r = c.post("/api/v1/reports/mitigation/doc_abc")
        assert r.status_code == 422

    def test_streams_sse_with_analysis_from_structural_table(self):
        mock_vault = _make_vault(friction_row=_friction_row())
        mock_result = {
            "is_genuine": True,
            "confidence": 0.9,
            "analysis": "Decouple the dependency between A and B.",
            "severity": 4,
            "probability": 3,
        }
        with patch("api.vault", mock_vault):
            with patch("api.ContradictionHunterAgent.synthesize_mitigation", return_value=mock_result):
                with TestClient(app) as c:
                    r = c.post(
                        "/api/v1/reports/mitigation/doc_abc",
                        params={"source_node_id": "A", "target_node_id": "B"},
                    )
        assert r.status_code == 200
        assert "text/event-stream" in r.headers["content-type"]
        body = r.text
        assert "analysing" in body
        assert "Decouple the dependency" in body

    def test_409_when_already_generating(self):
        import api as api_module
        key = "doc_abc:A:B"
        api_module._active_mitigations.add(key)
        try:
            mock_vault = _make_vault(friction_row=_friction_row())
            with patch("api.vault", mock_vault):
                with TestClient(app) as c:
                    r = c.post(
                        "/api/v1/reports/mitigation/doc_abc",
                        params={"source_node_id": "A", "target_node_id": "B"},
                    )
            assert r.status_code == 409
        finally:
            api_module._active_mitigations.discard(key)

    def test_falls_back_to_chronological_table(self):
        mock_vault = _make_vault(friction_row=None, chron_row=_friction_row(diamond="Temporal conflict"))
        mock_result = {"analysis": "Resolve the timeline conflict.", "is_genuine": True, "confidence": 0.8, "severity": 2, "probability": 2}
        with patch("api.vault", mock_vault):
            with patch("api.ContradictionHunterAgent.synthesize_mitigation", return_value=mock_result):
                with TestClient(app) as c:
                    r = c.post(
                        "/api/v1/reports/mitigation/doc_abc",
                        params={"source_node_id": "A", "target_node_id": "B"},
                    )
        assert r.status_code == 200
        assert "Resolve the timeline conflict" in r.text

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
        response = test_client.get("/api/v1/canvas/doc_doesnotexist")
        assert response.status_code == 404
        assert response.json()["detail"] == "Document not found."


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

    def test_delete_500_detail_contains_exception_message(self):
        mock_vault = _make_mock_vault(fetchone_value={"id": "doc_broken"})
        mock_vault.delete_document.side_effect = Exception("ChromaDB connection refused")
        with patch("api.vault", mock_vault):
            with TestClient(app) as c:
                response = c.delete("/api/v1/documents/doc_broken")
        assert response.status_code == 500
        assert "ChromaDB connection refused" in response.json()["detail"]

    def test_delete_returns_404_before_checking_409(self):
        """Document not found takes precedence over ingestion-in-progress."""
        mock_vault = _make_mock_vault(fetchone_value=None)
        job_store = {"job_1": {"status": "processing", "document_id": "doc_missing"}}
        with patch("api.vault", mock_vault), patch("api.JOB_STORE", job_store):
            with TestClient(app) as c:
                response = c.delete("/api/v1/documents/doc_missing")
        assert response.status_code == 404

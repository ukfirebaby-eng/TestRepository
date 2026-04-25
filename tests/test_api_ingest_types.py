import pytest
from pathlib import Path
from fastapi.testclient import TestClient
from unittest.mock import patch, MagicMock

from api import app


def _make_mock_vault():
    mock_vault = MagicMock()
    mock_vault.list_documents.return_value = []
    return mock_vault


@pytest.fixture
def client():
    mock_vault = _make_mock_vault()
    with patch("api.vault", mock_vault):
        with TestClient(app) as c:
            yield c


class TestIngestFileTypeValidation:
    def test_rejects_exe_with_415(self, client):
        response = client.post(
            "/api/v1/ingest",
            files={"file": ("payload.exe", b"MZ\x90\x00", "application/octet-stream")},
        )
        assert response.status_code == 415
        assert ".exe" in response.json()["detail"]

    def test_rejects_zip_with_415(self, client):
        response = client.post(
            "/api/v1/ingest",
            files={"file": ("archive.zip", b"PK\x03\x04", "application/zip")},
        )
        assert response.status_code == 415

    def test_rejects_no_extension_with_415(self, client):
        response = client.post(
            "/api/v1/ingest",
            files={"file": ("noextension", b"data", "application/octet-stream")},
        )
        assert response.status_code == 415

    @pytest.mark.parametrize("filename,mime", [
        ("report.pdf", "application/pdf"),
        ("notes.txt", "text/plain"),
        ("readme.md", "text/markdown"),
        ("strategy.docx", "application/vnd.openxmlformats-officedocument.wordprocessingml.document"),
        ("data.xlsx", "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"),
        ("risks.csv", "text/csv"),
        ("deck.pptx", "application/vnd.openxmlformats-officedocument.presentationml.presentation"),
    ])
    def test_accepts_allowed_extension(self, client, filename, mime):
        with patch("api._run_ingestion_task"):
            response = client.post(
                "/api/v1/ingest",
                files={"file": (filename, b"fake content", mime)},
            )
        assert response.status_code == 200
        body = response.json()
        assert "job_id" in body
        assert "document_id" in body
        assert body["status"] == "pending"

    def test_415_response_lists_allowed_types(self, client):
        response = client.post(
            "/api/v1/ingest",
            files={"file": ("bad.psd", b"data", "image/vnd.adobe.photoshop")},
        )
        assert response.status_code == 415
        detail = response.json()["detail"]
        # Should mention allowed formats
        assert ".pdf" in detail

    def test_sanitizes_uploaded_filename_before_writing(self, client, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        escaped_path = tmp_path / "escape.pdf"

        with patch("api._run_ingestion_task") as task:
            response = client.post(
                "/api/v1/ingest",
                files={"file": ("../escape.pdf", b"%PDF fake", "application/pdf")},
            )

        assert response.status_code == 200
        assert not escaped_path.exists()
        saved_path = Path(task.call_args.args[1])
        assert (tmp_path / "temp_uploads").resolve() in saved_path.resolve().parents
        assert saved_path.name != "escape.pdf"

    def test_rejects_upload_larger_than_limit_before_writing(self, client, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        monkeypatch.setattr("api.MAX_UPLOAD_BYTES", 4)

        with patch("api._run_ingestion_task") as task:
            response = client.post(
                "/api/v1/ingest",
                files={"file": ("large.pdf", b"12345", "application/pdf")},
            )

        assert response.status_code == 413
        assert "Upload too large" in response.json()["detail"]
        assert not (tmp_path / "temp_uploads").exists()
        task.assert_not_called()

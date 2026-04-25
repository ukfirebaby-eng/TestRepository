from io import BytesIO
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from fastapi.testclient import TestClient

from api import app


def _make_vault(doc_exists=True, narrative=None):
    vault = MagicMock()
    cursor = MagicMock()
    cursor.fetchone.return_value = {"id": "doc_abc"} if doc_exists else None
    vault.conn.cursor.return_value = cursor
    vault.get_narrative_report.return_value = narrative
    return vault


def _payload():
    return {
        "metadata": {"document_name": "Board Report / Q1"},
        "executive_summary": "Summary",
        "risk_heatmap": [],
        "key_findings": [],
        "chapters": [],
        "issue_register": [],
        "methodology": "Method",
    }


class TestPdfExport:
    def test_returns_404_for_unknown_document(self):
        with patch("api.vault", _make_vault(doc_exists=False)):
            with TestClient(app) as client:
                response = client.get("/api/v1/export/pdf/doc_missing")

        assert response.status_code == 404

    def test_returns_409_when_narrative_missing(self):
        with patch("api.vault", _make_vault(narrative=None)):
            with TestClient(app) as client:
                response = client.get("/api/v1/export/pdf/doc_abc")

        assert response.status_code == 409
        assert response.json()["detail"] == "Generate the narrative report first."

    def test_returns_descriptive_500_when_pdf_renderer_missing(self):
        assembler = MagicMock()
        assembler.assemble.return_value = _payload()
        with patch("api.vault", _make_vault(narrative={"chapters": []})), \
             patch("api.ReportAssembler", return_value=assembler), \
             patch.dict("sys.modules", {"weasyprint": None}):
            with TestClient(app, raise_server_exceptions=False) as client:
                response = client.get("/api/v1/export/pdf/doc_abc")

        assert response.status_code == 500
        assert "WeasyPrint" in response.json()["detail"]

    def test_streams_pdf_with_safe_filename(self):
        fake_html = SimpleNamespace(write_pdf=lambda: b"%PDF fake")
        fake_weasyprint = SimpleNamespace(HTML=lambda string: fake_html)
        assembler = MagicMock()
        assembler.assemble.return_value = _payload()

        with patch("api.vault", _make_vault(narrative={"chapters": []})), \
             patch("api.ReportAssembler", return_value=assembler), \
             patch.dict("sys.modules", {"weasyprint": fake_weasyprint}):
            with TestClient(app) as client:
                response = client.get("/api/v1/export/pdf/doc_abc")

        assert response.status_code == 200
        assert response.headers["content-type"] == "application/pdf"
        assert 'filename="Diamond_Miner_Report_Board_Report___Q1.pdf"' in response.headers["content-disposition"]
        assert response.content == b"%PDF fake"


class TestDocxExport:
    def test_returns_409_when_narrative_missing(self):
        with patch("api.vault", _make_vault(narrative=None)):
            with TestClient(app) as client:
                response = client.get("/api/v1/export/docx/doc_abc")

        assert response.status_code == 409

    def test_streams_docx_with_safe_filename(self):
        assembler = MagicMock()
        assembler.assemble.return_value = _payload()

        with patch("api.vault", _make_vault(narrative={"chapters": []})), \
             patch("api.ReportAssembler", return_value=assembler), \
             patch("api.build_narrative_docx", return_value=BytesIO(b"docx")):
            with TestClient(app) as client:
                response = client.get("/api/v1/export/docx/doc_abc")

        assert response.status_code == 200
        assert response.headers["content-type"] == "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
        assert 'filename="Diamond_Miner_Report_Board_Report___Q1.docx"' in response.headers["content-disposition"]
        assert response.content == b"docx"

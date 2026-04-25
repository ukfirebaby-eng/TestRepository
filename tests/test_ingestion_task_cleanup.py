from pathlib import Path
from unittest.mock import MagicMock, patch

import api


def test_run_ingestion_task_removes_temp_file_on_success(tmp_path):
    upload = tmp_path / "upload.pdf"
    upload.write_bytes(b"fake")
    job_store = {"job_1": {"status": "pending", "document_id": "doc_1", "log": []}}
    orchestrator = MagicMock()
    orchestrator.interrogate_friction.return_value = []
    orchestrator.interrogate_time_friction.return_value = []

    with patch("api.JOB_STORE", job_store), \
         patch("api.DOCUMENT_STORE", {}), \
         patch("api.DiamondOrchestrator", return_value=orchestrator):
        api._run_ingestion_task("job_1", str(upload), "tenant", "doc_1", "upload.pdf")

    assert job_store["job_1"]["status"] == "completed"
    assert not upload.exists()


def test_run_ingestion_task_removes_temp_file_on_failure(tmp_path):
    upload = tmp_path / "upload.pdf"
    upload.write_bytes(b"fake")
    job_store = {"job_1": {"status": "pending", "document_id": "doc_1", "log": []}}
    orchestrator = MagicMock()
    orchestrator.run_ingestion_pipeline.side_effect = RuntimeError("parser failed")

    with patch("api.JOB_STORE", job_store), \
         patch("api.DiamondOrchestrator", return_value=orchestrator):
        api._run_ingestion_task("job_1", str(upload), "tenant", "doc_1", "upload.pdf")

    assert job_store["job_1"]["status"] == "failed"
    assert job_store["job_1"]["error"] == "parser failed"
    assert job_store["job_1"]["error_code"] == "INGESTION_FAILED"
    assert not upload.exists()

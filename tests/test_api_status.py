from fastapi.testclient import TestClient
from unittest.mock import patch

from api import app


def test_job_status_returns_claim_layer_accuracy_telemetry():
    job_store = {
        "job_1": {
            "status": "processing",
            "document_id": "doc_1",
            "log": ["Claim layer extracted 4 claims."],
            "accuracy": {
                "evidence_spans": 7,
                "claims": 4,
                "validated": 2,
                "needs_review": 1,
                "failed": 1,
                "promotable": 2,
                "batches_attempted": 2,
                "batches_succeeded": 2,
                "claims_before_dedupe": 5,
                "claims_after_dedupe": 4,
            },
        }
    }

    with patch("api.JOB_STORE", job_store):
        with TestClient(app) as client:
            response = client.get("/api/v1/status/job_1")

    assert response.status_code == 200
    assert response.json()["accuracy"] == job_store["job_1"]["accuracy"]


def test_job_status_returns_404_for_unknown_job():
    with patch("api.JOB_STORE", {}):
        with TestClient(app) as client:
            response = client.get("/api/v1/status/missing")

    assert response.status_code == 404
    assert response.json()["detail"] == "Job not found"

import json
import pytest
from fastapi.testclient import TestClient
from unittest.mock import patch, MagicMock

from api import app, _attach_report_grounding, _gather_raw_issues


def _make_mock_vault(doc_exists=True, cached_report=None):
    mock_vault = MagicMock()

    def fresh_cursor():
        cur = MagicMock()
        cur.fetchone.return_value = {"id": "doc_abc"} if doc_exists else None
        cur.fetchall.return_value = []
        return cur

    mock_vault.conn.cursor.side_effect = fresh_cursor
    mock_vault.get_executive_summary.return_value = cached_report
    mock_vault.get_friction_lines.return_value = []
    mock_vault.get_chronological_friction_lines.return_value = []
    mock_vault.get_hub_vulnerabilities.return_value = []
    mock_vault.get_risk_matrix_data.return_value = []
    mock_vault.list_accuracy_review_decisions.return_value = {}
    return mock_vault


def _minimal_report():
    return {
        "overall_assessment": "No Issues Found",
        "generated_at": "2026-03-25T12:00:00Z",
        "summary_narrative": "No issues.",
        "business_impact": "",
        "issues": [],
        "coverage_verified": True,
        "coverage_warning": None,
    }


class TestGetExecutiveSummary:
    def test_returns_404_for_missing_document(self):
        mock_vault = _make_mock_vault(doc_exists=False)
        with patch("api.vault", mock_vault):
            with TestClient(app) as c:
                response = c.get("/api/v1/reports/executive-summary/doc_missing")
        assert response.status_code == 404

    def test_returns_cached_false_when_no_cache(self):
        mock_vault = _make_mock_vault(cached_report=None)
        with patch("api.vault", mock_vault):
            with TestClient(app) as c:
                response = c.get("/api/v1/reports/executive-summary/doc_abc")
        assert response.status_code == 200
        assert response.json()["cached"] is False

    def test_returns_cached_true_with_report_when_cached(self):
        mock_vault = _make_mock_vault(cached_report=_minimal_report())
        with patch("api.vault", mock_vault):
            with TestClient(app) as c:
                response = c.get("/api/v1/reports/executive-summary/doc_abc")
        data = response.json()
        assert data["cached"] is True
        assert data["report"]["overall_assessment"] == "No Issues Found"


class TestReportGrounding:
    def test_gather_raw_issues_adds_grounding_from_structured_findings(self):
        mock_vault = _make_mock_vault()
        mock_vault.get_friction_lines.return_value = [{
            "source": "cloud_migration",
            "target": "security_certification",
            "diamond": "Migration starts before certification.",
            "severity": 4,
            "probability": 4,
            "finding": {
                "confidence_score": 0.96,
                "confidence_level": "high",
                "claim_ids": ["claim_1"],
                "evidence_span_ids": ["span_1", "span_2"],
                "claim_validation_status": "passed",
            },
        }]

        with patch("api.vault", mock_vault):
            raw = _gather_raw_issues("doc_abc")

        grounding = raw["friction_lines"][0]["grounding"]
        assert grounding["confidence_score"] == 0.96
        assert grounding["confidence_level"] == "high"
        assert grounding["claim_ids"] == ["claim_1"]
        assert grounding["evidence_span_ids"] == ["span_1", "span_2"]
        assert grounding["evidence_basis"] == "validated_claims"

    def test_gather_raw_issues_adds_accuracy_review_context_for_reports(self):
        mock_vault = _make_mock_vault()
        mock_vault.list_accuracy_review_decisions.return_value = {
            "claim-only:entity_api_gateway:BLOCKS:entity_deployment": {
                "document_id": "doc_abc",
                "candidate_id": "claim-only:entity_api_gateway:BLOCKS:entity_deployment",
                "state": "accepted",
                "kind": "claim-only",
                "label": "api gateway blocks deployment",
                "updated_at": "2026-06-07T12:00:00Z",
            },
            "legacy-only:entity_legacy_gateway:DEPENDS_ON:entity_customer_portal": {
                "document_id": "doc_abc",
                "candidate_id": "legacy-only:entity_legacy_gateway:DEPENDS_ON:entity_customer_portal",
                "state": "ignored",
                "kind": "legacy-only",
                "label": "legacy gateway depends on customer portal",
                "updated_at": "2026-06-07T12:01:00Z",
            },
        }
        agreement = {
            "claim_only_edge_count": 1,
            "accepted_claim_only_edge_count": 1,
            "active_claim_only_edge_count": 0,
            "claim_only_edges": [{
                "source_id": "entity_api_gateway",
                "target_id": "entity_deployment",
                "relationship": "BLOCKS",
                "canonical_source_id": "entity_api_gateway",
                "canonical_target_id": "entity_deployment",
                "review_state": "accepted",
            }],
            "legacy_only_edges": [{
                "source_id": "entity_legacy_gateway",
                "target_id": "entity_customer_portal",
                "relationship": "DEPENDS_ON",
                "canonical_source_id": "entity_legacy_gateway",
                "canonical_target_id": "entity_customer_portal",
                "review_state": "ignored",
            }],
        }

        with patch("api.vault", mock_vault), \
             patch("api.collect_parallel_graph_agreement", return_value=agreement):
            raw = _gather_raw_issues("doc_abc")

        context = raw["accuracy_review_context"]
        assert context["review_decisions"][0]["state"] == "accepted"
        assert context["graph_agreement"] == agreement
        assert context["report_guidance"]["supporting_evidence_candidate_ids"] == [
            "claim-only:entity_api_gateway:BLOCKS:entity_deployment"
        ]
        assert context["report_guidance"]["excluded_candidate_ids"] == [
            "legacy-only:entity_legacy_gateway:DEPENDS_ON:entity_customer_portal"
        ]
        assert context["report_guidance"]["candidate_guidance"][0]["report_use"] == "supporting_evidence"
        assert context["report_guidance"]["candidate_guidance"][1]["report_use"] == "excluded"

    def test_attach_report_grounding_carries_review_guidance_summary(self):
        guidance = {
            "supporting_evidence_candidate_ids": ["claim-only:entity_api_gateway:BLOCKS:entity_deployment"],
            "excluded_candidate_ids": ["legacy-only:entity_legacy_gateway:DEPENDS_ON:entity_customer_portal"],
            "human_confirmed_legacy_candidate_ids": [],
            "active_review_candidate_ids": [],
            "candidate_guidance": [],
        }
        raw_issues = {
            "friction_lines": [],
            "chronological_friction_lines": [],
            "hub_vulnerabilities": [],
            "risk_matrix": [],
            "accuracy_review_context": {"report_guidance": guidance},
        }

        grounded = _attach_report_grounding(_minimal_report(), raw_issues)

        assert grounded["review_guidance_summary"] == guidance

    def test_attach_report_grounding_adds_summary_and_issue_metadata(self):
        report = {
            **_minimal_report(),
            "issues": [{
                "severity": "high",
                "title": "Migration starts before certification",
                "plain_english": "Cloud migration is starting before security certification.",
                "solution": "Move migration until certification is complete.",
                "source_nodes": ["cloud_migration", "security_certification"],
            }],
        }
        raw_issues = {
            "friction_lines": [{
                "source": "cloud_migration",
                "target": "security_certification",
                "grounding": {
                    "confidence_score": 0.96,
                    "confidence_level": "high",
                    "claim_ids": ["claim_1"],
                    "evidence_span_ids": ["span_1", "span_2"],
                    "claim_validation_status": "passed",
                    "evidence_basis": "validated_claims",
                },
            }],
            "chronological_friction_lines": [],
            "hub_vulnerabilities": [],
        }

        grounded = _attach_report_grounding(report, raw_issues)

        assert grounded["grounding_summary"] == {
            "grounded_issue_count": 1,
            "claim_ids": ["claim_1"],
            "evidence_span_ids": ["span_1", "span_2"],
            "claim_count": 1,
            "validated_claim_count": 1,
            "evidence_span_count": 2,
            "legacy_only_count": 0,
            "highest_confidence_level": "high",
            "confidence_score": 0.96,
            "confidence_level": "high",
        }
        assert grounded["issues"][0]["grounding"]["confidence_score"] == 0.96
        assert grounded["issues"][0]["grounding"]["evidence_basis"] == "validated_claims"


class TestPostExecutiveSummary:
    def _run_post_stream(self, mock_vault):
        """Fires the POST and collects all SSE event lines."""
        mock_storyteller = MagicMock()
        mock_storyteller.run.return_value = _minimal_report()
        mock_storyteller.model = "gpt-4o"

        mock_critic = MagicMock()
        mock_critic.run.return_value = _minimal_report()

        mock_kde = MagicMock()
        mock_kde.check.return_value = _minimal_report()

        with patch("api.vault", mock_vault), \
             patch("api.StorytellerAgent", return_value=mock_storyteller), \
             patch("api.CriticAgent", return_value=mock_critic), \
             patch("api.KDECoverageCheck", return_value=mock_kde), \
             patch("api._active_generations", set()):
            with TestClient(app) as c:
                with c.stream("POST", "/api/v1/reports/executive-summary/doc_abc") as r:
                    lines = [line for line in r.iter_lines() if line.startswith("data:")]
        return lines

    def test_returns_404_for_missing_document(self):
        mock_vault = _make_mock_vault(doc_exists=False)
        with patch("api.vault", mock_vault):
            with TestClient(app) as c:
                response = c.post("/api/v1/reports/executive-summary/doc_missing")
        assert response.status_code == 404

    def test_returns_409_when_already_generating(self):
        mock_vault = _make_mock_vault()
        with patch("api.vault", mock_vault), \
             patch("api._active_generations", {"doc_abc"}):
            with TestClient(app) as c:
                response = c.post("/api/v1/reports/executive-summary/doc_abc")
        assert response.status_code == 409

    def test_streams_four_progress_events(self):
        lines = self._run_post_stream(_make_mock_vault())
        stages = [json.loads(l[5:])["stage"] for l in lines]
        assert "analysing" in stages
        assert "drafting" in stages
        assert "auditing" in stages
        assert "verifying" in stages

    def test_streams_complete_event_with_report(self):
        lines = self._run_post_stream(_make_mock_vault())
        complete_lines = [l for l in lines if '"complete"' in l]
        assert len(complete_lines) == 1
        data = json.loads(complete_lines[0][5:])
        assert "report" in data
        assert data["report"]["overall_assessment"] == "No Issues Found"

    def test_writes_to_cache_on_complete(self):
        mock_vault = _make_mock_vault()
        self._run_post_stream(mock_vault)
        mock_vault.save_executive_summary.assert_called_once()

    def test_streams_error_event_when_provider_fails(self):
        mock_vault = _make_mock_vault()
        mock_storyteller = MagicMock()
        mock_storyteller.run.side_effect = RuntimeError("provider rejected max_tokens")
        mock_storyteller.model = "openrouter/test"

        with patch("api.vault", mock_vault), \
             patch("api.StorytellerAgent", return_value=mock_storyteller), \
             patch("api._active_generations", set()):
            with TestClient(app) as c:
                response = c.post("/api/v1/reports/executive-summary/doc_abc")

        assert response.status_code == 200
        events = [json.loads(line[5:]) for line in response.text.splitlines() if line.startswith("data:")]
        assert events[-1]["stage"] == "error"
        assert "provider rejected max_tokens" in events[-1]["message"]
        mock_vault.save_executive_summary.assert_not_called()


class TestDeleteExecutiveSummary:
    def test_returns_404_for_missing_document(self):
        mock_vault = _make_mock_vault(doc_exists=False)
        with patch("api.vault", mock_vault):
            with TestClient(app) as c:
                response = c.delete("/api/v1/reports/executive-summary/doc_missing")
        assert response.status_code == 404

    def test_returns_204_when_cache_exists(self):
        mock_vault = _make_mock_vault()
        with patch("api.vault", mock_vault):
            with TestClient(app) as c:
                response = c.delete("/api/v1/reports/executive-summary/doc_abc")
        assert response.status_code == 204

    def test_returns_204_when_no_cache_row_idempotent(self):
        mock_vault = _make_mock_vault(cached_report=None)
        with patch("api.vault", mock_vault):
            with TestClient(app) as c:
                response = c.delete("/api/v1/reports/executive-summary/doc_abc")
        assert response.status_code == 204

    def test_calls_delete_executive_summary(self):
        mock_vault = _make_mock_vault()
        with patch("api.vault", mock_vault):
            with TestClient(app) as c:
                c.delete("/api/v1/reports/executive-summary/doc_abc")
        mock_vault.delete_executive_summary.assert_called_once_with("doc_abc")

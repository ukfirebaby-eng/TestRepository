from datetime import datetime, timezone
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

from api import app
from core.accuracy.schemas import CanonicalEntity, DocumentManifest, EvidenceSpan, ExtractedClaim, ValidationResult
from core.vault import HybridVault


@pytest.fixture
def client(tmp_path):
    test_vault = HybridVault(tenant_id="accuracy_api", base_dir=str(tmp_path))
    with patch("api.vault", test_vault):
        with TestClient(app) as c:
            yield c, test_vault
    test_vault.conn.close()


def test_returns_claim_layer_accuracy_payload(client):
    test_client, vault = client
    vault.insert_document("doc_1", "strategy.md")
    vault.save_document_manifest(DocumentManifest(
        document_id="doc_1",
        filename="strategy.md",
        source_hash="sha256:abc",
        ingested_at=datetime.now(timezone.utc),
        llm_model="gpt-4o-mini",
        validation_status="partial",
    ))
    vault.insert_evidence_spans([
        EvidenceSpan(
            span_id="span_1",
            document_id="doc_1",
            chunk_id="chunk_1",
            page_number=1,
            text="Cloud migration requires security certification.",
            span_type="sentence",
            source_hash="sha256:abc",
        )
    ])
    vault.insert_extracted_claims([
        ExtractedClaim(
            claim_id="claim_1",
            document_id="doc_1",
            claim_type="dependency",
            subject="Cloud migration",
            predicate="requires",
            object="security certification",
            modality="must",
            certainty="explicit",
            evidence_span_ids=["span_1"],
            source_quote="Cloud migration requires security certification.",
            confidence=0.92,
            validation_status="passed",
        )
    ])
    vault.insert_validation_results([
        ValidationResult(
            claim_id="claim_1",
            document_id="doc_1",
            status="passed",
            reasons=[],
            can_promote=True,
        )
    ])
    vault.insert_canonical_entities("doc_1", [
        CanonicalEntity(
            entity_id="entity_cloud_migration",
            canonical_name="Cloud Migration",
            entity_type="initiative",
            aliases=["Cloud migration"],
            source_span_ids=["span_1"],
            confidence=0.92,
        )
    ])

    response = test_client.get("/api/v1/accuracy/doc_1")

    assert response.status_code == 200
    body = response.json()
    assert body["document_id"] == "doc_1"
    assert body["manifest"]["filename"] == "strategy.md"
    assert body["counts"] == {
        "evidence_spans": 1,
        "claims": 1,
        "validated": 1,
        "needs_review": 0,
        "failed": 0,
        "extraction_failures": 0,
        "canonical_entities": 1,
    }
    assert body["evidence_spans"][0]["span_id"] == "span_1"
    assert body["claims"][0]["claim_id"] == "claim_1"
    assert body["validation_results"][0]["can_promote"] == 1
    assert body["canonical_entities"][0]["canonical_name"] == "Cloud Migration"
    assert body["canonical_entities"][0]["aliases"] == ["Cloud migration"]
    assert body["extraction_failures"] == []


def test_accuracy_payload_404s_for_unknown_document(client):
    test_client, _ = client

    response = test_client.get("/api/v1/accuracy/missing")

    assert response.status_code == 404
    assert response.json()["detail"] == "Document not found."


def test_accuracy_review_decisions_persist_and_return_with_payload(client):
    test_client, vault = client
    vault.insert_document("doc_review", "review.md")

    create = test_client.post("/api/v1/accuracy/doc_review/review-decisions", json={
        "candidate_id": "claim-only:entity_cloud_migration:REQUIRES:entity_security_certification",
        "state": "accepted",
        "kind": "claim-only",
        "label": "cloud migration requires security certification",
    })

    assert create.status_code == 200
    assert create.json()["decision"]["state"] == "accepted"

    update = test_client.post("/api/v1/accuracy/doc_review/review-decisions", json={
        "candidate_id": "claim-only:entity_cloud_migration:REQUIRES:entity_security_certification",
        "state": "ignored",
        "kind": "claim-only",
        "label": "cloud migration requires security certification",
    })

    assert update.status_code == 200
    assert update.json()["review_states"] == {
        "claim-only:entity_cloud_migration:REQUIRES:entity_security_certification": "ignored",
    }

    payload = test_client.get("/api/v1/accuracy/doc_review").json()

    assert payload["review_states"] == {
        "claim-only:entity_cloud_migration:REQUIRES:entity_security_certification": "ignored",
    }
    assert payload["review_decisions"][0]["kind"] == "claim-only"
    assert payload["review_decisions"][0]["label"] == "cloud migration requires security certification"


def test_accuracy_review_decision_rejects_invalid_state(client):
    test_client, vault = client
    vault.insert_document("doc_review", "review.md")

    response = test_client.post("/api/v1/accuracy/doc_review/review-decisions", json={
        "candidate_id": "candidate",
        "state": "approved",
        "kind": "claim-only",
        "label": "candidate",
    })

    assert response.status_code == 422


def test_accuracy_payload_includes_claim_quality_report(client):
    test_client, vault = client
    vault.insert_document("doc_quality", "quality.md")
    vault.insert_evidence_spans([
        EvidenceSpan(
            span_id="span_1",
            document_id="doc_quality",
            chunk_id="chunk_1",
            page_number=1,
            text="Cloud migration requires certification.",
            span_type="sentence",
            source_hash="sha256:abc",
        ),
        EvidenceSpan(
            span_id="span_2",
            document_id="doc_quality",
            chunk_id="chunk_2",
            page_number=1,
            text="API gateway blocks deployment.",
            span_type="sentence",
            source_hash="sha256:abc",
        ),
        EvidenceSpan(
            span_id="span_3",
            document_id="doc_quality",
            chunk_id="chunk_3",
            page_number=1,
            text="Background context.",
            span_type="sentence",
            source_hash="sha256:abc",
        ),
    ])
    vault.insert_extracted_claims([
        ExtractedClaim(
            claim_id="claim_1",
            document_id="doc_quality",
            claim_type="dependency",
            subject="Cloud migration",
            predicate="requires",
            object="certification",
            modality="must",
            certainty="explicit",
            evidence_span_ids=["span_1"],
            source_quote="Cloud migration requires certification.",
            confidence=0.92,
            validation_status="passed",
        ),
        ExtractedClaim(
            claim_id="claim_2",
            document_id="doc_quality",
            claim_type="blocker",
            subject="API gateway",
            predicate="blocks",
            object="deployment",
            modality="must",
            certainty="implied",
            evidence_span_ids=["span_2"],
            source_quote="API gateway blocks deployment.",
            confidence=0.6,
            validation_status="needs_review",
        ),
    ])
    vault.insert_validation_results([
        ValidationResult(
            claim_id="claim_1",
            document_id="doc_quality",
            status="passed",
            reasons=[],
            can_promote=True,
        ),
        ValidationResult(
            claim_id="claim_2",
            document_id="doc_quality",
            status="needs_review",
            reasons=[
                "claim certainty is not explicit",
                "confidence below promotion threshold",
                "Claim subject is too generic for graph promotion: The programme.",
                "Claim subject and object resolve to the same entity.",
            ],
            can_promote=False,
        ),
    ])
    vault.insert_canonical_entities("doc_quality", [
        CanonicalEntity(
            entity_id="entity_cloud_migration",
            canonical_name="Cloud Migration",
            entity_type="initiative",
            aliases=["Cloud migration", "The Cloud-Migration Programme"],
            source_span_ids=["span_1"],
            confidence=0.92,
        ),
        CanonicalEntity(
            entity_id="entity_api_gateway",
            canonical_name="API Gateway",
            entity_type="system",
            aliases=["API gateway"],
            source_span_ids=["span_2"],
            confidence=0.6,
        ),
    ])
    vault.insert_graph_topology(
        nodes=[
            {"id": "cloud_migration", "label": "Concept", "name": "Cloud Migration"},
            {"id": "certification", "label": "Concept", "name": "Certification"},
            {"id": "legacy_only_source", "label": "Concept", "name": "Legacy Only Source"},
            {"id": "legacy_only_target", "label": "Concept", "name": "Legacy Only Target"},
        ],
        edges=[
            {
                "source_id": "cloud_migration",
                "target_id": "certification",
                "relationship": "REQUIRES",
            },
            {
                "source_id": "legacy_only_source",
                "target_id": "legacy_only_target",
                "relationship": "BLOCKS",
            }
        ],
        source_chunk_id="legacy_chunk",
        document_id="doc_quality",
    )
    vault.insert_graph_topology(
        nodes=[
            {"id": "entity_cloud_migration", "label": "Concept", "name": "Cloud Migration"},
            {"id": "entity_certification", "label": "Concept", "name": "Certification"},
            {"id": "entity_claim_only_source", "label": "Concept", "name": "Claim Only Source"},
            {"id": "entity_claim_only_target", "label": "Concept", "name": "Claim Only Target"},
        ],
        edges=[
            {
                "source_id": "entity_cloud_migration",
                "target_id": "entity_certification",
                "relationship": "REQUIRES",
                "claim_id": "claim_1",
                "evidence_span_ids": ["span_1"],
            },
            {
                "source_id": "entity_claim_only_source",
                "target_id": "entity_claim_only_target",
                "relationship": "REQUIRES",
                "claim_id": "claim_2",
                "evidence_span_ids": ["span_2"],
            }
        ],
        source_chunk_id="claim_layer",
        document_id="doc_quality",
    )
    vault.save_accuracy_review_decision(
        document_id="doc_quality",
        candidate_id="claim-only:entity_claim_only_source:REQUIRES:entity_claim_only_target",
        state="accepted",
        kind="claim-only",
        label="claim only source requires claim only target",
    )
    vault.save_accuracy_review_decision(
        document_id="doc_quality",
        candidate_id="legacy-only:entity_legacy_only_source:BLOCKS:entity_legacy_only_target",
        state="ignored",
        kind="legacy-only",
        label="legacy only source blocks legacy only target",
    )

    response = test_client.get("/api/v1/accuracy/doc_quality")

    assert response.status_code == 200
    assert response.json()["quality"] == {
        "extraction_coverage": {
            "evidence_span_count": 3,
            "evidence_spans_with_claims": 2,
            "coverage_rate": 0.6667,
            "claims_per_evidence_span": 0.6667,
        },
        "validation_quality": {
            "passed": 1,
            "needs_review": 1,
            "failed": 0,
            "pass_rate": 0.5,
            "review_rate": 0.5,
            "fail_rate": 0.0,
        },
        "promotion_readiness": {
            "promotable": 1,
            "promotion_rate": 0.5,
            "human_accepted_claim_only_edges": 1,
            "effective_promotable": 2,
            "review_adjusted_denominator": 3,
            "effective_promotion_rate": 0.6667,
        },
        "entity_normalization": {
            "canonical_entities": 2,
            "raw_aliases": 3,
            "average_aliases_per_entity": 1.5,
        },
        "graph_agreement": {
            "legacy_edge_count": 2,
            "claim_promoted_edge_count": 2,
            "shared_canonical_edge_count": 1,
            "legacy_only_edge_count": 1,
            "claim_only_edge_count": 1,
            "accepted_claim_only_edge_count": 1,
            "ignored_claim_only_edge_count": 0,
            "accepted_legacy_only_edge_count": 0,
            "ignored_legacy_only_edge_count": 1,
            "active_claim_only_edge_count": 0,
            "active_legacy_only_edge_count": 0,
            "human_promoted_edge_count": 1,
            "claim_vs_legacy_overlap_rate": 0.5,
            "legacy_only_edges": [
                {
                    "source_id": "legacy_only_source",
                    "target_id": "legacy_only_target",
                    "relationship": "BLOCKS",
                    "canonical_source_id": "entity_legacy_only_source",
                    "canonical_target_id": "entity_legacy_only_target",
                    "source_chunk_id": "legacy_chunk",
                    "claim_id": None,
                    "evidence_span_ids": [],
                    "review_state": "ignored",
                }
            ],
            "claim_only_edges": [
                {
                    "source_id": "entity_claim_only_source",
                    "target_id": "entity_claim_only_target",
                    "relationship": "REQUIRES",
                    "canonical_source_id": "entity_claim_only_source",
                    "canonical_target_id": "entity_claim_only_target",
                    "source_chunk_id": "claim_layer",
                    "claim_id": "claim_2",
                    "evidence_span_ids": ["span_2"],
                    "review_state": "accepted",
                }
            ],
        },
        "report_confidence": {
            "active_mismatch_count": 0,
            "accepted_mismatch_count": 1,
            "ignored_mismatch_count": 1,
            "review_adjusted_overlap_rate": 1.0,
            "confidence_level": "high",
        },
        "top_review_reasons": [
            {"reason": "claim certainty is not explicit", "count": 1},
            {"reason": "confidence below promotion threshold", "count": 1},
            {"reason": "Claim subject is too generic for graph promotion: The programme.", "count": 1},
            {"reason": "Claim subject and object resolve to the same entity.", "count": 1},
        ],
        "review_reason_categories": [
            {
                "category": "certainty",
                "label": "Non-explicit claim",
                "count": 1,
                "examples": ["claim certainty is not explicit"],
            },
            {
                "category": "confidence",
                "label": "Low confidence",
                "count": 1,
                "examples": ["confidence below promotion threshold"],
            },
            {
                "category": "generic_endpoint",
                "label": "Generic graph endpoint",
                "count": 1,
                "examples": ["Claim subject is too generic for graph promotion: The programme."],
            },
            {
                "category": "self_reference",
                "label": "Self-referential relationship",
                "count": 1,
                "examples": ["Claim subject and object resolve to the same entity."],
            },
        ],
    }

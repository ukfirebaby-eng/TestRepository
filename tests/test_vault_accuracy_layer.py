from datetime import datetime, timezone

import pytest

from core.accuracy.schemas import (
    DocumentManifest,
    EvidenceSpan,
    ExtractionFailure,
    ExtractedClaim,
    CanonicalEntity,
    ValidationResult,
)
from core.vault import HybridVault


@pytest.fixture
def vault(tmp_path):
    v = HybridVault(tenant_id="accuracy", base_dir=str(tmp_path))
    yield v
    v.conn.close()


def test_saves_and_reads_document_manifest(vault):
    manifest = DocumentManifest(
        document_id="doc_1",
        filename="strategy.md",
        source_hash="sha256:abc",
        ingested_at=datetime.now(timezone.utc),
        llm_model="gpt-4o-mini",
    )

    vault.save_document_manifest(manifest)

    loaded = vault.get_document_manifest("doc_1")
    assert loaded["document_id"] == "doc_1"
    assert loaded["source_hash"] == "sha256:abc"


def test_saves_evidence_spans_and_claims(vault):
    span = EvidenceSpan(
        span_id="span_1",
        document_id="doc_1",
        chunk_id="chunk_1",
        page_number=1,
        text="Cloud migration requires security certification.",
        span_type="sentence",
        source_hash="sha256:abc",
    )
    claim = ExtractedClaim(
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
    )

    vault.insert_evidence_spans([span])
    vault.insert_extracted_claims([claim])

    assert vault.list_evidence_spans("doc_1")[0]["span_id"] == "span_1"
    assert vault.list_extracted_claims("doc_1")[0]["claim_id"] == "claim_1"


def test_saves_validation_results(vault):
    result = ValidationResult(
        claim_id="claim_1",
        document_id="doc_1",
        status="passed",
        reasons=[],
        can_promote=True,
    )

    vault.insert_validation_results([result])

    loaded = vault.list_validation_results("doc_1")
    assert loaded[0]["claim_id"] == "claim_1"
    assert loaded[0]["status"] == "passed"
    assert loaded[0]["can_promote"] == 1


def test_saves_extraction_failures(vault):
    failure = ExtractionFailure(
        id="failure_1",
        document_id="doc_1",
        span_id="span_1",
        agent="claim_extractor",
        error="Invalid JSON response",
        raw_payload="{not-json",
        created_at=datetime.now(timezone.utc),
    )

    vault.insert_extraction_failures([failure])

    loaded = vault.list_extraction_failures("doc_1")
    assert loaded[0]["id"] == "failure_1"
    assert loaded[0]["span_id"] == "span_1"
    assert loaded[0]["agent"] == "claim_extractor"


def test_saves_and_reads_canonical_entities(vault):
    entity = CanonicalEntity(
        entity_id="entity_cloud_migration",
        canonical_name="Cloud Migration",
        entity_type="initiative",
        aliases=["The Cloud-Migration Programme", "cloud migration"],
        source_span_ids=["span_1", "span_2"],
        confidence=0.9,
    )

    vault.insert_canonical_entities("doc_1", [entity])

    loaded = vault.list_canonical_entities("doc_1")
    assert loaded == [
        {
            "entity_id": "entity_cloud_migration",
            "document_id": "doc_1",
            "canonical_name": "Cloud Migration",
            "entity_type": "initiative",
            "aliases": ["The Cloud-Migration Programme", "cloud migration"],
            "source_span_ids": ["span_1", "span_2"],
            "confidence": 0.9,
            "human_locked": 0,
        }
    ]


def test_triangular_conflicts_include_claim_edge_provenance(vault):
    vault.insert_graph_topology(
        nodes=[
            {"id": "migration", "label": "Concept", "name": "Cloud Migration"},
            {"id": "security", "label": "Concept", "name": "Security Certification"},
            {"id": "hardening", "label": "Concept", "name": "Cloud Platform Hardening"},
        ],
        edges=[
            {
                "source_id": "migration",
                "target_id": "security",
                "relationship": "REQUIRES",
                "claim_id": "claim_requires",
                "evidence_span_ids": ["span_requires"],
            },
            {
                "source_id": "hardening",
                "target_id": "security",
                "relationship": "BLOCKS",
                "claim_id": "claim_blocks",
                "evidence_span_ids": ["span_blocks"],
            },
        ],
        source_chunk_id="claim_layer",
        document_id="doc_1",
    )

    conflicts = vault.get_triangular_conflicts(document_id="doc_1")

    assert conflicts[0]["claim_ids"] == ["claim_requires", "claim_blocks"]
    assert conflicts[0]["evidence_span_ids"] == ["span_requires", "span_blocks"]


def test_saves_and_reads_accuracy_review_decisions(vault):
    vault.save_accuracy_review_decision(
        document_id="doc_1",
        candidate_id="claim-only:entity_cloud_migration:REQUIRES:entity_security_certification",
        state="accepted",
        kind="claim-only",
        label="cloud migration requires security certification",
    )
    vault.save_accuracy_review_decision(
        document_id="doc_1",
        candidate_id="legacy-only:entity_gateway:DEPENDS_ON:entity_portal",
        state="ignored",
        kind="legacy-only",
        label="gateway depends on portal",
    )

    loaded = vault.list_accuracy_review_decisions("doc_1")

    assert loaded["claim-only:entity_cloud_migration:REQUIRES:entity_security_certification"]["state"] == "accepted"
    assert loaded["claim-only:entity_cloud_migration:REQUIRES:entity_security_certification"]["kind"] == "claim-only"
    assert loaded["legacy-only:entity_gateway:DEPENDS_ON:entity_portal"]["state"] == "ignored"
    assert loaded["legacy-only:entity_gateway:DEPENDS_ON:entity_portal"]["updated_at"]

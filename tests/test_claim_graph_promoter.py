from core.accuracy.graph_promoter import promote_claim_to_topology
from core.accuracy.schemas import ExtractedClaim


def test_dependency_claim_promotes_to_requires_edge():
    claim = ExtractedClaim(
        claim_id="claim_1",
        document_id="doc_1",
        claim_type="dependency",
        subject="Cloud migration",
        predicate="requires",
        object="Security certification",
        modality="must",
        certainty="explicit",
        evidence_span_ids=["span_1"],
        source_quote="Cloud migration requires Security certification.",
        confidence=0.9,
        validation_status="passed",
    )

    topology = promote_claim_to_topology(claim)

    assert topology["nodes"] == [
        {"id": "entity_cloud_migration", "label": "Concept", "name": "Cloud Migration"},
        {"id": "entity_security_certification", "label": "Concept", "name": "Security Certification"},
    ]
    assert topology["edges"] == [
        {
            "source_id": "entity_cloud_migration",
            "target_id": "entity_security_certification",
            "relationship": "REQUIRES",
            "claim_id": "claim_1",
            "evidence_span_ids": ["span_1"],
        }
    ]


def test_unpassed_claim_does_not_promote():
    claim = ExtractedClaim(
        claim_id="claim_1",
        document_id="doc_1",
        claim_type="dependency",
        subject="Cloud migration",
        predicate="requires",
        object="Security certification",
        modality="must",
        certainty="inferred",
        evidence_span_ids=["span_1"],
        source_quote="Cloud migration requires Security certification.",
        confidence=0.9,
        validation_status="needs_review",
    )

    assert promote_claim_to_topology(claim) == {"nodes": [], "edges": []}


def test_claim_with_same_subject_and_object_does_not_promote_self_edge():
    claim = ExtractedClaim(
        claim_id="claim_1",
        document_id="doc_1",
        claim_type="dependency",
        subject="Orion Payments Modernisation Programme",
        predicate="requires",
        object="Orion Payments Modernisation Programme",
        modality="must",
        certainty="explicit",
        evidence_span_ids=["span_1"],
        source_quote="The programme requires steering approval.",
        confidence=0.9,
        validation_status="passed",
    )

    assert promote_claim_to_topology(claim) == {"nodes": [], "edges": []}


def test_claim_with_canonical_alias_self_edge_does_not_promote():
    claim = ExtractedClaim(
        claim_id="claim_1",
        document_id="doc_1",
        claim_type="dependency",
        subject="The Cloud-Migration Programme",
        predicate="requires",
        object="cloud migration",
        modality="must",
        certainty="explicit",
        evidence_span_ids=["span_1"],
        source_quote="The Cloud-Migration Programme requires cloud migration readiness.",
        confidence=0.9,
        validation_status="passed",
    )

    assert promote_claim_to_topology(claim) == {"nodes": [], "edges": []}


def test_claim_promotion_uses_canonical_entity_ids_and_names():
    claim = ExtractedClaim(
        claim_id="claim_1",
        document_id="doc_1",
        claim_type="dependency",
        subject="The Cloud-Migration Programme",
        predicate="requires",
        object="Security Certification",
        modality="must",
        certainty="explicit",
        evidence_span_ids=["span_1"],
        source_quote="The Cloud-Migration Programme requires Security Certification.",
        confidence=0.9,
        validation_status="passed",
    )

    topology = promote_claim_to_topology(claim)

    assert topology["nodes"][0] == {"id": "entity_cloud_migration", "label": "Concept", "name": "Cloud Migration"}
    assert topology["edges"][0]["source_id"] == "entity_cloud_migration"
